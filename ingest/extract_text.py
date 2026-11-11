"""
EPF Mitra - extract text from downloaded PDFs, page by page.

Reads data/manifest.jsonl, writes one JSON per PDF to data/text/<sha256[:12]>.json
and a summary report data/extract_report.csv. Flags scanned PDFs (little or no text)
so they can be OCR'd later.

Usage:
    pip install pymupdf
    python scripts/extract_text.py              # all PDFs in manifest
    python scripts/extract_text.py --limit 20   # first 20 only
"""

import argparse
import csv
import json
import re
from pathlib import Path

import fitz  # PyMuPDF

SCANNED_THRESHOLD = 200  # avg chars per page below this => probably scanned


def clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract(pdf_path: Path) -> dict:
    doc = fitz.open(pdf_path)
    pages = []
    for i, page in enumerate(doc, 1):
        txt = clean(page.get_text("text"))
        pages.append({"page": i, "chars": len(txt), "text": txt})
    doc.close()
    total = sum(p["chars"] for p in pages)
    avg = total / len(pages) if pages else 0
    return {
        "pages": pages,
        "num_pages": len(pages),
        "total_chars": total,
        "avg_chars_per_page": round(avg),
        "likely_scanned": avg < SCANNED_THRESHOLD,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    ap.add_argument("--out", default="data/text")
    ap.add_argument("--report", default="data/extract_report.csv")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(l) for l in Path(args.manifest).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]

    report, scanned, failed = [], 0, 0
    for i, rec in enumerate(rows, 1):
        doc_id = rec["sha256"][:12]
        target = out / f"{doc_id}.json"
        if target.exists():
            continue
        pdf = Path(rec["local_path"])
        try:
            info = extract(pdf)
        except Exception as e:
            failed += 1
            print(f"[{i}/{len(rows)}] ! failed {pdf.name}: {e}")
            report.append({"doc_id": doc_id, "title": rec["title"][:80], "status": f"error: {e}"})
            continue
        if info["likely_scanned"]:
            scanned += 1
        record = {
            "doc_id": doc_id,
            "title": rec["title"],
            "url": rec["url"],
            "date": rec.get("date"),
            "year": rec.get("year"),
            "division": rec.get("division"),
            "source_type": rec.get("source_type"),
            **info,
        }
        target.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
        flag = "SCANNED?" if info["likely_scanned"] else "ok"
        print(f"[{i}/{len(rows)}] {flag:8} {info['num_pages']:3}p {info['avg_chars_per_page']:5} c/p  {rec['title'][:60]}")
        report.append({
            "doc_id": doc_id, "title": rec["title"][:80], "date": rec.get("date"),
            "division": rec.get("division"), "pages": info["num_pages"],
            "avg_chars_per_page": info["avg_chars_per_page"],
            "status": "scanned" if info["likely_scanned"] else "ok",
        })

    if report:
        with Path(args.report).open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["doc_id", "title", "date", "division", "pages",
                                              "avg_chars_per_page", "status"])
            w.writeheader(); w.writerows(report)
    print(f"\nDone. {len(report)} processed, {scanned} likely scanned, {failed} failed. Report: {args.report}")


if __name__ == "__main__":
    main()