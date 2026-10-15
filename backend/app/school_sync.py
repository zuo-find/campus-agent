"""学校官网信息同步：抓取指定网址 → 提取正文 → 大模型抽取结构化条目 → 入库。

为什么不让小程序直接抓：
    小程序的 wx.request 只能请求已备案的 https 白名单域名，也不能解析 HTML。
    所以由后端代抓，小程序只负责「配置网址 + 展示结果」。

为什么用大模型抽取而不是写死选择器：
    各校官网页面结构千差万别，写死 CSS 选择器换个学校就失效；
    抓正文交给大模型抽取，通用性好得多（抽取结果不保证 100% 准确，需人工核对）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_BASE, "data", "school.db")

# 允许同步的类别（与前端展示的卡片对应）
CATEGORIES = ["校历", "作息", "通知公告", "成绩规则"]

# 类别 → 文件名用的 ASCII 短名（URL 里不能出现中文）
_SLUG = {"校历": "xiaoli", "作息": "zuoxi", "通知公告": "notice", "成绩规则": "chengji"}

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"

# 校徽缓存：按「网站域名」记，而不是按学校——同一个站点的不同栏目共用一张校徽，
# 而且预热脚本提前抓过的，用户同步时就能直接命中，不用现场再抓一遍。
_LOGO_CACHE_PATH = os.path.join(_BASE, "data", "school_logo_cache.json")


def _logo_cache() -> dict:
    try:
        return json.load(open(_LOGO_CACHE_PATH, encoding="utf-8"))
    except Exception:
        return {}


def put_logo_cache(host: str, path: str, light: bool, name: str = "") -> None:
    if not host or not path:
        return
    d = _logo_cache()
    d[host] = {"path": path, "light": 1 if light else 0, "name": name}
    os.makedirs(os.path.dirname(_LOGO_CACHE_PATH), exist_ok=True)
    json.dump(d, open(_LOGO_CACHE_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


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
    _ensure_col("school_sources", "logo", "TEXT")        # 学校 logo 的本地路径
    _ensure_col("school_sources", "name", "TEXT")        # 学校名称（取自网页标题）
    _ensure_col("school_sources", "logo_light", "INTEGER")  # logo 是否为浅色(白 logo 需深色底)


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


_A_RE = re.compile(r"<a\s[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)

# 每类内容在官网上通常挂在哪些栏目下（用于"这页没内容时"给用户推荐子页面）
_KW = {
    "校历": ["校历", "学期", "教学安排", "日历", "开课"],
    "作息": ["作息", "上课时间", "课表", "时间安排"],
    "通知公告": ["通知", "公告", "新闻", "动态"],
    "成绩规则": ["教务", "教学", "学籍", "成绩", "规章", "制度", "学分", "绩点", "考试",
                 "培养方案", "管理办法", "规定", "办法", "细则"],
}


def _same_site(url: str, base: str) -> bool:
    """两个地址是不是同一个站（允许 www. 与子域名之间互跳）。"""
    a = urlparse(url).netloc.lower().split(":")[0]
    b = urlparse(base).netloc.lower().split(":")[0]
    if not a or not b:
        return False
    a = a[4:] if a.startswith("www.") else a
    b = b[4:] if b.startswith("www.") else b
    return a == b or a.endswith("." + b) or b.endswith("." + a)


def find_links(html: str, base: str, category: str, limit: int = 6) -> list[dict]:
    """从页面里挑出与类别相关的下钻链接（用户填了首页/栏目页时给建议）。

    只收同一个站点的链接：页面里往往夹着抖音、公众号之类的推广外链，
    它们的标题偶尔也会命中关键词，拿来做"相关栏目"建议会莫名其妙。
    """
    kws = _KW.get(category) or []
    out, seen = [], set()
    for href, inner in _A_RE.findall(html or ""):
        text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", inner or "")).strip()
        if not text or len(text) > 24:
            continue
        if not any(k in text for k in kws):
            continue
        url = urljoin(base, href)
        if url in seen or url.rstrip("/") == base.rstrip("/"):
            continue
        if not _same_site(url, base):
            continue
        seen.add(url)
        out.append({"text": text, "url": url})
        if len(out) >= limit:
            break
    return out


def find_title(html: str) -> str:
    m = _TITLE_RE.search(html)
    if not m:
        return ""
    t = re.sub(r"\s+", " ", m.group(1)).strip()
    # 标题常是「XXX大学-首页」这类，去掉后缀
    return re.split(r"[-_|·—]", t)[0].strip()[:40] or t[:40]


def _png_mean_luma(data: bytes) -> float | None:
    """粗略算出 PNG 不透明像素的平均亮度(0~255)，用于判断 logo 是深色还是浅色。

    只处理 8 位 RGB/RGBA、且尺寸不大的图；其他情况返回 None（跳过判断）。
    纯 stdlib 实现，不引额外依赖。
    """
    import zlib
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    pos, w, h, bd, ct = 8, 0, 0, None, None
    idat = bytearray()
    while pos + 8 <= len(data):
        ln = int.from_bytes(data[pos:pos + 4], "big")
        typ = data[pos + 4:pos + 8]
        chunk = data[pos + 8:pos + 8 + ln]
        if typ == b"IHDR":
            w = int.from_bytes(chunk[0:4], "big")
            h = int.from_bytes(chunk[4:8], "big")
            bd, ct = chunk[8], chunk[9]
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
        pos += 12 + ln
    if bd != 8 or ct not in (2, 6) or not w or not h or w * h > 600000:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except Exception:
        return None

    bpp = 4 if ct == 6 else 3
    stride = w * bpp
    prev = bytearray(stride)
    total, cnt, p, y = 0.0, 0, 0, 0
    step = max(1, w // 60)
    while y < h and p + 1 + stride <= len(raw) + stride:
        f = raw[p]; p += 1
        if p + stride > len(raw):
            break
        line = bytearray(raw[p:p + stride]); p += stride
        if f == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif f == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif f == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        for x in range(0, w, step):
            o = x * bpp
            a = line[o + 3] if bpp == 4 else 255
            if a > 40:
                total += 0.299 * line[o] + 0.587 * line[o + 1] + 0.114 * line[o + 2]
                cnt += 1
        prev = line
        y += 1
    return (total / cnt) if cnt else None


# 位图的魔数。判断格式必须看内容，不能看 URL 后缀或 content-type——
# 有的学校把 logo 做成 .svg（里面再包一张位图），按后缀存就会存出一个坏文件，
# 小程序 <image> 加载不了，界面上就只剩一个"校"字。
_RASTER_MAGIC = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)


def _raster_ext(data: bytes) -> str:
    for magic, ext in _RASTER_MAGIC:
        if data.startswith(magic):
            return ext
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ""


# 带内容指纹的校徽路径（新命名）。不带指纹的旧路径一律不认，触发重新下载。
_HASHED_LOGO = re.compile(r"^/uploads/school_logo_.+_[0-9a-f]{8}\.(png|jpe?g|gif|webp)$")

# SVG 里内嵌的位图：<image xlink:href="data:image/png;base64,....">
_EMBEDDED_RASTER = re.compile(
    rb"data:image/(?:png|jpe?g|gif|webp);base64,([A-Za-z0-9+/=\s]+)", re.I)


def _unwrap_svg(data: bytes) -> bytes:
    """把 SVG 外壳里包的位图抠出来。

    小程序的 <image> 不认 SVG，但不少学校的 logo 是「SVG 壳 + 内嵌 base64 位图」，
    这种能救；纯矢量的 SVG 救不了，只能放弃（前端会退回校名首字）。"""
    if b"<svg" not in data[:300].lower():
        return b""
    m = _EMBEDDED_RASTER.search(data)
    if not m:
        return b""
    try:
        raw = base64.b64decode(re.sub(rb"\s+", b"", m.group(1)))
    except Exception:
        return b""
    return raw if _raster_ext(raw) else b""


def _drop_old_logos(slug: str, keep: str) -> None:
    """同一个 slug 只保留最新那张，清掉历史文件（都是本模块自己生成的缓存图）。"""
    from app.market import UPLOAD_DIR
    prefix = "school_logo_" + slug
    try:
        for f in os.listdir(UPLOAD_DIR):
            if f == keep or not f.startswith(prefix):
                continue
            # 前缀之后必须是 _ 或 . —— 否则 slug「xiaoli」会误删「xiaoli2」的文件
            if f[len(prefix):][:1] in ("_", "."):
                os.remove(os.path.join(UPLOAD_DIR, f))
    except Exception:
        pass      # 清理失败不影响本次保存


def save_logo(url: str, category: str) -> tuple[str, bool]:
    """把 logo 图片下载到本地并返回可访问路径（存本地，避免 http 图片在小程序真机加载不了）。"""
    from app.market import UPLOAD_DIR
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with httpx.Client(timeout=15, follow_redirects=True, trust_env=False,
                      headers={"User-Agent": UA}) as cli:
        r = cli.get(url)
        r.raise_for_status()
        data = r.content
    if not data or len(data) > 3 * 1024 * 1024:
        return "", False

    # 按真实内容定格式；拿到 SVG 就尝试把里面内嵌的位图抠出来
    ext = _raster_ext(data)
    if not ext:
        data = _unwrap_svg(data)
        ext = _raster_ext(data) if data else ""
    if not ext:
        return "", False      # 小程序显示不了的格式，宁可不存，让前端退回首字

    # 文件名必须是纯 ASCII：URL 里出现中文会让 <image> 取不到图（服务端 404）。
    # 末尾带 8 位内容指纹：图片内容一变，文件名跟着变 —— 小程序的图片缓存是按
    # URL 命中的，固定文件名会让它一直显示旧图（换学校后校徽和校名对不上就是这原因）。
    slug = _SLUG.get(category) or ("c" + hashlib.md5(category.encode("utf-8")).hexdigest()[:8])
    digest = hashlib.md5(data).hexdigest()[:8]
    name = f"school_logo_{slug}_{digest}{ext}"
    _drop_old_logos(slug, name)
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)

    # 判断是不是"白色 logo"（官网深色导航栏常见）：白 logo 放白底上会看不见，
    # 前端据此换成深色底。判断不出来时按深色处理（白底展示）。
    luma = _png_mean_luma(data)
    is_light = bool(luma is not None and luma > 205)
    return "/uploads/" + name, is_light


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
- 若类别是「成绩规则」：抽取绩点/学分绩点计算办法、成绩等级划分、补考重修、奖学金评定等规则要点。

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
            logo, logo_light = "", 0
            # 先查预热缓存：同一个域名抓过一次就不再抓（预热脚本提前跑过就直接命中）。
            # 只认带内容指纹的路径 —— 早期缓存存的是不带指纹的固定文件名，
            # 那种路径内容变了 URL 却没变，客户端的图片缓存会一直显示旧图
            host = urlparse(url).netloc.lower()
            cached = _logo_cache().get(host)
            if cached and _HASHED_LOGO.match(cached.get("path") or ""):
                logo = cached["path"]
                logo_light = int(cached.get("light") or 0)
            else:
                logo_src = find_logo(html, url)
                if logo_src:
                    try:
                        logo, is_light = save_logo(logo_src, cat)
                        logo_light = 1 if is_light else 0
                        if logo:
                            put_logo_cache(host, logo, is_light, name)
                    except Exception:
                        logo, logo_light = "", 0

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
                          "name=COALESCE(NULLIF(?,''),name), logo_light=? WHERE category=?",
                          (now, logo, name, logo_light, cat))
            # 一条都没抽到，多半是填了首页/栏目页（只有链接没有正文）：
            # 顺手把这个页面里相关的下钻链接捞出来，给用户当"下一步该填什么"的建议
            suggest = find_links(html, url, cat) if not items else []
            done.append({"category": cat, "count": len(items), "logo": logo,
                         "name": name, "logo_light": logo_light, "suggest": suggest})
        except Exception as e:
            failed.append({"category": cat, "msg": str(e)[:160]})

    return {"ok": True, "synced": done, "failed": failed}
