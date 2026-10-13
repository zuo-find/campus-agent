"""校园二手市场（借鉴闲鱼模式）：图片 + 价格 + 分类的闲置交易。

数据存 SQLite；图片上传后存本地 uploads 目录，通过 /uploads 静态托管。
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB = os.path.join(_BASE, "data", "market.db")
UPLOAD_DIR = os.path.join(_BASE, "data", "uploads")

CATEGORIES = ["教材书籍", "数码电子", "生活用品", "服饰鞋包", "运动户外", "其他"]

# 各分类的占位色（无图时用）
CAT_COLOR = {
    "教材书籍": "#4a9bff", "数码电子": "#7c3aed", "生活用品": "#10b981",
    "服饰鞋包": "#ec4899", "运动户外": "#ff8a00", "其他": "#64748b",
}


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS market_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                orig_price REAL,
                category TEXT,
                detail TEXT,
                images TEXT,            -- JSON 数组，存 /uploads/xxx 路径
                contact TEXT,
                status TEXT DEFAULT 'on',   -- on 在售 / sold 已售
                created_at TEXT NOT NULL
            )
        """)


# ------------------------------------------------------------------ 图片

_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def save_image(data: bytes, filename: str) -> str:
    """保存上传图片，返回可访问路径 /uploads/xxx。"""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp"):
        ext = ".jpg"
    name = uuid.uuid4().hex + ext
    with open(os.path.join(UPLOAD_DIR, _SAFE.sub("", name)), "wb") as f:
        f.write(data)
    return "/uploads/" + name


# ------------------------------------------------------------------ 数据

def _row_to_item(r: sqlite3.Row) -> dict:
    d = dict(r)
    try:
        d["images"] = json.loads(d.get("images") or "[]")
    except Exception:
        d["images"] = []
    d["cover"] = d["images"][0] if d["images"] else ""
    d["catColor"] = CAT_COLOR.get(d.get("category") or "", "#64748b")
    return d


def add_item(title: str, price: float, orig_price: float | None = None,
             category: str = "", detail: str = "", images: list[str] | None = None,
             contact: str = "") -> dict:
    if not title.strip():
        return {"ok": False, "msg": "标题不能为空"}
    try:
        price = float(price)
    except (TypeError, ValueError):
        return {"ok": False, "msg": "价格格式不对"}
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO market_items(title,price,orig_price,category,detail,images,contact,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (title.strip(), price, orig_price, category, detail,
             json.dumps(images or [], ensure_ascii=False), contact,
             datetime.now().isoformat(timespec="minutes")),
        )
        return {"ok": True, "id": cur.lastrowid}


def list_items(category: str = "", include_sold: bool = True) -> dict:
    sql = "SELECT * FROM market_items WHERE 1=1"
    params: list = []
    if category and category in CATEGORIES:
        sql += " AND category=?"
        params.append(category)
    if not include_sold:
        sql += " AND status='on'"
    sql += " ORDER BY id DESC LIMIT 200"
    with _conn() as c:
        rows = [_row_to_item(r) for r in c.execute(sql, params).fetchall()]
    return {"ok": True, "items": rows, "categories": CATEGORIES}


def get_item(item_id: int) -> dict:
    with _conn() as c:
        r = c.execute("SELECT * FROM market_items WHERE id=?", (item_id,)).fetchone()
    if not r:
        return {"ok": False, "msg": "商品不存在"}
    return {"ok": True, "item": _row_to_item(r)}


def mark_sold(item_id: int) -> dict:
    with _conn() as c:
        c.execute("UPDATE market_items SET status='sold' WHERE id=?", (item_id,))
    return {"ok": True}
