"""校园事务材料模板库 + 渲染 + 导出。

流程：LLM 把用户口语描述抽成结构化字段(fields) → 本模块用模板渲染成正式材料文本
     → 前端展示字段供人工编辑 → 确认后导出为 .docx 下载。

模板可自行替换为学校真实格式：只改 TEMPLATES 里的 fields / body 即可。
"""
from __future__ import annotations

import os
import uuid
from datetime import date

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPORT_DIR = os.path.join(_BASE, "data", "exports")

_TODAY = date.today().isoformat()


def _f(label: str, hint: str = "", default: str = "") -> dict:
    return {"label": label, "hint": hint, "default": default}


TEMPLATES: dict[str, dict] = {
    "请假条": {
        "title": "请假条",
        "fields": [
            _f("姓名"), _f("班级"), _f("请假事由"), _f("开始日期"), _f("请假天数"),
            _f("去向"), _f("联系方式"), _f("审批人", default="辅导员"),
            _f("申请日期", default=_TODAY),
        ],
        "body": (
            "请假条\n\n"
            "尊敬的{审批人}：\n\n"
            "    您好！我是{班级}{姓名}，因{请假事由}，需自{开始日期}起请假{请假天数}天。\n"
            "    请假期间本人去向为{去向}，联系方式{联系方式}。本人承诺请假期间注意安全，"
            "返校后及时销假，并主动补齐所学内容。\n"
            "    恳请批准，谢谢！\n\n"
            "    此致\n敬礼！\n\n"
            "                                          请假人：{姓名}\n"
            "                                          日期：{申请日期}"
        ),
    },
    "实训申请": {
        "title": "学生实训（实习）申请审批表",
        "fields": [
            _f("姓名"), _f("学号"), _f("班级"), _f("专业"),
            _f("实训单位"), _f("实训岗位"), _f("起止时间"), _f("单位联系人及电话"),
            _f("申请理由"), _f("申请日期", default=_TODAY),
        ],
        "body": (
            "学生实训（实习）申请审批表\n\n"
            "一、申请人信息\n"
            "    姓名：{姓名}          学号：{学号}\n"
            "    班级：{班级}          专业：{专业}\n\n"
            "二、实训信息\n"
            "    实训单位：{实训单位}\n"
            "    实训岗位：{实训岗位}\n"
            "    起止时间：{起止时间}\n"
            "    单位联系人及电话：{单位联系人及电话}\n\n"
            "三、申请理由\n"
            "{申请理由}\n\n"
            "四、审批意见\n"
            "    指导教师意见：＿＿＿＿＿＿＿＿＿＿\n"
            "    院（系）意见：＿＿＿＿＿＿＿＿＿＿\n\n"
            "                                    申请人签名：{姓名}\n"
            "                                    申请日期：{申请日期}"
        ),
    },
    "活动策划": {
        "title": "活动策划书",
        "fields": [
            _f("活动名称"), _f("主办单位"), _f("承办单位"), _f("活动时间"), _f("活动地点"),
            _f("参与对象"), _f("活动目的"), _f("活动流程"), _f("经费预算"), _f("安全预案"),
            _f("申请日期", default=_TODAY),
        ],
        "body": (
            "{活动名称} 活动策划书\n\n"
            "一、活动背景与目的\n{活动目的}\n\n"
            "二、组织机构\n    主办单位：{主办单位}\n    承办单位：{承办单位}\n\n"
            "三、活动安排\n    活动时间：{活动时间}\n    活动地点：{活动地点}\n    参与对象：{参与对象}\n\n"
            "四、活动流程\n{活动流程}\n\n"
            "五、经费预算\n{经费预算}\n\n"
            "六、安全预案\n{安全预案}\n\n"
            "                                        申请日期：{申请日期}"
        ),
    },
    "社团申报": {
        "title": "学生社团成立申报书",
        "fields": [
            _f("社团名称"), _f("社团类别"), _f("发起人"), _f("社团宗旨"),
            _f("主要成员"), _f("活动计划"), _f("经费来源"), _f("指导单位"), _f("指导教师"),
            _f("申请日期", default=_TODAY),
        ],
        "body": (
            "学生社团成立申报书\n\n"
            "一、社团基本信息\n"
            "    社团名称：{社团名称}\n"
            "    社团类别：{社团类别}\n"
            "    发起人：{发起人}\n\n"
            "二、社团宗旨\n{社团宗旨}\n\n"
            "三、发起人及主要成员\n{主要成员}\n\n"
            "四、业务范围与活动计划\n{活动计划}\n\n"
            "五、经费来源\n{经费来源}\n\n"
            "六、指导单位与指导教师\n"
            "    指导单位：{指导单位}\n"
            "    指导教师：{指导教师}\n\n"
            "                                        申请日期：{申请日期}"
        ),
    },
}

BLANK = "＿＿＿＿＿＿"


def doc_types() -> list[str]:
    return list(TEMPLATES.keys())


def render(doc_type: str, fields: dict | None = None) -> dict:
    """把字段填进模板，返回 {ok,title,text,fields}。缺的字段渲染成空白线。"""
    tpl = TEMPLATES.get(doc_type)
    if not tpl:
        return {"ok": False, "msg": f"没有这种材料模板：{doc_type}（可选：{'/'.join(doc_types())}）",
                "types": doc_types()}

    fields = fields or {}
    # 归一化：允许 key 是字段名，忽略大小写/空格
    norm = {str(k).strip(): ("" if v is None else str(v)).strip() for k, v in fields.items()}

    values, out_fields = {}, []
    for spec in tpl["fields"]:
        label = spec["label"]
        val = norm.get(label, "") or spec.get("default", "")
        out_fields.append({"label": label, "value": val, "hint": spec.get("hint", "")})
        values[label] = val or BLANK

    text = tpl["body"]
    for k, v in values.items():
        text = text.replace("{" + k + "}", v)

    return {"ok": True, "doc_type": doc_type, "title": tpl["title"], "text": text, "fields": out_fields}


def export_docx(title: str, text: str) -> dict:
    """把材料文本导出为 .docx，返回可下载路径 /exports/xxx.docx。"""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.shared import Pt
    except ImportError:
        return {"ok": False, "msg": "服务器缺少 python-docx，请安装依赖"}

    os.makedirs(EXPORT_DIR, exist_ok=True)
    doc = Document()

    # 标题：居中加粗
    lines = (text or "").split("\n")
    head = (title or (lines[0] if lines else "材料")).strip()
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = h.add_run(head)
    run.bold = True
    run.font.size = Pt(16)

    # 正文：逐行写入
    body_lines = lines[1:] if lines and lines[0].strip() == head else lines
    for ln in body_lines:
        p = doc.add_paragraph(ln)
        p.paragraph_format.space_after = Pt(2)

    name = uuid.uuid4().hex + ".docx"
    path = os.path.join(EXPORT_DIR, name)
    doc.save(path)
    return {"ok": True, "url": "/exports/" + name, "filename": head + ".docx"}
