"""Print the failed questions of the latest eval run (or a given run file).

Usage:
    python eval/show_failures.py
    python eval/show_failures.py eval/results/run-20261116-0958.jsonl
"""

import json
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"

path = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(RESULTS.glob("run-*.jsonl"))[-1]
print(f"Run: {path.name}")

for line in path.read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    if r["passed"]:
        continue
    failed = [c for c, ok in r["checks"].items() if not ok]
    run = f" run {r['run']}" if "run" in r else ""
    print(f"\n### {r['id']}{run}  (failed: {', '.join(failed)})")
    print(f"Q: {r['question']}")
    print(f"Expected source contains: {r['expected_sources']}")
    print(f"\n{r['answer']}\n")
    print("SOURCES:")
    for s in r["sources"]:
        mark = "*" if s["rank"] in r["cited"] else " "
        print(f" {mark}[{s['rank']}] {s['date'] or 'n.d.'}  {s['title'][:95]}")