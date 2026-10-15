"""把公开数据集整理成 app/data/universities.json（校名 + 官网 + 省份）。

数据来源（两个公开数据集，本脚本只做合并与清洗，不联网）：
  1. xioajiumi/Chinese_Universities 的 Chinese_Universities.json
     —— 582 所高校，含官方网址（软科排名数据）
  2. vczero/serverless-colleage 的 大学目录.json
     —— 2631 个校名（不含网址），用来补齐覆盖面

用法（先把上面两个文件下到任意目录）：
    python scripts/build_university_list.py <Chinese_Universities.json> <大学目录.json>

说明：教育部 2025 年名单共 3167 所，但不含官网地址，所以这里以"有官网的
582 所"为骨架，再用校名列表补全可搜索范围——没有官网的那些选中后会提示
用户自己填。
"""
from __future__ import annotations

import io
import json
import os
import re
import sys


def load_stream(path: str) -> list[dict]:
    """那个文件是一串首尾相连的 JSON 对象（}{ 直接相邻），不是标准 JSON。"""
    raw = io.open(path, encoding="utf-8", errors="replace").read()
    dec, i, out = json.JSONDecoder(), 0, []
    while i < len(raw):
        while i < len(raw) and raw[i] in " \r\n\t":
            i += 1
        if i >= len(raw):
            break
        try:
            obj, i = dec.raw_decode(raw, i)
            out.append(obj)
        except Exception:
            i += 1
    return out


def clean_url(u: str) -> str:
    u = (u or "").strip().split()[0] if (u or "").strip() else ""
    if not u:
        return ""
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u.rstrip("/") + "/"


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 1

    rows = load_stream(sys.argv[1])
    names = json.load(io.open(sys.argv[2], encoding="utf-8"))

    out: dict[str, dict] = {}
    for r in rows:
        n = (r.get("name") or "").strip()
        if not n:
            continue
        out[n] = {"n": n, "u": clean_url(r.get("link")), "p": (r.get("location") or "").strip()}

    # 手工补充：公开数据集没收录、但我们实际核实过官网的学校
    MANUAL = {
        "西安思源学院": "https://www.xasyu.cn/",
    }
    for n, u in MANUAL.items():
        out[n] = {"n": n, "u": clean_url(u), "p": ""}

    added = 0
    for n in names:
        n = (n or "").strip()
        if n and n not in out:
            out[n] = {"n": n, "u": "", "p": ""}
            added += 1

    items = sorted(out.values(), key=lambda x: x["n"])
    dst = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "data", "universities.json")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    json.dump({"source": "软科582所(含官网) + 大学目录2631所(仅校名)",
               "note": "u 为空表示暂未收录官网，需用户手填",
               "items": items},
              io.open(dst, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

    print("总条数:", len(items), "| 含官网:", sum(1 for x in items if x["u"]), "| 仅校名:", added)
    print("写出:", dst, os.path.getsize(dst), "字节")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
