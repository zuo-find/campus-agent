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

def gen_document(ctx: ToolContext, doc_type: str, fields: dict | None = None) -> dict:
    """生成校园事务材料初稿（模板填充）。

    由大模型把用户口语描述抽成结构化字段，再用模板渲染成正式材料；
    返回的 fields 供前端做成可编辑表单，确认后可导出 Word。
    """
    from app import documents
    r = documents.render(doc_type, fields or {})
    if not r.get("ok"):
        return r
    return {
        "ok": True,
        "doc_type": r["doc_type"],
        "title": r["title"],
        "text": r["text"],
        "fields": r["fields"],
        "note": "这是初稿。可在页面上修改字段后导出 Word。",
    }


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
    "gen_document": (gen_document, {
        "type": "function",
        "function": {
            "name": "gen_document",
            "description": (
                "生成校园事务材料初稿（模板填充）。当用户要写请假条、实训申请、活动策划、社团申报时调用。"
                "doc_type 只能是：请假条 / 实训申请 / 活动策划 / 社团申报。"
                "请从用户描述中抽取信息填入 fields（键用中文标签）；用户没提到的字段不要编造，留空即可。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_type": {
                        "type": "string",
                        "enum": ["请假条", "实训申请", "活动策划", "社团申报"],
                        "description": "材料类型",
                    },
                    "fields": {
                        "type": "object",
                        "description": (
                            "字段键值对，键用中文标签。例如请假条："
                            "{\"姓名\":\"张三\",\"请假事由\":\"感冒发烧\",\"请假天数\":\"2\",\"开始日期\":\"2026-11-05\"}"
                        ),
                    },
                },
                "required": ["doc_type"],
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


def tool_schemas(names: list[str] | None = None) -> list[dict]:
    """返回工具的 JSON Schema。names 为 None 时返回全部，否则只返回指定工具（供各 Agent 限定工具子集）。"""
    if names is None:
        return [schema for _, schema in TOOLS.values()]
    return [TOOLS[n][1] for n in names if n in TOOLS]


def run_tool(name: str, ctx: ToolContext, arguments: dict[str, Any]) -> dict:
    if name not in TOOLS:
        return {"ok": False, "msg": f"未知工具：{name}"}
    func, _ = TOOLS[name]
    try:
        return func(ctx, **arguments)
    except TypeError as e:
        return {"ok": False, "msg": f"工具参数错误：{e}"}
