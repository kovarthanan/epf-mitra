"""
EPF Mitra - hybrid retrieval: BM25 + vector search, fused with reciprocal rank fusion,
mild recency boost, optional FlashRank re-ranking, one chunk per document.

Usage:
    python rag/retrieve.py                           # built-in test questions
    python rag/retrieve.py "Form 121 TDS declaration"
    python rag/retrieve.py --no-rerank "..."         # skip FlashRank (faster)
    python rag/retrieve.py --compare "..."           # vector-only vs hybrid side by side
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions
from rank_bm25 import BM25Okapi

sys.path.insert(0, str(Path(__file__).parent))
from build_index import MODEL, COLLECTION  # noqa: E402

CHUNKS_PATH = Path("data/chunks.jsonl")
DB_PATH = "data/chroma"
RRF_K = 60            # standard constant for reciprocal rank fusion
CANDIDATES = 30       # how many to pull from each retriever before fusing
RECENCY_WEIGHT = 0.3  # 0 = ignore dates; 0.3 = newest docs get up to +30% on fused score
YEAR_MIN, YEAR_MAX = 2006, 2026

TEST_QUESTIONS = [
    "Can I get part payment of my PF if my employer did not deposit contributions?",
    "Is Aadhaar seeding mandatory to file ECR?",
    "How do I de-link a wrong member ID from my UAN?",
    "What is the Centralised Pension Payment System?",
    "Do I need to upload a cancelled cheque for a PF claim?",
]


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class Retriever:
    def __init__(self, rerank: bool = True):
        t0 = time.time()
        rows = [json.loads(l) for l in CHUNKS_PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
        self.chunks = {r["chunk_id"]: r for r in rows}
        self.ids = [r["chunk_id"] for r in rows]
        self.bm25 = BM25Okapi([tokenize(f"{r['title']} {r['text']}") for r in rows])

        ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=MODEL, device="cpu")
        self.col = chromadb.PersistentClient(path=DB_PATH).get_collection(COLLECTION, embedding_function=ef)

        self.ranker = None
        if rerank:
            from flashrank import Ranker
            self.ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="data/flashrank")
        print(f"Retriever ready: {len(rows)} chunks, rerank={'on' if rerank else 'off'} ({time.time()-t0:.1f}s)")

    # --- individual retrievers -------------------------------------------------
    def vector(self, q: str, n: int = CANDIDATES) -> list[str]:
        res = self.col.query(query_texts=[q], n_results=n, include=[])
        return res["ids"][0]

    def keyword(self, q: str, n: int = CANDIDATES) -> list[str]:
        scores = self.bm25.get_scores(tokenize(q))
        top = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n]
        return [self.ids[i] for i in top if scores[i] > 0]

    # --- fusion ------------------------------------------------------------------
    def fuse(self, *ranked_lists: list[str]) -> dict[str, float]:
        fused: dict[str, float] = {}
        for lst in ranked_lists:
            for rank, cid in enumerate(lst):
                fused[cid] = fused.get(cid, 0.0) + 1.0 / (RRF_K + rank + 1)
        if RECENCY_WEIGHT:
            for cid in fused:
                y = self.chunks[cid].get("year") or YEAR_MIN
                y = min(max(y, YEAR_MIN), YEAR_MAX)
                fused[cid] *= 1 + RECENCY_WEIGHT * (y - YEAR_MIN) / (YEAR_MAX - YEAR_MIN)
        return fused

    def dedupe(self, cids: list[str], k: int) -> list[str]:
        seen, out = set(), []
        for cid in cids:
            d = self.chunks[cid]["doc_id"]
            if d in seen:
                continue
            seen.add(d); out.append(cid)
            if len(out) == k:
                break
        return out

    # --- public API ----------------------------------------------------------------
    def search(self, q: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        if mode == "vector":
            order = self.vector(q)
        elif mode == "keyword":
            order = self.keyword(q)
        else:
            fused = self.fuse(self.vector(q), self.keyword(q))
            order = sorted(fused, key=fused.get, reverse=True)

        if self.ranker and mode == "hybrid":
            from flashrank import RerankRequest
            cand = order[:20]
            req = RerankRequest(query=q, passages=[
                {"id": c, "text": f"{self.chunks[c]['title']} ({self.chunks[c].get('date') or 'n.d.'})\n{self.chunks[c]['text'][:1200]}"}
                for c in cand])
            order = [r["id"] for r in self.ranker.rerank(req)] + order[20:]

        return [self._hit(c, i) for i, c in enumerate(self.dedupe(order, k), 1)]

    def _hit(self, cid: str, rank: int) -> dict:
        c = self.chunks[cid]
        return {
            "rank": rank, "chunk_id": cid, "doc_id": c["doc_id"], "title": c["title"],
            "url": c["url"], "date": c.get("date"), "year": c.get("year"),
            "division": c.get("division"), "page_start": c["page_start"], "page_end": c["page_end"],
            "ocr": bool(c.get("ocr")), "text": c["text"],
        }


def show(hits: list[dict]):
    for h in hits:
        ocr = " (OCR)" if h["ocr"] else ""
        print(f"  {h['rank']}. {h['title'][:78]}")
        print(f"     {h['date'] or 'n.d.'} | {h['division'] or '-'} | p.{h['page_start']}{ocr}")
        print(f"     {h['text'][:160].replace(chr(10), ' ')}…")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--no-rerank", action="store_true")
    ap.add_argument("--compare", action="store_true", help="show vector-only then hybrid")
    args = ap.parse_args()

    r = Retriever(rerank=not args.no_rerank)
    qs = [" ".join(args.question)] if args.question else TEST_QUESTIONS
    for q in qs:
        print(f"\n### {q}")
        if args.compare:
            print(" [vector only]")
            show(r.search(q, args.k, mode="vector"))
            print(" [hybrid + rerank]")
        t0 = time.time()
        hits = r.search(q, args.k)
        show(hits)
        print(f"     ({(time.time()-t0)*1000:.0f} ms)")


if __name__ == "__main__":
    main()