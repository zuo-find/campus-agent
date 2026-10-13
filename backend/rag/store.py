"""RAG 知识库：基于 Chroma 的校园文档检索。

设计要点：
- 文档切块后入库，检索返回 top-k 片段 + 来源文件名，供答辩"可解释、可溯源"。
- 默认用 Chroma 内置本地嵌入模型（all-MiniLM），零外部依赖即可跑通；
  若配置了远程 embedding，可在此替换为对应 embedding_function。
"""
from __future__ import annotations

import os

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


def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """按字符数切块（中文友好），带重叠以免切断语义。"""
    text = text.replace("\r\n", "\n")
    chunks, start = [], 0
    while start < len(text):
        chunk = text[start:start + size].strip()
        if chunk:
            chunks.append(chunk)
        start += size - overlap
    return chunks


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


def retrieve(query: str, top_k: int | None = None) -> list[dict]:
    """检索相关片段，返回 [{text, source, score}]。"""
    col = _get_collection()
    if col.count() == 0:
        return []
    res = col.query(query_texts=[query], n_results=top_k or settings.rag_top_k)
    out = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({"text": doc, "source": meta.get("source", "未知"), "score": round(1 - dist, 3)})
    return out
