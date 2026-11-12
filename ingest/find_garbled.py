"""
EPF Mitra - find pages whose extracted (non-OCR) text is garbled, e.g. digital PDFs
with broken font encodings ("whwh Otiq[<A]vfaqfrmiinH Empl®yee]").

Scores each page by the share of tokens that look like real English words.
Pages below the threshold get chars=0 and garbled=true, so ocr_text.py will OCR them.

Usage:
    python ingest/find_garbled.py            # report only
    python ingest/find_garbled.py --apply    # mark pages for OCR, write data/garbled_docs.txt
"""

import argparse
import json
import re
from pathlib import Path

THRESHOLD = 0.55   # share of word-like tokens; real English prose scores 0.8+
MIN_TOKENS = 30    # ignore near-empty pages

COMMON = set("""the of and to in for is be by or as on that with this shall are from at
any not may such which under all have been has will an it its no per also""".split())


def word_score(text: str) -> float:
    toks = re.findall(r"[A-Za-z][A-Za-z'\-]*", text)
    if len(toks) < MIN_TOKENS:
        return 1.0
    good = 0
    for t in toks:
        tl = t.lower()
        if tl in COMMON:
            good += 1
        elif 3 <= len(tl) <= 15 and re.search(r"[aeiouy]", tl) and not re.search(r"[bcdfghjklmnpqrstvwxz]{5}", tl):
            good += 1
    return good / len(toks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="data/text")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    flagged_docs, flagged_pages, scanned_files = [], 0, 0
    for f in sorted(Path(args.text).glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        bad = []
        for p in d["pages"]:
            if p.get("ocr"):
                continue  # OCR output is noisy by nature; leave it
            s = word_score(p["text"])
            if s < THRESHOLD:
                bad.append((p["page"], round(s, 2)))
        if not bad:
            continue
        scanned_files += 1
        flagged_pages += len(bad)
        flagged_docs.append(d["doc_id"])
        print(f"{d['doc_id']}  {len(bad):2}/{d['num_pages']:2} pages  {d['title'][:60]}  e.g. p{bad[0][0]} score {bad[0][1]}")
        if args.apply:
            for p in d["pages"]:
                if any(p["page"] == pg for pg, _ in bad):
                    p["chars"], p["garbled"] = 0, True
            d["likely_scanned"] = True
            d.pop("ocr_applied", None)
            f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")

    print(f"\n{scanned_files} docs / {flagged_pages} pages look garbled.")
    if args.apply:
        Path("data/garbled_docs.txt").write_text("\n".join(flagged_docs), encoding="utf-8")
        print("Marked for OCR. Next: python ingest/ocr_text.py")


if __name__ == "__main__":
    main()