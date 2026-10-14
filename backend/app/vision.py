"""图像识别：把用户拍的照片交给多模态大模型，产出可直接用的结果。

前端「拍照」时先选用途，决定走哪条链路：

- ask    图片问答   → 多模态模型看图直接回答
- solve  拍题解题   → 先转写题干，再交给「刷题陪练」Agent 讲解
- notice 拍通知     → 先转写正文，再交给「日程提醒」Agent 抽时间点生成待办
- scores 拍成绩单   → 直接抽成结构化课程列表，回前端确认后写入本地成绩

识别用的多模态模型与问答用的文本模型分开配置：文本模型（如 DeepSeek）大多看不了图，
所以这里独立解析 vision_llm；用户没填则回落到服务端 .env 里的 VISION_* 配置。
"""
from __future__ import annotations

import json
import re

from openai import OpenAI

from app import agent, providers
from app.config import settings
from app.tools import ToolContext

MODES = ("ask", "solve", "notice", "scores")

# 各用途的默认提问（用户没打字时用）
DEFAULT_ASK = {
    "ask": "这张图里是什么？有哪些信息是我需要留意的？",
    "solve": "",      # 题干本身就是全部输入
    "notice": "",     # 通知正文就是全部输入
    "scores": "",
}

VISION_SYSTEM = "你是校园助手的识图模块。只依据图片内容作答，看不清就说看不清，不要猜。用中文，简洁，不要 emoji。"

# 转写：要求逐字抄录，避免模型顺手总结或补全
TRANSCRIBE_PROMPT = {
    "notice": """请把这张图片里的文字**逐字完整**抄写出来，保持原有顺序和分段。
要求：
- 只输出图片中真实出现的文字，不要总结、不要解释、不要补全看不清的内容
- 确实看不清的字用 □ 代替
- 如果是通知/公告，保留标题、正文、落款单位和日期""",
    "solve": """请把这张图片里的**题目完整转写**成文字。
要求：
- 题干、小题、选项、图表中的数据都要写出来
- 公式用文字写法表示（例如 x^2、根号(a+b)、a≥b）
- 只输出题目本身，不要解题、不要加任何说明""",
}

# 结构化抽取：只吐 JSON
SCORES_PROMPT = """这是一张成绩单或成绩查询截图。请提取其中的课程成绩，严格只输出 JSON，不要任何其他文字：
{"courses":[{"name":"课程名","credit":3.0,"score":88}]}

规则：
- credit 是学分，图上没有就填 0
- score 用百分制；若图上写的是等级，按 优秀=90 良好=82 中等=75 及格=62 不合格=50 换算
- 若写「合格/通过」记 60，「不合格/未通过」记 50
- 表头、合计、绩点、排名这类行不要当成课程
- 看不清课程名或分数的条目直接不要"""


def _client(vision_llm: dict | None) -> tuple[OpenAI, str]:
    """选识图用的多模态模型：用户自填的 key 优先，其次服务端 .env。"""
    if vision_llm and vision_llm.get("api_key"):
        base, model, _ = providers.resolve_vision(vision_llm.get("provider", ""),
                                                   vision_llm.get("model", ""))
        return OpenAI(api_key=vision_llm["api_key"], base_url=base), model
    if settings.vision_api_key:
        return (OpenAI(api_key=settings.vision_api_key, base_url=settings.vision_base_url),
                settings.vision_model)
    raise RuntimeError(
        "还没配置识图模型。请到「我的 → 大模型设置 → 识图模型」选一个多模态模型"
        "（推荐智谱 glm-4v-flash，有免费额度）并填入你自己的 API Key。"
    )


def _ask_image(image: str, prompt: str, vision_llm: dict | None,
               system: str = VISION_SYSTEM, max_tokens: int = 1200) -> str:
    """把图片 + 提示词发给多模态模型，返回文本。"""
    client, model = _client(vision_llm)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": image}},
            ]},
        ],
        temperature=0.2,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


def _parse_json(text: str) -> dict:
    """从模型输出里抠出 JSON（有的模型会裹 ```json 或加一句废话）。"""
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


# 图上写等级时的兜底换算（提示词里已要求模型换算，这里再保一层）。
# 按词长倒序匹配，避免「不及格」被「及格」先截走。
_LEVEL: dict[str, int] = {
    "优秀": 90, "良好": 82, "中等": 75, "及格": 62, "合格": 60, "通过": 60,
    "不及格": 50, "不合格": 50, "未通过": 50, "差": 45, "优": 90, "良": 82, "中": 75,
}
_LEVEL_KEYS = sorted(_LEVEL, key=len, reverse=True)


def _num(v: object, default: float = -1) -> float:
    """把「4 学分」「88 分」「优秀」这类写法转成数字，转不了给默认值。"""
    s = str(v).strip()
    for k in _LEVEL_KEYS:
        if k in s:
            return float(_LEVEL[k])
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else default


def _clean_courses(raw: object) -> list[dict]:
    """清洗抽出来的课程行：丢掉字段缺失/数值离谱的，同名去重。"""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for c in raw:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name", "")).strip()
        if not name or name in seen:
            continue
        credit = _num(c.get("credit", 0), 0)
        score = _num(c.get("score", ""), -1)
        if credit < 0 or credit > 30 or score < 0 or score > 150:
            continue
        seen.add(name)
        out.append({"name": name, "credit": round(credit, 1), "score": round(score, 1)})
    return out[:40]


def handle(image: str, mode: str, message: str, history: list[dict],
           ctx: ToolContext, llm: dict | None = None,
           vision_llm: dict | None = None) -> dict:
    """按用途处理一张图，返回给前端的统一结构。"""
    mode = mode if mode in MODES else "ask"
    question = (message or "").strip()
    out: dict = {"mode": mode, "ocr": "", "sources": [], "tool_calls": [],
                 "agent": "", "agent_name": ""}

    # ---------- 拍成绩单：只做结构化抽取，不进 Agent ----------
    if mode == "scores":
        txt = _ask_image(image, SCORES_PROMPT, vision_llm, max_tokens=1500)
        courses = _clean_courses(_parse_json(txt).get("courses"))
        out["courses"] = courses
        out["raw"] = "" if courses else txt[:300]
        out["reply"] = (f"识别出 {len(courses)} 门课程，确认后即可写入成绩页。"
                        if courses else
                        "这张图里没识别出课程成绩。请确认截的是成绩单，或换一张更清晰的图。")
        return out

    # ---------- 拍题 / 拍通知：先转写，再交给对应 Agent ----------
    if mode in TRANSCRIBE_PROMPT:
        text = _ask_image(image, TRANSCRIBE_PROMPT[mode], vision_llm, max_tokens=1800)
        out["ocr"] = text
        if not text:
            out["reply"] = "没能从这张图里读出文字。换一张更清晰、正对着拍的照片试试。"
            return out

        # 把识别出的文字一起交给智能体 —— 图片内容就是它这一步的资料
        if mode == "notice":
            ask = question or "把上面通知里的关键时间点整理成待办清单"
            res = agent.chat(f"【我拍的图片里识别出的文字】\n{text}\n\n{ask}",
                             history, ctx, llm=llm, agent_key="schedule", skip_rag=True)
        else:
            ask = question or "这道题该怎么解？先给我讲思路"
            res = agent.chat(f"【我拍的图片里识别出的题目】\n{text}\n\n{ask}",
                             history, ctx, llm=llm, agent_key="study", skip_rag=True)

        out.update({"reply": res["reply"], "sources": [{"source": "图片识别"}] + res["sources"],
                    "tool_calls": res["tool_calls"], "agent": res["agent"],
                    "agent_name": res["agent_name"]})
        return out

    # ---------- 图片问答：多模态模型直接看图回答 ----------
    prompt = question or DEFAULT_ASK["ask"]
    out["reply"] = _ask_image(image, prompt, vision_llm)
    out["agent"], out["agent_name"] = "vision", "识图"
    out["sources"] = [{"source": "你上传的图片"}]
    return out
