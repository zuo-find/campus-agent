"""上传文件解析：把用户发来的 PDF / Word / 纯文本读成文字，交给大模型。

小程序没有「选文件夹」的能力（平台限制），能做的是用 wx.chooseMessageFile
一次批量选多个文件，这里逐个解析。

长度上做了三层限制，防止一次塞爆模型上下文：
- 单文件 10MB（再大传不动，也没必要）
- 单文件取前 6000 字
- 一次提问带的文件总量 18000 字（超出按顺序截断，并在末尾说明）
"""
from __future__ import annotations

import io

MAX_BYTES = 10 * 1024 * 1024
MAX_CHARS_PER_FILE = 6000
MAX_CHARS_TOTAL = 18000

# 能直接按文本读的扩展名
TEXT_EXT = {
    ".txt", ".md", ".markdown", ".csv", ".json", ".log", ".ini", ".yml", ".yaml",
    ".py", ".js", ".ts", ".java", ".c", ".cpp", ".h", ".hpp", ".cs", ".go", ".rs",
    ".html", ".htm", ".css", ".xml", ".sql", ".sh", ".bat", ".tex",
}

# 明确告诉用户不支持的，比让它报"读取失败"清楚
UNSUPPORTED = {
    ".xlsx": "Excel 表格", ".xls": "Excel 表格", ".ppt": "PPT", ".pptx": "PPT",
    ".zip": "压缩包", ".rar": "压缩包", ".7z": "压缩包", ".mp4": "视频", ".mp3": "音频",
}


def _ext(name: str) -> str:
    i = name.rfind(".")
    return name[i:].lower() if i >= 0 else ""


def _read_pdf(raw: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(raw))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages)


def _read_docx(raw: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(raw))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    # 表格里的内容（课表、成绩单常见）也要，按行用竖线隔开
    for t in doc.tables:
        for row in t.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _read_text(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030"):     # 国内的老文件不少是 GBK
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


def parse(name: str, raw: bytes) -> dict:
    """解析一个文件，返回 {ok, name, kind, chars, text, msg}。"""
    name = (name or "未命名文件").strip()
    ext = _ext(name)

    if len(raw) > MAX_BYTES:
        return {"ok": False, "name": name, "msg": "文件超过 10MB，请压缩或拆分后再传"}

    if ext in UNSUPPORTED:
        return {"ok": False, "name": name,
                "msg": f"暂不支持{UNSUPPORTED[ext]}（{ext}）。可以转成 PDF 或 Word 再传"}

    try:
        if ext == ".pdf":
            text, kind = _read_pdf(raw), "pdf"
        elif ext == ".docx":
            text, kind = _read_docx(raw), "docx"
        elif ext == ".doc":
            return {"ok": False, "name": name,
                    "msg": "不支持老版 .doc，请用 Word 另存为 .docx 再传"}
        elif ext in TEXT_EXT or not ext:
            text, kind = _read_text(raw), "text"
        else:
            return {"ok": False, "name": name, "msg": f"暂不支持 {ext} 格式"}
    except Exception as e:
        # PDF 读不出来通常是扫描件（整页是图，没有文字层），这跟"文件坏了"不是一回事
        if ext == ".pdf":
            return {"ok": False, "name": name,
                    "msg": "这个 PDF 读不出文字，多半是扫描件或截图。"
                           "用问答页左边的相机拍它，走识图来读"}
        return {"ok": False, "name": name, "msg": f"读取失败：{str(e)[:80]}"}

    text = (text or "").strip()
    if not text:
        msg = ("这个 PDF 里没有文字，可能是扫描件或截图。"
               "用问答页左边的相机拍它，走识图来读。") if ext == ".pdf" else "文件里没有读到内容"
        return {"ok": False, "name": name, "msg": msg}

    note = ""
    if len(text) > MAX_CHARS_PER_FILE:
        text = text[:MAX_CHARS_PER_FILE]
        note = f"内容较长，只读取了前 {MAX_CHARS_PER_FILE} 字"

    return {"ok": True, "name": name, "kind": kind,
            "chars": len(text), "text": text, "note": note, "msg": ""}


def pack_for_prompt(items: list[dict]) -> tuple[str, list[dict]]:
    """把多个已解析的文件拼成给模型看的上下文块。

    返回 (文本块, 来源列表)。总量超过 MAX_CHARS_TOTAL 时按顺序截断，
    并在末尾说明还有哪些没带上，避免模型以为读全了。
    """
    if not items:
        return "", []

    parts: list[str] = []
    sources: list[dict] = []
    used = 0
    dropped: list[str] = []

    for it in items:
        name = (it.get("name") or "未命名文件").strip()
        text = (it.get("text") or "").strip()
        if not text:
            continue
        room = MAX_CHARS_TOTAL - used
        if room <= 200:                     # 剩下的填不下一个文件了
            dropped.append(name)
            continue
        piece = text[:room]
        used += len(piece)
        # 只带了一部分时必须说清楚，否则模型会以为读全了
        if len(piece) < len(text):
            piece += f"\n（该文件较长，这里只带了前 {len(piece)} 字）"
        parts.append(f"[文件：{name}]\n{piece}")
        sources.append({"source": "上传：" + name})

    block = ("\n\n【用户上传的文件】\n"
             "（以下是用户自己上传的文件内容，回答时优先依据它，"
             "并在回答里说明结论来自哪个文件；文件里没有的不要编）\n"
             + "\n---\n".join(parts))
    if dropped:
        block += "\n---\n（还有这些文件因为整体太长没有带上：" + "、".join(dropped) + "）"
    return block, sources
