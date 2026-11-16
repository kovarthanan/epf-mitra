"""
EPF Mitra - regression eval over eval/questions.jsonl.

For every question it runs the real pipeline (retrieve -> LLM answer) and checks:
  retrieved  : an expected source document is in the top-k results          (retrieval quality)
  cited      : the answer cites an expected source document                 (grounding)
  keyword    : the answer contains an expected fact, e.g. "8.25"            (correctness)
  dated      : the answer mentions a year, i.e. the date of the rule        (freshness rule)
  refused    : out-of-scope questions get "I couldn't find..." + no citation (no hallucination)
A question PASSES when every check that applies to it passes.

Retrieved chunk texts are saved too, so RAGAS can score the same run later.

Usage (from the project root):
    python eval/run_eval.py                    # all 30 questions (~Rs 1 with gpt-4o-mini)
    python eval/run_eval.py --only rate_current trap_car
    python eval/run_eval.py --repeat 3         # 3 runs: average pass rate + flaky questions

LLM answers vary slightly between runs even at temperature 0, so one run can mislead.
With --repeat, a question is "stable" if it passed every run and "flaky" if it passed some.
"""

import argparse
import json
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rag"))

import answer as answer_mod  # noqa: E402
from retrieve import Retriever  # noqa: E402

QUESTIONS = ROOT / "eval" / "questions.jsonl"
OUT_DIR = ROOT / "eval" / "results"
NOT_FOUND = "couldn't find"
YEAR = re.compile(r"\b(19|20)\d{2}\b")


class CapturingRetriever:
    """Wraps the real retriever so we can keep the exact chunks the LLM saw (needed for RAGAS)."""

    def __init__(self, inner: Retriever):
        self.inner, self.last = inner, []

    def search(self, q, k=5, mode="hybrid"):
        self.last = self.inner.search(q, k=k, mode=mode)
        return self.last


def any_in(needles: list[str], hay: str) -> bool:
    hay = hay.lower()
    return any(n.lower() in hay for n in needles)


def grade(q: dict, r: dict) -> dict:
    ans = r["answer"]
    titles = [s["title"] for s in r["sources"]]
    cited_titles = [s["title"] for s in r["sources"] if s["rank"] in r["cited"]]
    checks: dict[str, bool] = {}

    if q["out_of_scope"]:
        checks["refused"] = NOT_FOUND in ans.lower() and not r["cited"]
    else:
        if q["expected_sources"]:
            checks["retrieved"] = any(any_in(q["expected_sources"], t) for t in titles)
            checks["cited"] = any(any_in(q["expected_sources"], t) for t in cited_titles)
        if q["expected_any"]:
            checks["keyword"] = any_in(q["expected_any"], ans)
        if q["category"] != "trap":
            checks["dated"] = bool(YEAR.search(ans))
    return {"checks": checks, "passed": all(checks.values())}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", help="question ids to run")
    ap.add_argument("-k", type=int, default=5)
    ap.add_argument("--repeat", type=int, default=1, help="run the whole set N times")
    args = ap.parse_args()

    qs = [json.loads(l) for l in QUESTIONS.read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.only:
        qs = [q for q in qs if q["id"] in set(args.only)]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    answer_mod.LOG_PATH = OUT_DIR / "query_log_eval.jsonl"  # keep eval traffic out of the real query log
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_path = OUT_DIR / f"run-{stamp}.jsonl"

    retriever = CapturingRetriever(Retriever(rerank=True))
    rows, t0 = [], time.time()
    for run in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\n=== run {run}/{args.repeat} ===")
        for i, q in enumerate(qs, 1):
            r = answer_mod.answer(retriever, q["question"], k=args.k)
            g = grade(q, r)
            row = {**q, **g, "run": run, "answer": r["answer"], "cited": r["cited"],
                   "sources": [{"rank": s["rank"], "title": s["title"], "date": s["date"]} for s in r["sources"]],
                   "contexts": [h["text"] for h in retriever.last],
                   "cost_inr": r["cost_inr"], "latency_s": r["latency_s"]["total"]}
            rows.append(row)
            failed = [c for c, ok in g["checks"].items() if not ok]
            print(f"[{i:2}/{len(qs)}] {'PASS' if g['passed'] else 'FAIL'}  {q['id']:<24} "
                  f"{'' if g['passed'] else 'failed: ' + ', '.join(failed)}")

    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # ---- summary ----
    by_cat = defaultdict(list)
    for row in rows:
        by_cat[row["category"]].append(row["passed"])
    check_tot = defaultdict(lambda: [0, 0])
    for row in rows:
        for c, ok in row["checks"].items():
            check_tot[c][0] += ok
            check_tot[c][1] += 1

    per_q = defaultdict(list)
    for row in rows:
        per_q[row["id"]].append(row["passed"])
    stable = [q for q, v in per_q.items() if all(v)]
    flaky = [q for q, v in per_q.items() if any(v) and not all(v)]
    broken = [q for q, v in per_q.items() if not any(v)]

    passed = sum(r["passed"] for r in rows)
    cost = sum(r["cost_inr"] for r in rows)
    lat = sorted(r["latency_s"] for r in rows)
    lines = [
        f"## Eval run {stamp}",
        "",
        f"**{passed}/{len(rows)} passed ({passed / len(rows):.0%})** · cost ₹{cost:.2f} · "
        f"median latency {lat[len(lat) // 2]:.1f}s · wall time {time.time() - t0:.0f}s",
        "",
        *([f"Runs: {args.repeat} · stable {len(stable)}/{len(per_q)} · flaky {len(flaky)} · always failing {len(broken)}",
           *[f"- flaky `{q}`: passed {sum(per_q[q])}/{args.repeat}" for q in flaky],
           *[f"- always failing `{q}`" for q in broken], ""] if args.repeat > 1 else []),
        "| Category | Passed |", "|---|---|",
        *[f"| {c} | {sum(v)}/{len(v)} |" for c, v in sorted(by_cat.items())],
        "",
        "| Check | Passed |", "|---|---|",
        *[f"| {c} | {ok}/{n} |" for c, (ok, n) in sorted(check_tot.items())],
        "",
        "### Failures",
        *[f"- `{r['id']}`{' (run ' + str(r['run']) + ')' if args.repeat > 1 else ''}: failed {', '.join(c for c, ok in r['checks'].items() if not ok)}"
          for r in rows if not r["passed"]],
    ]
    if passed == len(rows):
        lines.append("- none")
    summary = "\n".join(lines)
    (OUT_DIR / f"run-{stamp}.md").write_text(summary + "\n", encoding="utf-8")
    print("\n" + summary)
    print(f"\nDetails: {out_path}")


if __name__ == "__main__":
    main()