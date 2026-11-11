"""
EPF Mitra - OCR for scanned pages.

Reads data/text/*.json produced by extract_text.py. For every page with too little
text, renders the page with PyMuPDF and runs Tesseract. Updates the JSON in place
(adds "ocr": true on OCR'd pages) and writes data/ocr_report.csv.

Usage:
    pip install pymupdf pytesseract
    python scripts/ocr_text.py                 # all docs needing OCR
    python scripts/ocr_text.py --limit 20      # first 20 docs
    python scripts/ocr_text.py --dpi 300       # higher quality, slower
"""

import argparse
import csv
import json
import re
import time
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

PAGE_MIN_CHARS = 200          # page below this gets OCR'd
TESS_CONFIG = "--oem 1 --psm 6"   # LSTM engine, assume a uniform block of text


def clean(text: str) -> str:
    text = text.replace("\x00", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def ocr_page(doc: fitz.Document, page_no: int, dpi: int) -> str:
    page = doc[page_no - 1]
    pix = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return clean(pytesseract.image_to_string(img, lang="eng", config=TESS_CONFIG))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="data/text")
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    ap.add_argument("--report", default="data/ocr_report.csv")
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    # doc_id -> local pdf path
    pdf_by_id = {}
    for line in Path(args.manifest).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            pdf_by_id[rec["sha256"][:12]] = rec["local_path"]

    files = sorted(Path(args.text).glob("*.json"))
    todo = []
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        if any(p["chars"] < PAGE_MIN_CHARS and not p.get("ocr") for p in d["pages"]):
            todo.append((f, d))
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(files)} docs, {len(todo)} need OCR")

    report = []
    t0 = time.time()
    for i, (f, d) in enumerate(todo, 1):
        pdf = pdf_by_id.get(d["doc_id"])
        if not pdf or not Path(pdf).exists():
            print(f"[{i}/{len(todo)}] ! pdf missing for {d['doc_id']}")
            continue
        doc = fitz.open(pdf)
        pages_done, before = 0, d["total_chars"]
        for p in d["pages"]:
            if p["chars"] >= PAGE_MIN_CHARS or p.get("ocr"):
                continue
            try:
                txt = ocr_page(doc, p["page"], args.dpi)
            except Exception as e:
                print(f"  ! page {p['page']} failed: {e}")
                continue
            if len(txt) > p["chars"]:
                p["text"], p["chars"], p["ocr"] = txt, len(txt), True
            else:
                p["ocr"] = True  # tried; page is blank or an image
            pages_done += 1
        doc.close()
        d["total_chars"] = sum(p["chars"] for p in d["pages"])
        d["avg_chars_per_page"] = round(d["total_chars"] / max(1, d["num_pages"]))
        d["likely_scanned"] = False
        d["ocr_applied"] = True
        f.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        elapsed = time.time() - t0
        print(f"[{i}/{len(todo)}] {pages_done:3}p OCR  {before:6} -> {d['total_chars']:6} chars  "
              f"({elapsed/60:4.1f} min)  {d['title'][:50]}")
        report.append({"doc_id": d["doc_id"], "title": d["title"][:80], "pages_ocr": pages_done,
                       "chars_before": before, "chars_after": d["total_chars"]})

    if report:
        with Path(args.report).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(report[0].keys()))
            w.writeheader(); w.writerows(report)
    low = [r for r in report if r["chars_after"] < 300]
    print(f"\nDone. {len(report)} docs OCR'd in {(time.time()-t0)/60:.1f} min. "
          f"{len(low)} still have <300 chars (check manually). Report: {args.report}")


if __name__ == "__main__":
    main()