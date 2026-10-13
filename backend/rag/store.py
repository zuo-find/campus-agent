"""RAG 知识库：基于 Chroma 的校园文档检索。

设计要点：
- 文档切块后入库，检索返回 top-k 片段 + 来源文件名，供答辩"可解释、可溯源"。
- 默认用 Chroma 内置本地嵌入模型（all-MiniLM），零外部依赖即可跑通；
  若配置了远程 embedding，可在此替换为对应 embedding_function。
"""
from __future__ import annotations

import os
import re

import chromadb

from app.config import settings

_client: chromadb.ClientAPI | None = None
_collection = None


def _get_collection():
    global _client, _collection
    if _collection is None:
        os.makedirs(settings.chroma_dir, exist_ok=True)
        _client = chromadb.PersistentClient(path=settings.chroma_dir)
        _collection = _client.get_or_create_collection(
            name=settings.rag_collection,
            metadata={"hnsw:space": "cosine"},
        )
    return _collection


_HEAD = re.compile(r"(?=\n[ \t　]*[一二三四五六七八九十]+[、．.])")


def _split_fixed(text: str, size: int, overlap: int) -> list[str]:
    """长段落退化为按字符数切块（中文友好），带重叠以免切断语义。"""
    out, start = [], 0
    while start < len(text):
        piece = text[start:start + size].strip()
        if piece:
            out.append(piece)
        start += size - overlap
    return out


def chunk_text(text: str, size: int = 600, overlap: int = 80, max_len: int = 1800) -> list[str]:
    """切块：优先按小标题（一、二、……）分段，过长再按字符数切。

    通知类的赛程表若被固定字数切碎，检索时就很难整块命中，所以按标题分段更靠谱。
    """
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    parts = [p.strip() for p in _HEAD.split(text) if p.strip()]
    chunks: list[str] = []
    for p in parts:
        if len(p) <= max_len:
            chunks.append(p)
        else:
            chunks.extend(_split_fixed(p, size, overlap))
    return chunks


def reset() -> None:
    """清空整个知识库（重建索引时用）。"""
    global _client, _collection
    client = _client
    if client is None:
        os.makedirs(settings.chroma_dir, exist_ok=True)
        client = chromadb.PersistentClient(path=settings.chroma_dir)
        _client = client
    try:
        client.delete_collection(settings.rag_collection)
    except Exception:
        pass
    _collection = None


def add_document(doc_id: str, text: str, source: str) -> int:
    """把一篇文档切块入库，返回入库片段数。"""
    col = _get_collection()
    chunks = chunk_text(text)
    if not chunks:
        return 0
    col.add(
        ids=[f"{doc_id}::{i}" for i in range(len(chunks))],
        documents=chunks,
        metadatas=[{"source": source, "chunk": i} for i in range(len(chunks))],
    )
    return len(chunks)


_STOP = set("的了是在有和与或这那什么怎吗呢我你他她它们把被就都还也一个为对到从会能要需要请问下时候怎么如何帮我吧啊以及这个哪个")

# 空泛词：大模型有时会把"待办""关键时间点"这类词当检索词，它们没有检索价值
_META_KW = {"待办", "提醒", "关键时间点", "时间点", "时间安排", "信息", "内容", "整理",
            "安排", "关键", "相关", "问题", "要求", "事项", "详情", "具体"}

# 时间意图：提问涉及这些词时，含具体日期的片段会加权
_TIME_HINT = re.compile(r"什么时|时间|日期|截止|赛程|日程|报名|提交|几号|哪天|ddl")
_DATE_RE = re.compile(r"\d{1,2}\s*月\s*\d{1,2}\s*[日号]|\d{4}\s*年\s*\d{1,2}\s*月")


def _keywords(query: str, limit: int = 6) -> list[str]:
    """从提问里抽关键词片段，用于补充检索（长句会稀释向量相似度）。

    做法：取 2~3 字片段、滤掉含虚词的，再按"区分度"筛 ——
    在语料里出现过、但又不是满篇都有的词（如"挑战赛"满篇都是，会被剔除；
    "报名""作品提交"有区分度，会被留下）。
    """
    q = re.sub(r"[^一-鿿0-9]", "", query or "")
    cands: list[str] = re.findall(r"\d{1,4}[月年日号]|\d{1,2}/\d{1,2}", q)
    for size in (3, 2):
        for i in range(len(q) - size + 1):
            s = q[i:i + size]
            if any(c in _STOP for c in s):
                continue
            cands.append(s)

    seen, uniq = set(), []
    for c in cands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)

    col = _get_collection()
    total = max(col.count(), 1)
    cap = max(3, total // 3)          # 出现次数超过这个比例就算"没区分度"
    scored: list[tuple[int, str]] = []
    for c in uniq:
        try:
            n = len(col.get(where_document={"$contains": c}).get("ids", []))
        except Exception:
            continue
        if n == 0 or n > cap:
            continue
        scored.append((n, c))

    # 越罕见的关键词越有区分度，排在前面，其命中的片段也就越优先
    scored.sort(key=lambda x: x[0])
    return [c for _n, c in scored[:limit]]


def retrieve(query: str, top_k: int | None = None,
             extra_queries: list[str] | None = None) -> list[dict]:
    """混合检索，返回 [{text, source, score, by}]。

    - 多查询：长提问会把真正相关的片段挤出向量前列，所以除了原句，
      再用「报名时间」「作品提交」这类短关键词各检一遍，按片段取最高分合并。
    - 没给额外关键词时，退化为"关键词包含"兜底补充。
    """
    col = _get_collection()
    total = col.count()
    if total == 0:
        return []
    k = top_k or settings.rag_top_k

    best: dict[str, dict] = {}

    def _absorb(q: str, by: str) -> None:
        res = col.query(query_texts=[q], n_results=min(max(k, 8), total))
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        dists = res.get("distances", [[]])[0]
        for _id, doc, meta, dist in zip(ids, docs, metas, dists):
            sc = round(1 - dist, 3)
            cur = best.get(_id)
            if cur is None or sc > cur["score"]:
                best[_id] = {"text": doc, "source": meta.get("source", "未知"),
                             "score": sc, "by": by}

    extra = [x for x in (extra_queries or []) if x and x != query and x not in _META_KW]
    for q in [query] + extra:
        _absorb(q, "向量")

    # 时间意图：用户问"什么时候/截止/赛程"时，含具体日期的片段才是答案。
    # 这类片段常藏在通知的表格里、向量相似度不高，容易被挤出前列，
    # 所以只要知识库不大，就把含日期的片段一并纳入候选。
    if _TIME_HINT.search(query):
        for v in best.values():
            if _DATE_RE.search(v["text"]):
                v["score"] = round(v["score"] + 0.15, 3)
                v["by"] = "向量+日期"
        if total <= 200:
            try:
                allr = col.get()
            except Exception:
                allr = {}
            for _id, doc, meta in zip(allr.get("ids", []), allr.get("documents", []),
                                      allr.get("metadatas", [])):
                if _id not in best and _DATE_RE.search(doc or ""):
                    best[_id] = {"text": doc, "source": meta.get("source", "未知"),
                                 "score": 0.55, "by": "日期"}

    if not extra_queries:
        # 兜底：用"关键词包含"补充命中的片段
        hits: dict[str, list] = {}
        for kw in _keywords(query):
            try:
                r = col.get(where_document={"$contains": kw})
            except Exception:
                continue
            for _id, doc, meta in zip(r.get("ids", []), r.get("documents", []), r.get("metadatas", [])):
                if _id in best:
                    continue
                if _id not in hits:
                    hits[_id] = [doc, meta, 0]
                hits[_id][2] += 1
        for _id, (doc, meta, _cnt) in sorted(hits.items(), key=lambda kv: -kv[1][2])[:6]:
            best[_id] = {"text": doc, "source": meta.get("source", "未知"),
                         "score": 0.0, "by": "关键词"}

    out = sorted(best.values(), key=lambda x: -x["score"])
    return out[: k + 6]
