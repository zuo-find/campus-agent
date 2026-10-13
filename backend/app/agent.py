"""Agent 核心：一轮对话里，让大模型自行决定
  - 调用工具（查成绩/算绩点/请假条/ddl），还是
  - 基于 RAG 检索到的校园文档作答，还是
  - 直接回答。

实现方式：OpenAI 兼容的 function-calling 循环。先把 RAG 命中的文档片段
作为“资料”注入系统提示，再把 4 个工具的 schema 交给模型；模型可多轮调用
工具，最后产出自然语言回答。所有工具结果与引用来源一并返回前端，便于答辩溯源。
"""
from __future__ import annotations

import json

from openai import OpenAI

from app import providers
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


SYSTEM_PROMPT = """你是西安思源学院的「校园服务智能体」，帮助同学解答校园制度、办事流程问题，并能调用工具查成绩、算绩点、生成请假条、整理 ddl。

规则：
1. 涉及学校制度、流程、规定的问题，优先依据【校园资料】中的内容回答，并在回答末尾用「来源：xxx」标注依据的文件；资料中没有的，明确说"资料里没找到，建议咨询教务老师"，不要编造。
2. 涉及成绩、绩点、请假、ddl 的操作，调用对应工具，不要凭空捏造数据。
3. 回答简洁、口语化，像学长学姐一样亲切。"""

MAX_TOOL_ROUNDS = 4


def chat(user_message: str, history: list[dict], ctx: ToolContext,
         llm: dict | None = None) -> dict:
    """处理一条用户消息，返回 {reply, sources, tool_calls}。

    llm: 用户自选的模型配置 {provider, api_key, model}，为空则用服务端默认。
    """
    # 1) RAG 检索，把命中片段注入上下文
    hits = store.retrieve(user_message)
    rag_block = ""
    if hits:
        rag_block = "\n\n【校园资料】\n" + "\n---\n".join(
            f"[来源：{h['source']}]\n{h['text']}" for h in hits
        )

    messages = [{"role": "system", "content": SYSTEM_PROMPT + rag_block}]
    messages.extend(history[-6:])  # 只带最近几轮，控制 token
    messages.append({"role": "user", "content": user_message})

    client, model = _resolve_llm(llm)
    used_tools: list[dict] = []

    for _ in range(MAX_TOOL_ROUNDS):
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tool_schemas(),
            temperature=0.3,
        )
        msg = resp.choices[0].message

        if not msg.tool_calls:
            return {
                "reply": msg.content or "",
                "sources": [{"source": h["source"], "score": h["score"]} for h in hits],
                "tool_calls": used_tools,
            }

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
    return {
        "reply": final.choices[0].message.content or "",
        "sources": [{"source": h["source"], "score": h["score"]} for h in hits],
        "tool_calls": used_tools,
    }
