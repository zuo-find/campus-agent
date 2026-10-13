"""Agent 可调用的工具集合。

每个工具 = 一个纯函数 + 一份 JSON Schema（供大模型 function calling 识别）。
工具保持无状态、可单测；成绩等数据由前端随请求传入（见 ToolContext），
不依赖爬取教务系统，落地合规、答辩可解释。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Any, Callable


@dataclass
class ToolContext:
    """单次对话携带的用户上下文（由前端传入，后端不持久化隐私数据）。"""
    courses: list[dict] = field(default_factory=list)   # [{name, credit, score}]
    ddls: list[dict] = field(default_factory=list)      # [{title, due}]
    user_name: str = "同学"


# ---------------------------------------------------------------- 绩点换算

def _score_to_gpa(score: float) -> float:
    """百分制 → 4.0 绩点（常见的 5 分段线性档，可按学校规则替换）。"""
    if score >= 90: return 4.0
    if score >= 85: return 3.7
    if score >= 82: return 3.3
    if score >= 78: return 3.0
    if score >= 75: return 2.7
    if score >= 72: return 2.3
    if score >= 68: return 2.0
    if score >= 64: return 1.5
    if score >= 60: return 1.0
    return 0.0


def calc_gpa(ctx: ToolContext) -> dict:
    """根据用户已录入的课程成绩计算加权平均绩点与加权平均分。"""
    courses = [c for c in ctx.courses if c.get("score") is not None and c.get("credit")]
    if not courses:
        return {"ok": False, "msg": "还没有录入成绩，请先到『成绩』页录入课程、学分和分数。"}
    total_credit = sum(float(c["credit"]) for c in courses)
    gpa = sum(_score_to_gpa(float(c["score"])) * float(c["credit"]) for c in courses) / total_credit
    avg = sum(float(c["score"]) * float(c["credit"]) for c in courses) / total_credit
    failed = [c["name"] for c in courses if float(c["score"]) < 60]
    return {
        "ok": True,
        "gpa": round(gpa, 3),
        "weighted_avg": round(avg, 2),
        "total_credit": total_credit,
        "course_count": len(courses),
        "failed_courses": failed,
    }


def query_scores(ctx: ToolContext, keyword: str | None = None) -> dict:
    """查询已录入的成绩；可按课程名关键词过滤。"""
    courses = ctx.courses
    if keyword:
        courses = [c for c in courses if keyword in c.get("name", "")]
    if not courses:
        return {"ok": False, "msg": "没有匹配的课程成绩。"}
    return {"ok": True, "courses": courses}


# ---------------------------------------------------------------- 请假条

def gen_leave_note(ctx: ToolContext, reason: str, days: int,
                   start_date: str | None = None) -> dict:
    """生成一份请假条草稿文本，供用户修改后使用。"""
    start = start_date or date.today().isoformat()
    note = (
        f"请假条\n\n"
        f"尊敬的老师：\n"
        f"    您好！我是{ctx.user_name}，因{reason}，"
        f"需自{start}起请假{days}天，望批准。请假期间我会主动了解并补齐所学内容。\n\n"
        f"    此致\n敬礼！\n\n"
        f"请假人：{ctx.user_name}\n日期：{date.today().isoformat()}"
    )
    return {"ok": True, "draft": note, "note": "这是草稿，请根据实际情况修改后使用。"}


# ---------------------------------------------------------------- DDL 提醒

def list_ddls(ctx: ToolContext) -> dict:
    """列出未完成的 ddl，按截止时间升序，并标注剩余天数。"""
    today = date.today()
    items = []
    for d in ctx.ddls:
        try:
            due = datetime.fromisoformat(d["due"]).date()
            items.append({"title": d["title"], "due": d["due"], "days_left": (due - today).days})
        except (KeyError, ValueError):
            continue
    items.sort(key=lambda x: x["days_left"])
    if not items:
        return {"ok": False, "msg": "目前没有记录任何 ddl。"}
    return {"ok": True, "ddls": items}


# ---------------------------------------------------------------- 注册表

# 工具名 -> (函数, function-calling schema)
TOOLS: dict[str, tuple[Callable[..., dict], dict]] = {
    "calc_gpa": (calc_gpa, {
        "type": "function",
        "function": {
            "name": "calc_gpa",
            "description": "计算用户的加权平均绩点(GPA)和加权平均分。当用户问绩点、GPA、平均分、排名预估相关问题时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }),
    "query_scores": (query_scores, {
        "type": "function",
        "function": {
            "name": "query_scores",
            "description": "查询用户已录入的课程成绩，可按课程名关键词过滤。当用户问某门课考多少分、我的成绩等问题时调用。",
            "parameters": {
                "type": "object",
                "properties": {"keyword": {"type": "string", "description": "课程名关键词，可选"}},
                "required": [],
            },
        },
    }),
    "gen_leave_note": (gen_leave_note, {
        "type": "function",
        "function": {
            "name": "gen_leave_note",
            "description": "生成请假条草稿。当用户想请假、要请假条时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "请假原因"},
                    "days": {"type": "integer", "description": "请假天数"},
                    "start_date": {"type": "string", "description": "起始日期 YYYY-MM-DD，可选，默认今天"},
                },
                "required": ["reason", "days"],
            },
        },
    }),
    "list_ddls": (list_ddls, {
        "type": "function",
        "function": {
            "name": "list_ddls",
            "description": "列出用户未完成的 ddl（作业/考试截止时间），按紧急程度排序。当用户问还有什么作业、哪些快截止了、我的 ddl 时调用。",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    }),
}


def tool_schemas() -> list[dict]:
    return [schema for _, schema in TOOLS.values()]


def run_tool(name: str, ctx: ToolContext, arguments: dict[str, Any]) -> dict:
    if name not in TOOLS:
        return {"ok": False, "msg": f"未知工具：{name}"}
    func, _ = TOOLS[name]
    try:
        return func(ctx, **arguments)
    except TypeError as e:
        return {"ok": False, "msg": f"工具参数错误：{e}"}
