"""批量把 data/docs/ 下的 txt/pdf/md 文档导入 RAG 知识库。

用法（在 backend 目录下）：
    python -I scripts/ingest.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag import store  # noqa: E402

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "docs")


def read_file(path: str) -> str:
    if path.lower().endswith(".pdf"):
        from pypdf import PdfReader
        reader = PdfReader(path)
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    with open(path, encoding="utf-8", errors="ignore") as f:
        return f.read()


def main():
    if not os.path.isdir(DOCS_DIR):
        print(f"目录不存在：{DOCS_DIR}")
        return
    total = 0
    for name in sorted(os.listdir(DOCS_DIR)):
        if name.startswith("."):
            continue
        path = os.path.join(DOCS_DIR, name)
        if not os.path.isfile(path):
            continue
        text = read_file(path)
        n = store.add_document(doc_id=name, text=text, source=name)
        total += n
        print(f"  + {name}: {n} 块")
    print(f"完成，共入库 {total} 个片段。")


if __name__ == "__main__":
    main()
