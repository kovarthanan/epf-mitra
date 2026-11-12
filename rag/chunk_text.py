"""
EPF Mitra - clean and chunk extracted text into data/chunks.jsonl.

Each chunk carries the metadata needed for citations:
  doc_id, title, url, date, year, division, source_type, page_start, page_end, ocr

Usage:
    python scripts/chunk_text.py
    python scripts/chunk_text.py --size 900 --overlap 150
"""

import argparse
import json
import re
from pathlib import Path

# Lines like these are letterhead/stamp noise from OCR
NOISE_PATTERNS = [
    r"^website\s*:", r"^plate a, ground floor", r"^head office$", r"^to$", r"^madam\s*/?\s*sir,?$",
    r"^all (accs|regional|zonal)", r"^\(?ministry of labour", r"employees'? provident fund organisation$",
    r"^(copy|cc) to", r"^page \d+( of \d+)?$", r"^\d+$",
]

def best_date(d: dict) -> str | None:
    """Prefer the date written in the circular's title over the site's upload date."""
    m = re.search(r"dated\s*:?\s*(\d{1,2})[-./](\d{1,2})[-./](20\d{2})", d["title"], re.I)
    if m:
        dd, mm, yy = map(int, m.groups())
        try:
            from datetime import date
            return date(yy, mm, dd).isoformat()
        except ValueError:
            pass
    return d.get("date")


def is_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    low = s.lower()
    if any(re.search(p, low) for p in NOISE_PATTERNS):
        return True
    letters = sum(c.isalpha() for c in s)
    # short lines that are mostly symbols/garbage ("Ne ae", "Lat yh, , . Sty")
    if len(s) <= 25 and letters / max(1, len(s)) < 0.75:
        return True
    words = s.split()
    if len(s) <= 25 and all(len(w) <= 3 for w in words):
        return True
    return False


def clean_page(text: str) -> str:
    lines = [l.rstrip() for l in text.splitlines()]
    kept = [l for l in lines if not is_noise(l)]
    txt = "\n".join(kept)
    txt = re.sub(r"-\n(\w)", r"\1", txt)          # join hyphenated line breaks
    txt = re.sub(r"(?<![.:;!?])\n(?=[a-z])", " ", txt)  # join wrapped lines
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt.strip()


def split_paragraphs(text: str) -> list[str]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras


def chunk_pages(pages: list[dict], size: int, overlap: int) -> list[dict]:
    """Greedy paragraph packing with page tracking and overlap carry-over."""
    chunks, buf, buf_pages, buf_ocr = [], [], set(), False

    def flush():
        nonlocal buf, buf_pages, buf_ocr
        if not buf:
            return
        text = "\n\n".join(buf).strip()
        if len(text) >= 80:
            chunks.append({"text": text, "page_start": min(buf_pages),
                           "page_end": max(buf_pages), "ocr": buf_ocr})
        # overlap: keep the tail of the last paragraph(s)
        tail, keep = [], 0
        for p in reversed(buf):
            if keep >= overlap:
                break
            tail.insert(0, p); keep += len(p)
        buf = tail[-1:] if tail and len(tail[-1]) <= overlap * 2 else []
        buf_pages = set(list(buf_pages)[-1:]) if buf else set()
        buf_ocr = buf_ocr if buf else False

    for pg in pages:
        text = clean_page(pg["text"])
        if not text:
            continue
        for para in split_paragraphs(text):
            # very long paragraph -> split by sentences
            pieces = [para] if len(para) <= size else re.split(r"(?<=[.;:])\s+", para)
            for piece in pieces:
                if sum(len(b) for b in buf) + len(piece) > size and buf:
                    flush()
                buf.append(piece); buf_pages.add(pg["page"]); buf_ocr = buf_ocr or bool(pg.get("ocr"))
    flush()
    return chunks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="data/text")
    ap.add_argument("--out", default="data/chunks.jsonl")
    ap.add_argument("--size", type=int, default=900, help="target chars per chunk")
    ap.add_argument("--overlap", type=int, default=150)
    args = ap.parse_args()

    files = sorted(Path(args.text).glob("*.json"))
    exclude_path = Path("data/exclude_docs.txt")
    excluded = set(exclude_path.read_text(encoding="utf-8").split()) if exclude_path.exists() else set()
    total, docs, skipped = 0, 0, 0
    with Path(args.out).open("w", encoding="utf-8") as out:
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            if d["doc_id"] in excluded:
                skipped += 1
                continue
            if d.get("likely_scanned") and not d.get("ocr_applied"):
                skipped += 1
                continue
            chunks = chunk_pages(d["pages"], args.size, args.overlap)
            for i, c in enumerate(chunks):
                rec = {
                    "chunk_id": f"{d['doc_id']}_{i:03d}",
                    "doc_id": d["doc_id"],
                    "title": d["title"],
                    "url": d["url"],
                    "date": best_date(d),
                    "year": int(best_date(d)[:4]) if best_date(d) else d.get("year"),
                    "division": d.get("division"),
                    "source_type": d.get("source_type"),
                    **c,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            total += len(chunks); docs += 1
    print(f"{docs} docs -> {total} chunks ({total/max(1,docs):.1f} per doc). "
          f"Skipped {skipped} scanned docs not yet OCR'd. Output: {args.out}")


if __name__ == "__main__":
    main()