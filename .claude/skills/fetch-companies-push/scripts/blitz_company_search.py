#!/usr/bin/env python3
"""Pull target companies from Blitz Company Search. The search filters come from flags.

Example (the approved 2026-10-19 Clay request, docs/company-search-request.md):
    FILTERS='--industry "Software Development" --keyword SaaS --employee-range 51-200 --country US'
    python3 .claude/skills/fetch-companies-push/scripts/blitz_company_search.py $FILTERS --limit 10 --dry-run              # show the request, no API call
    python3 .claude/skills/fetch-companies-push/scripts/blitz_company_search.py $FILTERS --limit 10 --page-size 10         # sample
    python3 .claude/skills/fetch-companies-push/scripts/blitz_company_search.py $FILTERS --limit 300 --resume              # scale, continuing after the sample
Exploring filters: add --probe for one 1-record call that prints how many companies match, saving nothing.
Each filter flag can be repeated (values are OR'd, as in Blitz): --employee-range 11-50 --employee-range 51-200.

Writes (one run = one date-stamped set):
    data/raw/companies_blitz_<date>.jsonl          every company exactly as returned (used for resume/dedup)
    data/raw/companies_blitz_<date>.csv            readable copy of the raw file, every field
    data/raw/companies_blitz_<date>.cursor         cursor to resume from (the next unread page)
    data/raw/companies_blitz_<date>.filters.json   filters this set was pulled with (resume must match)
    data/processed/companies_blitz_<date>.csv      flattened, one row per company, for review
Each company costs 1 Blitz record. Run log: logs/blitz_company_search.log.
Failed calls (code, message, request): logs/blitz_company_search_errors.log.
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

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
URL = "https://api.blitz-api.ai/v2/search/companies"
LOG_FILE = ROOT / "logs" / "blitz_company_search.log"
ERROR_LOG = ROOT / "logs" / "blitz_company_search_errors.log"

# Readable copy of the raw file: every field Blitz returns, with hq split into columns.
RAW_CSV_COLUMNS = [
    "name", "domain", "website", "linkedin_url", "linkedin_id", "industry", "type", "size",
    "employees_on_linkedin", "followers", "founded_year", "hq_city", "hq_state",
    "hq_country_code", "hq_country_name", "hq_region", "hq_continent", "specialties", "about",
]

# Review CSV columns = the signed-off gtm.accounts columns (docs/schema-accounts.md).
# Everything else Blitz returns is kept, unfiltered, in the `raw` JSON column.
CSV_COLUMNS = [
    "domain", "name", "website", "linkedin_url", "industry", "employees_on_linkedin",
    "hq_country_code", "about", "raw",
]


def env_get(key):
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env")


def log_error(code, message, body):
    """Append one failed call to the error log for review after the run."""
    ERROR_LOG.parent.mkdir(exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "message": message,
            "request": body,
        }) + "\n")


def post(api_key, body, attempts=3):
    """Return the parsed response, or None after logging the error (never raises)."""
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
            code, message = e.code, e.read().decode(errors="replace")[:1000]
        except (urllib.error.URLError, TimeoutError) as e:
            # A timeout is not retried: Blitz may already have counted the records.
            log_error("network", str(e), body)
            return None
        if code in (429, 500, 503) and attempt < attempts:
            wait = 60 if code == 429 else 2 ** attempt
            logging.warning("HTTP %s, retrying in %ss", code, wait)
            time.sleep(wait)
            continue
        log_error(code, message, body)
        return None


def flatten(company, columns=CSV_COLUMNS):
    hq = company.get("hq") or {}
    row = {c: company.get(c) for c in columns}
    row.update({f"hq_{k}": v for k, v in hq.items() if f"hq_{k}" in columns})
    row.update(
        specialties="; ".join(company.get("specialties") or []),
        about=" ".join((company.get("about") or "").split()),  # collapse \n, \r, tabs
    )
    if "raw" in columns:
        row["raw"] = json.dumps(company)
    return row


def open_csv(path, columns):
    """Open a CSV for appending, writing the header only if the file is new."""
    is_new = not path.exists()
    f = open(path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
    if is_new:
        writer.writeheader()
    return f, writer


def build_filters(args):
    filters = {
        "industry": {"include": args.industry},
        "employee_range": args.employee_range,
        "hq": {"country_code": args.country},
    }
    if args.keyword:
        filters["keywords"] = {"include": args.keyword}
    return filters


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry", action="append", required=True,
                        help='exact LinkedIn industry string, e.g. "Software Development" (repeatable)')
    parser.add_argument("--keyword", action="append", help="keyword the company must match, e.g. SaaS (repeatable)")
    parser.add_argument("--employee-range", action="append", required=True,
                        help="LinkedIn size band, e.g. 51-200 (repeatable)")
    parser.add_argument("--country", action="append", required=True,
                        help="HQ country, ISO 2-letter code, e.g. US (repeatable)")
    parser.add_argument("--dry-run", action="store_true", help="print the request body and exit without calling Blitz")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    parser.add_argument("--probe", action="store_true",
                        help="one call returning 1 company (1 record): print the match count and that company, save nothing")
    parser.add_argument("--limit", type=int, help="total companies to pull this run (required unless --probe)")
    parser.add_argument("--page-size", type=int, default=50, help="results per request (1-50)")
    parser.add_argument("--resume", action="store_true", help="continue from the saved cursor")
    parser.add_argument("--date", default=date.today().isoformat(), help="file date stamp to write/resume")
    args = parser.parse_args()
    if args.limit is None and not args.probe:
        parser.error("--limit is required (unless --probe)")
    global ENV_FILE
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    filters = build_filters(args)

    if args.dry_run:
        print(json.dumps({"company": filters, "max_results": min(args.page_size, args.limit)}, indent=2))
        return

    if args.probe:
        resp = post(env_get("Blitz_APIKEY"), {"company": filters, "max_results": 1})
        if resp is None:
            sys.exit(f"probe failed: see {ERROR_LOG.relative_to(ROOT)}")
        first = (resp.get("results") or [{}])[0]
        print(f"total matching: {resp.get('total_results')} | records remaining: "
              f"{(resp.get('fair_usage') or {}).get('records_remaining')}")
        if first:
            row = flatten(first, RAW_CSV_COLUMNS)
            print("example: " + " | ".join(str(row.get(k)) for k in
                  ("name", "domain", "industry", "employees_on_linkedin", "hq_country_code", "specialties")))
        return

    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    raw_file = ROOT / "data" / "raw" / f"companies_blitz_{args.date}.jsonl"
    raw_csv_file = raw_file.with_suffix(".csv")
    cursor_file = raw_file.with_suffix(".cursor")
    filters_file = raw_file.with_suffix(".filters.json")
    csv_file = ROOT / "data" / "processed" / f"companies_blitz_{args.date}.csv"
    for d in (raw_file.parent, csv_file.parent):
        d.mkdir(parents=True, exist_ok=True)

    cursor = None
    if args.resume:
        if not cursor_file.exists():
            sys.exit(f"No cursor to resume from at {cursor_file}")
        cursor = cursor_file.read_text().strip() or None
        if cursor is None:
            sys.exit("Saved cursor is empty: all matching companies were already pulled")
        # A cursor belongs to one search: resuming it with other filters would mix two lists.
        if filters_file.exists() and json.loads(filters_file.read_text()) != filters:
            sys.exit(f"Filters differ from the ones this set was pulled with ({filters_file}). "
                     "Use the same filters to resume, or --date for a new set.")
    elif raw_file.exists():
        sys.exit(f"{raw_file} already exists. Use --resume to continue it, or --date for a new set.")
    filters_file.write_text(json.dumps(filters, indent=2) + "\n")

    api_key = env_get("Blitz_APIKEY")
    seen = set()
    if raw_file.exists():
        seen = {json.loads(l).get("linkedin_url") for l in raw_file.read_text().splitlines() if l}

    pulled = errors = 0
    raw_csv_out, raw_writer = open_csv(raw_csv_file, RAW_CSV_COLUMNS)
    csv_out, writer = open_csv(csv_file, CSV_COLUMNS)
    with open(raw_file, "a") as raw_out, raw_csv_out, csv_out:
        while pulled < args.limit:
            body = {"company": filters, "max_results": min(args.page_size, args.limit - pulled)}
            if cursor:
                body["cursor"] = cursor
            resp = post(api_key, body)
            if resp is None:
                errors += 1
                logging.error("page failed; cursor saved. Fix the cause, then re-run with --resume")
                break
            results = resp.get("results") or []
            fair = resp.get("fair_usage") or {}
            for company in results:
                if company.get("linkedin_url") in seen:
                    continue
                seen.add(company.get("linkedin_url"))
                raw_out.write(json.dumps(company) + "\n")
                raw_writer.writerow(flatten(company, RAW_CSV_COLUMNS))
                writer.writerow(flatten(company))
                pulled += 1
            for f in (raw_out, raw_csv_out, csv_out):
                f.flush()
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

    logging.info(
        "done: %d new companies this run, %d total in %s | errors: %d%s",
        pulled, len(seen), csv_file.relative_to(ROOT), errors,
        f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "",
    )


if __name__ == "__main__":
    main()
