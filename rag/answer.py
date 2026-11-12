"""
EPF Mitra - answer a question from retrieved EPFO circulars, with citations.

Usage:
    python rag/answer.py "Can I get part payment of my PF if my employer did not deposit contributions?"
    python rag/answer.py                 # runs the built-in test questions
    python rag/answer.py -k 6 --model gpt-4o-mini "..."

Needs OPENAI_API_KEY in .env. Logs every query to data/query_log.jsonl (question, sources,
tokens, cost) so cost per query can be tracked.
"""

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).parent))
from retrieve import Retriever, TEST_QUESTIONS  # noqa: E402

load_dotenv()
client = OpenAI()

# USD per 1M tokens (gpt-4o-mini, Nov 2026 list price; update if it changes)
PRICE = {"gpt-4o-mini": (0.15, 0.60)}
USD_INR = float(os.getenv("USD_INR", "88"))
LOG_PATH = Path("data/query_log.jsonl")

SYSTEM = """You are EPF Mitra, an assistant that answers questions about India's Employees' Provident Fund (EPF), Employees' Pension Scheme (EPS) and EDLI using ONLY the official EPFO documents provided as numbered sources.

Rules:
1. Answer only from the sources. Do not use outside knowledge. If the sources do not answer the question, say: "I couldn't find this in the EPFO documents I have." and suggest what the user could check on epfo.gov.in.
2. Cite every factual claim with the source number in square brackets, e.g. [1]. A sentence may cite more than one source: [1][3].
3. Each source has a date. When sources conflict or show a rule changing over time, prefer the most recent one and say so briefly, e.g. "This was extended to June 2024 [2], and no further extensions were granted from December 2025 [4]."
3b. Before writing, identify the MOST RECENT source relevant to the question and base your answer on it. Older sources are context only. If an older source is 5+ years older than the newest one, it may describe a different or superseded system: do not merge them; mention it as history, if at all.
4. Mention the date of the rule you rely on at least once, so the user knows how current it is.
5. Be concise: 3-6 sentences for a simple question, short bullet points if there are steps or conditions. Plain English, no legal jargon unless you explain it.
6. Never give personal financial or legal advice. Describe what the rule says; the user decides.
7. End with one line: "Note: This is not official EPFO advice. Verify with your regional PF office."
"""


def build_prompt(question: str, hits: list[dict]) -> str:
    parts = []
    # newest first: models weight early context more, and rule 3b asks for the most recent source
    for h in sorted(hits, key=lambda h: h["date"] or "0000", reverse=True):
        date = h["date"] or "date not available"
        ocr = " (text from OCR; may contain errors)" if h["ocr"] else ""
        parts.append(f"[{h['rank']}] {h['title']}\nDate: {date} | Division: {h['division'] or 'n/a'} | Page {h['page_start']}{ocr}\n{h['text']}")
    sources = "\n\n".join(parts)
    return f"Sources (newest first):\n\n{sources}\n\nQuestion: {question}\n\nAnswer with citations:"


def cost_inr(model: str, usage) -> float:
    pin, pout = PRICE.get(model, (0, 0))
    usd = usage.prompt_tokens / 1e6 * pin + usage.completion_tokens / 1e6 * pout
    return round(usd * USD_INR, 4)


def answer(retriever: Retriever, question: str, k: int = 5, model: str = "gpt-4o-mini") -> dict:
    t0 = time.time()
    hits = retriever.search(question, k=k)
    t_retrieve = time.time() - t0

    resp = client.chat.completions.create(
        model=model, temperature=0,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": build_prompt(question, hits)}],
    )
    text = resp.choices[0].message.content.strip()
    usage = resp.usage
    cited = sorted({int(n) for n in re.findall(r"\[(\d+)\]", text)})
    result = {
        "question": question,
        "answer": text,
        "sources": [{k2: h[k2] for k2 in ("rank", "title", "date", "division", "page_start", "url", "ocr")} for h in hits],
        "cited": cited,
        "model": model,
        "tokens": {"prompt": usage.prompt_tokens, "completion": usage.completion_tokens},
        "cost_inr": cost_inr(model, usage),
        "latency_s": {"retrieve": round(t_retrieve, 2), "total": round(time.time() - t0, 2)},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    LOG_PATH.parent.mkdir(exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(result, ensure_ascii=False) + "\n")
    return result


def show(r: dict):
    print(f"\n### {r['question']}\n")
    print(r["answer"])
    print("\nSources:")
    for s in r["sources"]:
        mark = "*" if s["rank"] in r["cited"] else " "
        ocr = " (OCR)" if s["ocr"] else ""
        print(f" {mark}[{s['rank']}] {s['title'][:80]} — {s['date'] or 'n.d.'}, p.{s['page_start']}{ocr}")
        print(f"      {s['url']}")
    t = r["tokens"]
    print(f"\n{t['prompt']} in + {t['completion']} out tokens = ₹{r['cost_inr']:.3f} | "
          f"retrieve {r['latency_s']['retrieve']}s, total {r['latency_s']['total']}s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("question", nargs="*")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--model", default="gpt-4o-mini")
    ap.add_argument("--no-rerank", action="store_true")
    args = ap.parse_args()

    retriever = Retriever(rerank=not args.no_rerank)
    qs = [" ".join(args.question)] if args.question else TEST_QUESTIONS
    total = 0.0
    for q in qs:
        r = answer(retriever, q, k=args.k, model=args.model)
        show(r); total += r["cost_inr"]
    if len(qs) > 1:
        print(f"\nTotal for {len(qs)} questions: ₹{total:.3f}")


if __name__ == "__main__":
    main()