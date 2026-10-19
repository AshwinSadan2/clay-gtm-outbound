#!/usr/bin/env python3
"""Pull target companies from Blitz Company Search using the approved request.

Approved request: docs/company-search-request.md (approved 2026-10-19).

Usage:
    python3 scripts/blitz_company_search.py --limit 10 --page-size 10   # sample
    python3 scripts/blitz_company_search.py --limit 300 --resume        # scale, continuing after the sample

Writes (one run = one date-stamped set):
    data/raw/companies_blitz_<date>.jsonl          every company exactly as returned
    data/raw/companies_blitz_<date>.cursor         cursor to resume from (the next unread page)
    data/processed/companies_blitz_<date>.csv      flattened, one row per company, for review
Each company costs 1 Blitz record. Logs go to logs/blitz_company_search.log.
"""
import argparse
import csv
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://api.blitz-api.ai/v2/search/companies"
LOG_FILE = ROOT / "logs" / "blitz_company_search.log"

APPROVED_FILTERS = {
    "industry": {"include": ["Software Development"]},
    "keywords": {"include": ["SaaS"]},
    "employee_range": ["51-200"],
    "hq": {"country_code": ["US"]},
}

CSV_COLUMNS = [
    "name", "domain", "website", "linkedin_url", "linkedin_id", "industry", "type", "size",
    "employees_on_linkedin", "followers", "founded_year", "hq_city", "hq_state",
    "hq_country_code", "specialties", "about",
]


def env_get(key):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env")


def post(api_key, body, attempts=3):
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code in (429, 500, 503) and attempt < attempts:
                wait = 60 if e.code == 429 else 2 ** attempt
                logging.warning("HTTP %s, retrying in %ss: %s", e.code, wait, detail)
                time.sleep(wait)
                continue
            sys.exit(f"HTTP {e.code}: {detail}")


def flatten(company):
    hq = company.get("hq") or {}
    row = {c: company.get(c) for c in CSV_COLUMNS}
    row.update(
        hq_city=hq.get("city"),
        hq_state=hq.get("state"),
        hq_country_code=hq.get("country_code"),
        specialties="; ".join(company.get("specialties") or []),
        about=(company.get("about") or "").replace("\n", " ").strip(),
    )
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, required=True, help="total companies to pull this run")
    parser.add_argument("--page-size", type=int, default=50, help="results per request (1-50)")
    parser.add_argument("--resume", action="store_true", help="continue from the saved cursor")
    parser.add_argument("--date", default=date.today().isoformat(), help="file date stamp to write/resume")
    args = parser.parse_args()

    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    raw_file = ROOT / "data" / "raw" / f"companies_blitz_{args.date}.jsonl"
    cursor_file = raw_file.with_suffix(".cursor")
    csv_file = ROOT / "data" / "processed" / f"companies_blitz_{args.date}.csv"

    cursor = None
    if args.resume:
        if not cursor_file.exists():
            sys.exit(f"No cursor to resume from at {cursor_file}")
        cursor = cursor_file.read_text().strip() or None
        if cursor is None:
            sys.exit("Saved cursor is empty: all matching companies were already pulled")
    elif raw_file.exists():
        sys.exit(f"{raw_file} already exists. Use --resume to continue it, or --date for a new set.")

    api_key = env_get("Blitz_APIKEY")
    seen = set()
    if raw_file.exists():
        seen = {json.loads(l).get("linkedin_url") for l in raw_file.read_text().splitlines() if l}

    pulled = 0
    with open(raw_file, "a") as raw_out:
        while pulled < args.limit:
            body = {"company": APPROVED_FILTERS, "max_results": min(args.page_size, args.limit - pulled)}
            if cursor:
                body["cursor"] = cursor
            resp = post(api_key, body)
            results = resp.get("results") or []
            fair = resp.get("fair_usage") or {}
            for company in results:
                if company.get("linkedin_url") in seen:
                    continue
                seen.add(company.get("linkedin_url"))
                raw_out.write(json.dumps(company) + "\n")
                pulled += 1
            raw_out.flush()
            cursor = resp.get("cursor")
            cursor_file.write_text(cursor or "")
            logging.info(
                "page: %d results | pulled this run %d/%d | total matching %s | records used %s, remaining %s | request %s",
                len(results), pulled, args.limit, resp.get("total_results"),
                fair.get("records_used"), fair.get("records_remaining"), fair.get("request_id"),
            )
            if not cursor or not results:
                logging.info("no more pages")
                break

    # Rebuild the review CSV from everything in the raw file (sample + later runs).
    companies = [json.loads(l) for l in raw_file.read_text().splitlines() if l]
    with open(csv_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(flatten(c) for c in companies)
    logging.info("wrote %d companies to %s", len(companies), csv_file.relative_to(ROOT))


if __name__ == "__main__":
    main()
