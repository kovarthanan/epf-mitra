"""
EPF Mitra - test retrieval against the Chroma index.

Usage:
    python scripts/search.py "Can I withdraw PF partially if my employer has not paid?"
    python scripts/search.py                     # runs the built-in test questions
    python scripts/search.py -k 5 "pension claim help at PRO"
"""

import argparse
import sys

import chromadb
from chromadb.utils import embedding_functions

from build_index import MODEL, COLLECTION

TEST_QUESTIONS = [
    "Can I get part payment of my PF if my employer did not deposit contributions?",
    "Is Aadhaar seeding mandatory to file ECR?",
    "How do I de-link a wrong member ID from my UAN?",
    "What is the Centralised Pension Payment System?",
    "Do I need to upload a cancelled cheque for a PF claim?",
]


def search(col, q: str, k: int):
    res = col.query(query_texts=[q], n_results=k, include=["documents", "metadatas", "distances"])
    print(f"\n### {q}")
    for doc, meta, dist in zip(res["documents"][0], res["metadatas"][0], res["distances"][0]):
        score = 1 - dist
        ocr = " (OCR)" if meta.get("ocr") else ""
        print(f"\n  [{score:.3f}] {meta['title'][:80]}")
        print(f"          {meta['date'] or 'date n/a'} | {meta['division'] or '-'} | p.{meta['page_start']}{ocr}")
        print(f"          {doc[:220].replace(chr(10), ' ')}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("-k", type=int, default=3)
    ap.add_argument("--db", default="data/chroma")
    args = ap.parse_args()

    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL, device="cpu")
    col = chromadb.PersistentClient(path=args.db).get_collection(COLLECTION, embedding_function=ef)
    print(f"Index: {col.count()} chunks")

    questions = [" ".join(args.question)] if args.question else TEST_QUESTIONS
    for q in questions:
        search(col, q, args.k)


if __name__ == "__main__":
    sys.path.insert(0, "scripts")
    main()