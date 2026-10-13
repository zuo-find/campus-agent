"""微信小程序登录。

标准流程：
  小程序 wx.login() 取临时 code
    → 本页 /auth/login 收到 code
    → 用 appid+secret 向微信 jscode2session 换 openid
    → 以 openid 建本地用户、签发简单会话 token 返回

降级：未配置 wx_appid/wx_secret 时走"游客模式"，用 code 派生一个稳定的
演示 openid，便于本地/测试号联调与答辩演示（不接触微信服务器）。
用户资料（头像昵称）由前端 getUserProfile 授权后随请求上报，存 SQLite。
"""
from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
from datetime import datetime

import httpx

from app.config import settings

_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users.db")

JSCODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"


def _conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    conn = sqlite3.connect(_DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                openid TEXT PRIMARY KEY,
                nickname TEXT DEFAULT '',
                avatar TEXT DEFAULT '',
                token TEXT,
                created_at TEXT,
                updated_at TEXT
            )
        """)


def _code2openid(code: str) -> tuple[str, bool]:
    """返回 (openid, is_real)。未配密钥或换取失败时降级为演示 openid。"""
    if settings.wx_appid and settings.wx_secret:
        try:
            with httpx.Client(timeout=10) as client:
                r = client.get(JSCODE2SESSION, params={
                    "appid": settings.wx_appid,
                    "secret": settings.wx_secret,
                    "js_code": code,
                    "grant_type": "authorization_code",
                })
                data = r.json()
            if "openid" in data:
                return data["openid"], True
            # 微信返回 errcode 时降级，避免演示中断
        except Exception:
            pass
    # 降级：用 code 派生稳定 openid（同一 code 得同一值，仅供演示）
    demo = "demo_" + hashlib.sha256(code.encode()).hexdigest()[:24]
    return demo, False


def login(code: str) -> dict:
    openid, is_real = _code2openid(code)
    token = secrets.token_hex(16)
    now = datetime.now().isoformat(timespec="seconds")
    with _conn() as c:
        row = c.execute("SELECT openid FROM users WHERE openid=?", (openid,)).fetchone()
        if row:
            c.execute("UPDATE users SET token=?, updated_at=? WHERE openid=?", (token, now, openid))
        else:
            c.execute(
                "INSERT INTO users(openid,token,created_at,updated_at) VALUES(?,?,?,?)",
                (openid, token, now, now),
            )
    return {"ok": True, "token": token, "openid": openid, "is_real": is_real}


def update_profile(token: str, nickname: str, avatar: str) -> dict:
    with _conn() as c:
        row = c.execute("SELECT openid FROM users WHERE token=?", (token,)).fetchone()
        if not row:
            return {"ok": False, "msg": "登录态失效，请重新登录"}
        c.execute(
            "UPDATE users SET nickname=?, avatar=?, updated_at=? WHERE token=?",
            (nickname, avatar, datetime.now().isoformat(timespec="seconds"), token),
        )
        return {"ok": True, "nickname": nickname, "avatar": avatar}


def get_user(token: str) -> dict:
    with _conn() as c:
        row = c.execute(
            "SELECT openid,nickname,avatar FROM users WHERE token=?", (token,)
        ).fetchone()
    if not row:
        return {"ok": False, "msg": "未登录"}
    return {"ok": True, **dict(row)}
