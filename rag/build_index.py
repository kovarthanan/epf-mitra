"""
EPF Mitra - embed chunks into a local Chroma vector DB.

Uses a local embedding model (no API cost), so the demo stays cheap on the VPS.

Usage:
    pip install chromadb sentence-transformers
    python scripts/build_index.py                 # (re)index data/chunks.jsonl
    python scripts/build_index.py --reset         # wipe and rebuild
"""

import argparse
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

MODEL = "BAAI/bge-small-en-v1.5"   # 33M params, strong for retrieval, runs on CPU
COLLECTION = "epf_circulars"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", default="data/chunks.jsonl")
    ap.add_argument("--db", default="data/chroma")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--docs", help="file with doc_ids (one per line): delete their chunks, then re-add")
    args = ap.parse_args()

    client = chromadb.PersistentClient(path=args.db)
    if args.reset:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL, device="cpu")
    col = client.get_or_create_collection(COLLECTION, embedding_function=ef,
                                          metadata={"hnsw:space": "cosine"})

    rows = [json.loads(l) for l in Path(args.chunks).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.docs:
        doc_ids = [d.strip() for d in Path(args.docs).read_text(encoding="utf-8").splitlines() if d.strip()]
        for d in doc_ids:
            col.delete(where={"doc_id": d})
        print(f"Deleted chunks of {len(doc_ids)} docs; re-adding from chunks.jsonl")
    existing = set(col.get(include=[])["ids"]) if col.count() else set()
    todo = [r for r in rows if r["chunk_id"] not in existing]
    print(f"{len(rows)} chunks in file, {len(existing)} already indexed, {len(todo)} to add")

    for i in range(0, len(todo), args.batch):
        batch = todo[i:i + args.batch]
        col.add(
            ids=[r["chunk_id"] for r in batch],
            documents=[f"{r['title']} ({r.get('date') or 'n.d.'})\n\n{r['text']}" for r in batch],
            metadatas=[{
                "doc_id": r["doc_id"], "title": r["title"][:200], "url": r["url"],
                "date": r.get("date") or "", "year": r.get("year") or 0,
                "division": r.get("division") or "", "source_type": r.get("source_type") or "",
                "page_start": r["page_start"], "page_end": r["page_end"], "ocr": bool(r.get("ocr")),
            } for r in batch],
        )
        print(f"  indexed {min(i + args.batch, len(todo))}/{len(todo)}")
    print(f"Done. Collection '{COLLECTION}' now has {col.count()} chunks at {args.db}")


if __name__ == "__main__":
    main()