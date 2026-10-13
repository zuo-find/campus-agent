"""Agent 可调用的工具集合。

每个工具 = 一个纯函数 + 一份 JSON Schema（供大模型 function calling 识别）。
工具保持无状态、可单测；成绩等数据由前端随请求传入（见 ToolContext），
不依赖爬取教务系统，落地合规、答辩可解释。
"""
from __future__ import annotations

import re
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


# ---------------------------------------------------------------- 日程 / 待办

_DATE_YMD = re.compile(r"(\d{4})\s*[-/年.]\s*(\d{1,2})\s*[-/月.]\s*(\d{1,2})")
_DATE_MD = re.compile(r"(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
_DATE_SLASH = re.compile(r"(?<!\d)(\d{1,2})\s*[/-]\s*(\d{1,2})(?!\d)")


def _parse_date(s: str | None):
    """尽量容错地解析日期：2026-11-30 / 2026年11月30日 / 11月30日 / 11/30。"""
    if not s:
        return None
    s = str(s).strip()
    year = date.today().year
    m = _DATE_YMD.search(s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = _DATE_MD.search(s) or _DATE_SLASH.search(s)
    if m:
        try:
            return date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    return None


def gen_todos(ctx: ToolContext, items: list | None = None) -> dict:
    """把从通知/资料里提取到的关键时间点整理成一份待办清单。"""
    today = date.today()
    out: list[dict] = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or it.get("事项") or it.get("name") or "").strip()
        if not title:
            continue
        raw_due = str(it.get("due") or it.get("截止") or it.get("日期") or it.get("date") or "").strip()
        note = str(it.get("note") or it.get("说明") or "").strip()
        d = _parse_date(raw_due)
        days = (d - today).days if d else None
        if days is None:
            days_text, urgent = "", False
        elif days < 0:
            days_text, urgent = "已过", False
        elif days == 0:
            days_text, urgent = "今天", True
        else:
            days_text, urgent = f"还有{days}天", days <= 7
        out.append({
            "title": title,
            "due": d.isoformat() if d else raw_due,
            "due_text": f"{d.month}月{d.day}日" if d else (raw_due or "待确认"),
            "days_left": days,
            "days_text": days_text,
            "urgent": urgent,
            "note": note,
        })
    out.sort(key=lambda x: (x["days_left"] is None,
                            x["days_left"] if x["days_left"] is not None else 0))
    return {
        "ok": bool(out),
        "today": today.isoformat(),
        "todos": out,
        "msg": "" if out else "没有提取到明确时间点。",
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
    "gen_todos": (gen_todos, {
        "type": "function",
        "function": {
            "name": "gen_todos",
            "description": (
                "把从通知/资料中提取到的关键时间点整理成待办清单。"
                "当用户问报名时间、赛程、材料提交截止、比赛安排，或要求'帮我整理提醒/待办'时调用。"
                "请依据【校园资料】中的真实日期填入，不要编造；资料里没有的日期不要写。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "关键时间点列表",
                        "items": {
                            "type": "object",
                            "properties": {
                                "title": {"type": "string", "description": "事项，如 报名、作品提交"},
                                "due": {"type": "string", "description": "日期，如 2026-11-30 或 11月30日"},
                                "note": {"type": "string", "description": "补充说明（可选），如 24:00截止"},
                            },
                            "required": ["title"],
                        },
                    },
                },
                "required": ["items"],
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
