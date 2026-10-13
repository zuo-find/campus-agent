"""「生活」栏后端：天气穿衣、食堂推荐、失物招领。

- 天气：open-meteo 免费接口（无需密钥），再交给大模型给穿衣/带伞建议。
- 食堂推荐：内置示例菜单 + 大模型按口味/预算/天气推荐。
- 失物招领：SQLite 本地存储（Python 内置，无额外依赖），支持发布/查询/标记找到。
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime

import httpx

from app.config import settings

# 西安坐标（可按学校所在地调整）
CITY_LAT, CITY_LON, CITY_NAME = 34.34, 108.94, "西安"

_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "life.db")

# 示例食堂菜单（答辩可替换为真实菜单/价格）
CANTEEN_MENU = [
    {"name": "红烧牛肉面", "price": 12, "taste": "咸香", "type": "面食", "hot": True},
    {"name": "番茄鸡蛋盖饭", "price": 10, "taste": "酸甜", "type": "盖饭", "hot": True},
    {"name": "麻辣香锅", "price": 18, "taste": "麻辣", "type": "炒菜", "hot": True},
    {"name": "凉皮肉夹馍套餐", "price": 13, "taste": "酸辣", "type": "小吃", "hot": False},
    {"name": "小米粥+包子", "price": 7, "taste": "清淡", "type": "早餐", "hot": True},
    {"name": "黄焖鸡米饭", "price": 15, "taste": "咸鲜", "type": "盖饭", "hot": True},
    {"name": "酸辣粉", "price": 9, "taste": "酸辣", "type": "小吃", "hot": True},
    {"name": "水果沙拉", "price": 11, "taste": "清爽", "type": "轻食", "hot": False},
]


# ----------------------------------------------------------------- 数据库

def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS lost_found (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,            -- 'lost' 丢了 / 'found' 捡到
                title TEXT NOT NULL,
                location TEXT,
                contact TEXT,
                detail TEXT,
                status TEXT DEFAULT 'open',    -- 'open' / 'closed'
                created_at TEXT NOT NULL
            )
        """)


# ----------------------------------------------------------------- 天气

def get_weather() -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={CITY_LAT}&longitude={CITY_LON}"
        "&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        "&timezone=Asia/Shanghai&forecast_days=1"
    )
    with httpx.Client(timeout=10) as client:
        r = client.get(url)
        r.raise_for_status()
        d = r.json()
    cur, daily = d["current"], d["daily"]
    code = cur["weather_code"]
    return {
        "city": CITY_NAME,
        "temp": cur["temperature_2m"],
        "humidity": cur["relative_humidity_2m"],
        "wind": cur["wind_speed_10m"],
        "desc": _wmo_desc(code),
        "temp_max": daily["temperature_2m_max"][0],
        "temp_min": daily["temperature_2m_min"][0],
        "rain_prob": daily["precipitation_probability_max"][0],
    }


def _wmo_desc(code: int) -> str:
    m = {
        0: "晴", 1: "多云转晴", 2: "多云", 3: "阴",
        45: "雾", 48: "雾凇", 51: "小毛雨", 53: "毛雨", 55: "大毛雨",
        61: "小雨", 63: "中雨", 65: "大雨", 71: "小雪", 73: "中雪", 75: "大雪",
        80: "阵雨", 81: "强阵雨", 82: "暴雨", 95: "雷阵雨",
    }
    return m.get(code, "未知")


def _llm():
    from openai import OpenAI
    if not settings.llm_api_key:
        raise RuntimeError("未配置 LLM_API_KEY")
    return OpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


def weather_advice() -> dict:
    """取天气 + 让大模型给一句穿衣/带伞建议。"""
    w = get_weather()
    prompt = (
        f"现在{w['city']}天气：{w['desc']}，当前{w['temp']}℃，今天{w['temp_min']}~{w['temp_max']}℃，"
        f"降水概率{w['rain_prob']}%，湿度{w['humidity']}%。"
        "请用一句话（30字内）给大学生今天的穿衣和带伞建议，亲切口语化。"
    )
    try:
        resp = _llm().chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        advice = resp.choices[0].message.content.strip()
    except Exception:
        advice = "注意天气变化，适当增减衣物。" + ("记得带伞～" if w["rain_prob"] >= 40 else "")
    return {"weather": w, "advice": advice}


# ----------------------------------------------------------------- 食堂推荐

def recommend_meal(taste: str = "", budget: float = 0, meal: str = "午餐") -> dict:
    """根据口味/预算/餐段，让大模型从菜单里推荐 1-2 个。"""
    menu_str = "\n".join(
        f"- {m['name']}（{m['price']}元，{m['taste']}，{m['type']}）" for m in CANTEEN_MENU
    )
    cond = f"口味偏好：{taste or '不限'}；预算：{('≤'+str(budget)+'元') if budget else '不限'}；餐段：{meal}"
    prompt = (
        f"你是校园食堂推荐助手。现有菜单：\n{menu_str}\n\n"
        f"用户条件：{cond}。\n请从菜单里推荐 1-2 个最合适的，说明理由，30-60字，口语化。"
    )
    try:
        resp = _llm().chat.completions.create(
            model=settings.llm_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
        )
        text = resp.choices[0].message.content.strip()
    except Exception as e:
        text = f"推荐失败：{e}"
    return {"recommend": text, "menu": CANTEEN_MENU}


# ----------------------------------------------------------------- 失物招领

def add_lost_found(kind: str, title: str, location: str = "", contact: str = "", detail: str = "") -> dict:
    if kind not in ("lost", "found") or not title.strip():
        return {"ok": False, "msg": "参数错误"}
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO lost_found(kind,title,location,contact,detail,created_at) VALUES(?,?,?,?,?,?)",
            (kind, title.strip(), location, contact, detail, datetime.now().isoformat(timespec="minutes")),
        )
        return {"ok": True, "id": cur.lastrowid}


def list_lost_found(kind: str = "") -> dict:
    sql = "SELECT * FROM lost_found WHERE status='open'"
    params: list = []
    if kind in ("lost", "found"):
        sql += " AND kind=?"
        params.append(kind)
    sql += " ORDER BY id DESC LIMIT 100"
    with _conn() as c:
        rows = [dict(r) for r in c.execute(sql, params).fetchall()]
    return {"ok": True, "items": rows}


def close_lost_found(item_id: int) -> dict:
    with _conn() as c:
        c.execute("UPDATE lost_found SET status='closed' WHERE id=?", (item_id,))
    return {"ok": True}
