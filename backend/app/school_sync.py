"""学校官网信息同步：抓取指定网址 → 提取正文 → 大模型抽取结构化条目 → 入库。

为什么不让小程序直接抓：
    小程序的 wx.request 只能请求已备案的 https 白名单域名，也不能解析 HTML。
    所以由后端代抓，小程序只负责「配置网址 + 展示结果」。

为什么用大模型抽取而不是写死选择器：
    各校官网页面结构千差万别，写死 CSS 选择器换个学校就失效；
    抓正文交给大模型抽取，通用性好得多（抽取结果不保证 100% 准确，需人工核对）。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx

from app.config import settings

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_BASE, "data", "school.db")

# 允许同步的类别（与前端展示的卡片对应）
CATEGORIES = ["校历", "作息", "通知公告"]

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"


# ------------------------------------------------------------------ 存储

def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    c = sqlite3.connect(_DB)
    c.row_factory = sqlite3.Row
    return c


def _ensure_col(table: str, col: str, typ: str) -> None:
    with _conn() as c:
        cols = [r[1] for r in c.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")


def init_db() -> None:
    with _conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS school_sources (
            category TEXT PRIMARY KEY, url TEXT, synced_at TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS school_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT, title TEXT, date TEXT, content TEXT,
            source_url TEXT, synced_at TEXT)""")
    _ensure_col("school_sources", "logo", "TEXT")   # 学校 logo 的本地路径
    _ensure_col("school_sources", "name", "TEXT")   # 学校名称（取自网页标题）


def list_sources() -> dict:
    with _conn() as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM school_sources").fetchall()]
    return {"ok": True, "sources": rows, "categories": CATEGORIES}


def set_source(category: str, url: str) -> dict:
    if category not in CATEGORIES:
        return {"ok": False, "msg": f"类别只能是：{'/'.join(CATEGORIES)}"}
    url = (url or "").strip()
    if not re.match(r"^https?://", url, re.I):
        return {"ok": False, "msg": "网址要以 http:// 或 https:// 开头"}
    with _conn() as c:
        c.execute("INSERT INTO school_sources(category,url) VALUES(?,?) "
                  "ON CONFLICT(category) DO UPDATE SET url=excluded.url", (category, url))
    return {"ok": True, "category": category, "url": url}


def get_items(category: str = "") -> dict:
    sql = "SELECT * FROM school_items"
    params: list = []
    if category:
        sql += " WHERE category=?"
        params.append(category)
    sql += " ORDER BY id DESC LIMIT 200"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    return {"ok": True, "items": rows, "categories": CATEGORIES}


# ------------------------------------------------------------------ 抓取

class _TextExtractor(HTMLParser):
    """把 HTML 转成纯文本（stdlib，不额外引依赖）。"""

    SKIP = {"script", "style", "noscript", "svg"}
    BREAK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "td", "section", "article"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip += 1
        elif tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        t = (data or "").strip()
        if t:
            self.parts.append(t)

    def text(self, limit: int = 8000) -> str:
        s = "".join(self.parts)
        s = re.sub(r"[ \t\xa0　]+", " ", s)
        s = re.sub(r"\n\s*\n+", "\n", s)
        return s.strip()[:limit]


_IMG_RE = re.compile(r"<img[^>]+>", re.I)
_ATTR_RE = re.compile(r"(src|href|alt|class|id|property|content)\s*=\s*[\"']([^\"']*)[\"']", re.I)
_LINK_RE = re.compile(r"<link[^>]+>", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


def _attrs(tag: str) -> dict:
    return {k.lower(): v for k, v in _ATTR_RE.findall(tag)}


def find_logo(html: str, base: str) -> str:
    """从网页里找一个像学校 logo 的图片地址（尽量返回绝对地址）。"""
    # 1) og:image 最像宣传图
    for tag in _LINK_RE.findall(html) + re.findall(r"<meta[^>]+>", html, re.I):
        a = _attrs(tag)
        if a.get("property", "").lower() == "og:image" and a.get("content"):
            return urljoin(base, a["content"])
    # 2) <img> 的 src/alt/class/id 里带 logo 的
    for tag in _IMG_RE.findall(html):
        a = _attrs(tag)
        blob = " ".join([a.get("src", ""), a.get("alt", ""), a.get("class", ""), a.get("id", "")]).lower()
        if "logo" in blob and a.get("src"):
            return urljoin(base, a["src"])
    # 3) 站点图标
    for tag in _LINK_RE.findall(html):
        a = _attrs(tag)
        if "icon" in a.get("rel", "").lower() and a.get("href"):
            return urljoin(base, a["href"])
    return ""


def find_title(html: str) -> str:
    m = _TITLE_RE.search(html)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    # 标题常是「XXX大学-首页」这类，去掉后缀
    return re.split(r"[-_|·—]", t)[0].strip()[:40] or t[:40]


def save_logo(url: str, category: str) -> str:
    """把 logo 图片下载到本地并返回可访问路径（存本地，避免 http 图片在小程序真机加载不了）。"""
    from app.market import UPLOAD_DIR
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with httpx.Client(timeout=15, follow_redirects=True, trust_env=False,
                      headers={"User-Agent": UA}) as cli:
        r = cli.get(url)
        r.raise_for_status()
        data = r.content
    if not data or len(data) > 3 * 1024 * 1024:
        return ""
    ct = (r.headers.get("content-type") or "").lower()
    low = url.lower()
    if "png" in ct or low.endswith(".png"):
        ext = ".png"
    elif "jpeg" in ct or "jpg" in ct or re.search(r"\.jpe?g$", low):
        ext = ".jpg"
    elif "gif" in ct:
        ext = ".gif"
    elif "webp" in ct:
        ext = ".webp"
    else:
        ext = ".png"
    name = f"school_logo_{category}{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    return "/uploads/" + name


def fetch_text(url: str, limit: int = 8000) -> str:
    # trust_env=False：不读取系统代理环境变量。
    # 服务器抓公开网页应当直连，否则会被本机代理拦掉（尤其是本地/内网地址）。
    with httpx.Client(timeout=20, follow_redirects=True, trust_env=False,
                      headers={"User-Agent": UA}) as cli:
        r = cli.get(url)
        r.raise_for_status()
        html = r.text
    p = _TextExtractor()
    p.feed(html)
    return p.text(limit)


# ------------------------------------------------------------------ 抽取

EXTRACT_PROMPT = """下面是一所学校官网页面的正文。请从中抽取与「{cat}」有关的信息条目。

要求：
- 只输出 JSON，不要任何解释文字。
- 格式：{{"items":[{{"title":"条目标题","date":"日期(没有就留空)","content":"要点，一句话"}}]}}
- 最多 20 条；按日期先后或重要性排列；正文里没有相关信息的，items 返回空数组。
- 不要编造正文里没有的内容。

正文：
{text}"""


def _llm_extract(cat: str, text: str) -> list[dict]:
    from openai import OpenAI
    if not settings.llm_api_key:
        raise RuntimeError("后端未配置 LLM_API_KEY，无法抽取")
    client = OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)
    resp = client.chat.completions.create(
        model=settings.llm_model,
        messages=[{"role": "user", "content": EXTRACT_PROMPT.format(cat=cat, text=text)}],
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        data = json.loads(raw)
    except Exception:
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0)) if m else {}
    items = data.get("items") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        out.append({
            "title": title[:120],
            "date": str(it.get("date") or "").strip()[:40],
            "content": str(it.get("content") or "").strip()[:300],
        })
    return out


def sync(category: str = "") -> dict:
    """抓取并同步一个或全部类别的网址。"""
    cats = [category] if category else CATEGORIES
    with _conn() as c:
        srcs = {r["category"]: r["url"] for r in c.execute("SELECT * FROM school_sources").fetchall()}

    done, failed = [], []
    for cat in cats:
        url = srcs.get(cat)
        if not url:
            continue
        try:
            # 抓原始 HTML：正文给大模型抽取，同时从中找学校 logo 与名称
            with httpx.Client(timeout=20, follow_redirects=True, trust_env=False,
                              headers={"User-Agent": UA}) as cli:
                resp = cli.get(url)
                resp.raise_for_status()
                html = resp.text

            p = _TextExtractor()
            p.feed(html)
            text = p.text(8000)
            if len(text) < 50:
                failed.append({"category": cat, "msg": "页面正文为空（可能是 JS 渲染的页面，抓不到内容）"})
                continue

            # 学校 logo / 名称（失败不影响主流程）
            name = find_title(html)
            logo = ""
            logo_src = find_logo(html, url)
            if logo_src:
                try:
                    logo = save_logo(logo_src, cat)
                except Exception:
                    logo = ""

            items = _llm_extract(cat, text)
            now = datetime.now().isoformat(timespec="minutes")
            with _conn() as c:
                c.execute("DELETE FROM school_items WHERE category=?", (cat,))
                c.executemany(
                    "INSERT INTO school_items(category,title,date,content,source_url,synced_at) "
                    "VALUES(?,?,?,?,?,?)",
                    [(cat, it["title"], it["date"], it["content"], url, now) for it in items],
                )
                c.execute("UPDATE school_sources SET synced_at=?, logo=COALESCE(NULLIF(?,''),logo), "
                          "name=COALESCE(NULLIF(?,''),name) WHERE category=?",
                          (now, logo, name, cat))
            done.append({"category": cat, "count": len(items), "logo": logo, "name": name})
        except Exception as e:
            failed.append({"category": cat, "msg": str(e)[:160]})

    return {"ok": True, "synced": done, "failed": failed}
