"""Agent 核心（多 Agent 版）：先把用户意图路由到一个专职智能体，再用该智能体的
系统提示与工具子集跑一轮 function-calling 循环。

- 路由 route()：轻量调用，把意图归类为 问答 / 刷题 / 材料 / 日程
- 运行 chat()：注入 RAG 资料 → 模型自行决定调工具或直接回答 → 返回 reply/来源/工具调用
所有工具结果与引用来源一并返回前端，便于答辩溯源与展示"哪个 Agent 在应答"。
"""
from __future__ import annotations

import json

from openai import OpenAI

from app import providers
from app import files as files_mod
from app.agent_defs import AGENTS, DEFAULT_AGENT, ROUTE_MAP, ROUTER_PROMPT
from app.config import settings
from app.tools import ToolContext, run_tool, tool_schemas
from rag import store

_client: OpenAI | None = None


def _llm() -> OpenAI:
    global _client
    if _client is None:
        if not settings.llm_api_key:
            raise RuntimeError("未配置 LLM_API_KEY，请在 backend/.env 填入 DeepSeek 密钥。")
        _client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    return _client


def _resolve_llm(llm: dict | None) -> tuple[OpenAI, str]:
    """选择用哪个大模型：
    - llm 带 api_key（用户在小程序里自填的 key）→ 用对应 provider 的地址与模型
    - 否则用服务端 .env 里配置的默认（DeepSeek）
    返回 (client, model)。"""
    if llm and llm.get("api_key"):
        base, model, _name = providers.resolve(llm.get("provider", ""), llm.get("model", ""))
        return OpenAI(api_key=llm["api_key"], base_url=base), model
    return _llm(), settings.llm_model


MAX_TOOL_ROUNDS = 4


def route(user_message: str, llm: dict | None = None) -> tuple[str, list[str]]:
    """路由：返回 (该由哪个 Agent 处理, 检索关键词列表)。失败回退默认 Agent。"""
    try:
        client, model = _resolve_llm(llm)
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": ROUTER_PROMPT + user_message}],
            temperature=0, max_tokens=48,
        )
        txt = (r.choices[0].message.content or "").strip()

        key = DEFAULT_AGENT
        for word, k in ROUTE_MAP.items():
            if word in txt:
                key = k
                break

        kws: list[str] = []
        if "|" in txt:
            tail = txt.split("|", 1)[1]
            for w in tail.replace("，", " ").replace(",", " ").replace("、", " ").split():
                w = w.strip(" 　|")
                if w:
                    kws.append(w)
        return key, kws[:4]
    except Exception:
        return DEFAULT_AGENT, []


def chat(user_message: str, history: list[dict], ctx: ToolContext,
         llm: dict | None = None, agent_key: str | None = None,
         skip_rag: bool = False, files: list[dict] | None = None) -> dict:
    """处理一条用户消息，返回 {reply, sources, tool_calls, agent, agent_name}。

    llm:       用户自选的模型配置 {provider, api_key, model}，为空则用服务端默认。
    agent_key: 指定用哪个智能体；为空则先路由判断。
    skip_rag:  不检索知识库。用于图片识别等「内容本身即资料」的场景。
    files:     用户上传并已解析的文件 [{name, text}]，拼成上下文块喂给模型。
    """
    if agent_key in AGENTS:
        key, extra_q = agent_key, []
    else:
        key, extra_q = route(user_message, llm)
    adef = AGENTS.get(key) or AGENTS[DEFAULT_AGENT]

    # 1) RAG 检索（多查询：原句 + 路由产出的关键词），把命中片段注入上下文
    hits = store.retrieve(user_message, extra_queries=extra_q) if not skip_rag else []
    rag_block = ""
    if hits:
        rag_block = "\n\n【校园资料】\n" + "\n---\n".join(
            f"[来源：{h['source']}]\n{h['text']}" for h in hits
        )

    # 2) 用户上传的文件（已在前端解析成文本），作为一等资料来源注入
    file_block, file_sources = files_mod.pack_for_prompt(files or [])

    messages = [{"role": "system", "content": adef["system"] + rag_block + file_block}]
    messages.extend(history[-6:])  # 只带最近几轮，控制 token
    messages.append({"role": "user", "content": user_message})

    client, model = _resolve_llm(llm)
    schemas = tool_schemas(adef["tools"])
    used_tools: list[dict] = []

    def _result(reply: str) -> dict:
        return {
            "reply": reply,
            "sources": file_sources + [{"source": h["source"], "score": h["score"]} for h in hits],
            "tool_calls": used_tools,
            "agent": key,
            "agent_name": adef["name"],
        }

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=schemas,
            temperature=0.3,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return _result(msg.content or "")

        # 执行模型请求的工具调用
        messages.append(msg.model_dump(exclude_none=True))
        for tc in msg.tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = run_tool(tc.function.name, ctx, args)
            used_tools.append({"name": tc.function.name, "args": args, "result": result})
            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result, ensure_ascii=False),
            })

    # 超过最大轮数仍未收敛，兜底再问一次（不带工具）
    final = client.chat.completions.create(
        model=model, messages=messages, temperature=0.3,
    )
    return _result(final.choices[0].message.content or "")
