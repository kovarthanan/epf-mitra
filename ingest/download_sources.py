"""
EPF Mitra - polite downloader for EPFO public documents (new portal, www.epfo.gov.in).

Pages scanned:
  - /circulars/            -> div.download-box cards (title, division, date, PDF)
  - /employee-documents/   -> member reference PDFs (contribution rate, wage ceiling, ...)
  - /archives/             -> older scheme guidelines and FAQs

Usage:
    pip install requests beautifulsoup4
    python scripts/download_sources.py --dry-run          # list + division counts, no download
    python scripts/download_sources.py --out data/raw     # download everything selected
    python scripts/download_sources.py --limit 20         # small test run
"""

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.epfo.gov.in"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 epf-mitra/0.1",
    "Accept-Language": "en-US,en;q=0.9",
}
ALLOWED_HOSTS = {"epfo.gov.in", "epfindia.gov.in", "pmvbry.epfindia.gov.in", "pmvbry-cdn.epfindia.gov.in"}

SEEDS = [
    ("circular", f"{BASE}/circulars/"),
    ("employee_doc", f"{BASE}/employee-documents/"),
    ("archive", f"{BASE}/archives/"),
]

# Internal / staff-only divisions - not useful for members (tune after dry run)
INCLUDE_DIVISIONS = {
    "pension", "wsu", "edli", "exemption", "compliance", "legal",
    "international worker", "banking", "caiu", "csd", None,
}
EXCLUDE_TITLE_KEYWORDS = [
    "recruitment", "probation", "transfer of officer", "posting", "promotion", "apar",
    "ccs conduct", "vigilance", "tender", "admit card", "examination", "deputation",
    "seniority", "dpc", "e-mail", "staff provident fund", "leave travel", "ltc",
    "sparrow", "training programme", "workshop", "orientation program",
    "productivity linked bonus", "nominations for training", "induction training",
    "training program", "translation officer", "group 'c'", "group 'b'", "group 'a'",
]
MIN_YEAR = 2000
IGNORE_FILES = {"CitizenCharter.pdf"}

session = requests.Session()
session.headers.update(HEADERS)


def polite_get(url: str, delay: float, retries: int = 3):
    for attempt in range(1, retries + 1):
        time.sleep(delay)
        try:
            r = session.get(url, timeout=90)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503):
                wait = delay * attempt * 5
                print(f"  ! {r.status_code}, backing off {wait:.0f}s")
                time.sleep(wait)
                continue
            print(f"  ! HTTP {r.status_code}: {url}")
            return None
        except requests.RequestException as e:
            print(f"  ! attempt {attempt} failed: {e}")
    return None


def allowed(url: str) -> bool:
    host = urlparse(url).netloc.replace("www.", "")
    return any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS)


def to_iso(d: str | None) -> str | None:
    """'17/12/2025' -> '2025-12-17'"""
    if not d:
        return None
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", d)
    if not m:
        return None
    dd, mm, yy = map(int, m.groups())
    try:
        return datetime(yy, mm, dd).date().isoformat()
    except ValueError:
        return None


def to_iso_from_title(title: str) -> str | None:
    """'... dated 02-12-2025 ...' -> '2025-12-02' (fallback for untagged cards)"""
    m = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](20\d{2})", title)
    if not m:
        return None
    dd, mm, yy = map(int, m.groups())
    try:
        return datetime(yy, mm, dd).date().isoformat()
    except ValueError:
        return None


def parse_cards(soup: BeautifulSoup, source_type: str, page_url: str) -> list[dict]:
    """Circulars page: structured download-box cards."""
    items = []
    for box in soup.select("div.download-box"):
        a = box.select_one("a.view-pdf-btn[href]") or box.select_one("a[href$='.pdf']")
        if not a:
            continue
        url = urljoin(page_url, a["href"].strip())
        title_el = box.select_one(".download-title")
        title = title_el.get_text(" ", strip=True) if title_el else Path(urlparse(url).path).stem
        metas = [m.get_text(" ", strip=True) for m in box.select(".meta-item")]
        date_text = next((m for m in metas if re.search(r"\d{1,2}/\d{1,2}/\d{4}", m)), None)
        items.append({
            "url": url,
            "title": re.sub(r"\s+", " ", title)[:400],
            "date": to_iso(date_text) or to_iso_from_title(title),
            "year": int(box.get("data-year") or 0) or None,
            "month": int(box.get("data-month") or 0) or None,
            "division": (box.get("data-division") or "").lower() or None,
            "source_type": source_type,
            "seed_page": page_url,
        })
    return items


def parse_plain_links(soup: BeautifulSoup, source_type: str, page_url: str) -> list[dict]:
    """Employee-documents / archives: PDF links, title from nearest heading or filename."""
    items = []
    for a in soup.find_all("a", href=True):
        url = urljoin(page_url, a["href"].strip())
        if not url.lower().endswith(".pdf"):
            continue
        title = a.get_text(" ", strip=True)
        if not title or title.lower() in ("view pdf", "download"):
            parent = a.find_parent(["div", "li", "tr"])
            h = parent.find(["h2", "h3", "h4", "h5", "strong"]) if parent else None
            title = h.get_text(" ", strip=True) if h else Path(urlparse(url).path).stem
        items.append({
            "url": url, "title": re.sub(r"\s+", " ", title)[:400],
            "date": None, "year": None, "month": None, "division": None,
            "source_type": source_type, "seed_page": page_url,
        })
    return items


def collect_links(delay: float) -> list[dict]:
    found: dict[str, dict] = {}
    for source_type, seed in SEEDS:
        print(f"Scanning {seed}")
        r = polite_get(seed, delay)
        if not r:
            continue
        soup = BeautifulSoup(r.text, "html.parser")
        items = parse_cards(soup, source_type, seed) if source_type == "circular" \
            else parse_plain_links(soup, source_type, seed)
        print(f"  {len(items)} PDF links on page")
        for it in items:
            if not allowed(it["url"]):
                continue
            if Path(urlparse(it["url"]).path).name in IGNORE_FILES:
                continue
            found.setdefault(it["url"], it)  # de-dupe by URL
    return list(found.values())


def keep(item: dict) -> bool:
    low = item["title"].lower()
    if item["division"] not in INCLUDE_DIVISIONS:
        return False
    if any(k in low for k in EXCLUDE_TITLE_KEYWORDS):
        return False
    if item["year"] and item["year"] < MIN_YEAR:
        return False
    if "hindi" in low:
        return False
    if re.search(r"[ऀ-ॿ]", item["title"]):  # Hindi-only (Devanagari) circulars
        return False
    return True


def safe_name(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", Path(urlparse(url).path).name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/raw")
    ap.add_argument("--manifest", default="data/manifest.jsonl")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between requests")
    ap.add_argument("--limit", type=int, default=0, help="max downloads (0 = all)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    manifest_path = Path(args.manifest); manifest_path.parent.mkdir(parents=True, exist_ok=True)

    done = set()
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(json.loads(line)["url"])

    links = collect_links(args.delay)
    selected = [l for l in links if keep(l)]
    todo = [l for l in selected if l["url"] not in done]
    print(f"\nFound {len(links)} PDFs -> {len(selected)} after filters -> {len(todo)} new.")

    if args.dry_run:
        print("\nBy division (all circulars):")
        for div, n in Counter(l["division"] for l in links if l["source_type"] == "circular").most_common():
            flag = "" if div in INCLUDE_DIVISIONS else "  (excluded)"
            print(f"  {div!s:14} {n:5}{flag}")
        print("\nBy year (selected):")
        for y, n in sorted(Counter(l["year"] for l in selected).items(), key=lambda x: str(x[0])):
            print(f"  {y}: {n}")
        print("\nSamples:")
        for l in selected[:15]:
            print(f"- [{l['source_type']}/{l['division']}] {l['date']} | {l['title'][:90]}")
        return

    if args.limit:
        todo = todo[: args.limit]

    seen_hashes = set()
    with manifest_path.open("a", encoding="utf-8") as mf:
        for i, item in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] {item['title'][:70]}")
            r = polite_get(item["url"], args.delay)
            if not r or not r.content.startswith(b"%PDF"):
                print("  ! not a valid PDF, skipped")
                continue
            sha = hashlib.sha256(r.content).hexdigest()
            if sha in seen_hashes:
                print("  = duplicate content, skipped")
                continue
            seen_hashes.add(sha)
            path = out / item["source_type"] / safe_name(item["url"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(r.content)
            record = {
                **item,
                "sha256": sha,
                "bytes": len(r.content),
                "local_path": str(path).replace("\\", "/"),
                "last_modified": r.headers.get("Last-Modified"),
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
            }
            mf.write(json.dumps(record, ensure_ascii=False) + "\n")
            mf.flush()

    rows = [json.loads(l) for l in manifest_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    if rows:
        with manifest_path.with_suffix(".csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
    print(f"\nDone. Manifest: {manifest_path} ({len(rows)} records)")


if __name__ == "__main__":
    main()