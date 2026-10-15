"""全国高校名单：给「选择学校」用，选中后自动填官网地址。

数据在 app/data/universities.json（由 scripts/build_university_list.py 生成）：
2657 所高校，其中 582 所有官网地址；其余只有校名，选中后提示用户手填。

刻意不做的事：不下发、也不内置任何校徽图片。校徽体积太大（全量上百 MB），
小程序主包只有 2MB；而且批量打包分发别人的校徽也有版权问题。校徽一律
在用户同步时从学校官网抓取，抓到后由后端缓存，所有人共用。
"""
from __future__ import annotations

import io
import json
import os

_DATA: list[dict] | None = None
_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "universities.json")


def _load() -> list[dict]:
    global _DATA
    if _DATA is None:
        try:
            _DATA = json.load(io.open(_PATH, encoding="utf-8")).get("items", [])
        except Exception:
            _DATA = []      # 名单缺失不该让接口 500，退化成空列表
    return _DATA


def count() -> dict:
    items = _load()
    return {"total": len(items), "with_url": sum(1 for x in items if x.get("u"))}


def search(q: str = "", limit: int = 30) -> list[dict]:
    """按校名搜索。排序：完全匹配 > 开头匹配 > 包含；同样匹配程度时，
    有官网的排前面（选完能直接同步，体验更顺）。"""
    items = _load()
    q = (q or "").strip()

    if not q:
        # 没输关键词时给一批"有官网"的学校当起点
        return [x for x in items if x.get("u")][:limit]

    scored: list[tuple[int, str, dict]] = []
    for x in items:
        n = x.get("n", "")
        if q not in n:
            continue
        rank = 0 if n == q else (1 if n.startswith(q) else 2)
        if not x.get("u"):
            rank += 3          # 没官网的往后排
        scored.append((rank, n, x))
    scored.sort(key=lambda t: (t[0], len(t[1])))
    return [x for _, _, x in scored[:limit]]
