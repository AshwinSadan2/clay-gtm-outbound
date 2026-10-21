#!/usr/bin/env python3
"""Find the best-matching person at each target company. Titles and the companies file come from flags.

Two modes, one per run:
  --tier ... (repeated)  a title cascade, sent to Blitz Waterfall ICP. Each --tier is one tier, in
                         priority order (1-10 tiers; first tier with a match wins; its number becomes icp_tier).
  --title ...            one title list, no cascade, sent to Blitz People Search (icp_tier = 1).
--exclude-title and --location apply to both. --tier-exclude / --headline-tier take a tier number
(use 1 with --title).

Single-title example:
    python3 .claude/skills/fetch-contacts-push/scripts/blitz_contact_search.py --companies data/processed/companies_blitz_2026-10-19.csv \
      --title "Head Partnerships" "Director Partnerships" --exclude-title Intern --location WORLD --limit 10

Cascade example (the approved 2026-10-19 Clay cascade, docs/contact-search-request.md):
    python3 .claude/skills/fetch-contacts-push/scripts/blitz_contact_search.py \
      --companies data/processed/companies_blitz_2026-10-19.csv \
      --tier "VP Marketing" "Vice President Marketing" "SVP Marketing" "Senior Vice President Marketing" \
             "EVP Marketing" "CMO" "Chief Marketing Officer" "VP Growth" "Vice President Growth" \
             "VP Demand Generation" "VP Demand Gen" "Vice President Demand Generation" \
      --tier "Head Marketing" "Head Growth" "Head Demand Generation" "Head Demand Gen" \
      --tier "Director Marketing" "Director Growth" "Director Demand Generation" "Director Demand Gen" \
      --tier "VP Revenue Operations" "Vice President Revenue Operations" "Head Revenue Operations" \
             "Director Revenue Operations" "RevOps" "GTM Engineer" "Go To Market Engineer" \
      --tier "Founder" "CEO" "Chief Executive Officer" "[Owner]" \
      --tier "Marketing" "Growth" "Demand Generation" "Demand Gen" "Revenue Operations" \
      --exclude-title Assistant Intern Junior Coordinator Freelance Brand Communications Content PR "Social Media" \
      --tier-exclude 5 "Chief of Staff" Advisor \
      --headline-tier 6 --location WORLD \
      --limit 10                                # add --dry-run first to see the request without calling Blitz

Input:  any companies CSV with name, domain and linkedin_url columns (--companies)
Writes (appended as each company finishes; re-runs skip companies already done):
    data/raw/contacts_blitz_<date>.jsonl         one line per company: our ids + the API response, untouched
    data/raw/contacts_blitz_<date>.csv           readable copy of the raw file, every field
    data/processed/contacts_blitz_<date>.csv     gtm.contacts columns, found contacts only
One record per person found; a company with no match costs nothing.
Run log: logs/blitz_contact_search.log. Failed calls: logs/blitz_contact_search_errors.log.
"""
import argparse
import csv
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
WATERFALL_URL = "https://api.blitz-api.ai/v2/search/waterfall-icp-keyword"
PEOPLE_URL = "https://api.blitz-api.ai/v2/search/people"
LOG_FILE = ROOT / "logs" / "blitz_contact_search.log"
ERROR_LOG = ROOT / "logs" / "blitz_contact_search_errors.log"

RAW_CSV_COLUMNS = [
    "company_name", "company_domain", "company_linkedin_url", "status", "icp_tier", "ranking",
    "first_name", "last_name", "full_name", "nickname", "civility_title", "headline", "about_me",
    "person_linkedin_url", "connections_count", "profile_picture_url",
    "location_city", "location_state_code", "location_country_code", "location_continent",
    "job_title", "job_start_date", "job_is_current", "job_description",
    "experiences", "education", "skills", "certifications",
]

# Processed CSV = the signed-off gtm.contacts columns (docs/schema-contacts.md), found
# contacts only. No-match companies stay visible in the raw CSV (`status` column).
CSV_COLUMNS = [
    "person_linkedin_url", "company_domain", "icp_tier", "first_name", "last_name",
    "job_title", "headline", "location_country_code", "about_me", "raw",
]


class RateLimiter:
    """At most `rps` request starts per second, shared across worker threads."""

    def __init__(self, rps):
        self.interval = 1.0 / rps
        self.next_at = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.monotonic()
            start = max(now, self.next_at)
            self.next_at = start + self.interval
        time.sleep(max(0.0, start - now))


def env_get(key):
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env")


def log_error(code, message, body):
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "message": message,
            "request": body,
        }) + "\n")


def post(api_key, url, body, limiter, label, attempts=3):
    """Return the parsed response, or None after logging the error (never raises)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"x-api-key": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, attempts + 1):
        limiter.wait()
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
            logging.warning("HTTP %s for %s, retrying in %ss", code, label, wait)
            time.sleep(wait)
            continue
        log_error(code, message, body)
        return None


def matched_job(person, company_url):
    """The current job at the target company (the one the cascade matched)."""
    norm = lambda u: (u or "").rstrip("/").lower()
    jobs = person.get("experiences") or []
    for job in jobs:
        if norm(job.get("company_linkedin_url")) == norm(company_url) and job.get("job_is_current"):
            return job
    return jobs[0] if jobs else {}


def flatten(record, columns):
    company = record["company"]
    results = (record["response"].get("results") or [])
    row = {
        "company_name": company["name"],
        "company_domain": company["domain"],
        "company_linkedin_url": company["linkedin_url"],
        "status": "found" if results else "no_match",
    }
    if results:
        hit = results[0]
        person = hit.get("person") or hit  # Waterfall wraps the person; People Search returns it bare
        loc = person.get("location") or {}
        job = matched_job(person, company["linkedin_url"])
        row.update({k: person.get(k) for k in columns if k in person})
        row.update(
            icp_tier=hit.get("icp", 1),  # People Search has no tiers: its one title list is tier 1
            ranking=hit.get("ranking"),
            person_linkedin_url=person.get("linkedin_url"),
            headline=" ".join((person.get("headline") or "").split()),
            about_me=" ".join((person.get("about_me") or "").split()),
            location_city=loc.get("city"),
            location_state_code=loc.get("state_code"),
            location_country_code=loc.get("country_code"),
            location_continent=loc.get("continent"),
            job_title=job.get("job_title"),
            job_start_date=job.get("job_start_date"),
            job_is_current=job.get("job_is_current"),
            job_description=" ".join((job.get("job_description") or "").split()),
        )
        for k in ("experiences", "education", "skills", "certifications"):
            if k in columns:
                row[k] = json.dumps(person.get(k) or [])
    if "raw" in columns:
        row["raw"] = json.dumps(record["response"])
    return row


def open_csv(path, columns):
    """Open a CSV for appending, writing the header only if the file is new."""
    is_new = not path.exists()
    f = open(path, "a", newline="")
    writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
    if is_new:
        writer.writeheader()
    return f, writer


def build_cascade(args):
    if len(args.tier) > 10:
        sys.exit(f"Blitz allows at most 10 tiers, got {len(args.tier)}")
    for titles in args.tier + [args.exclude_title or []]:
        if len(titles) > 50:
            sys.exit(f"Blitz allows at most 50 titles per list, got {len(titles)}: {titles[0]!r}...")
    extra = {}
    for n, *titles in args.tier_exclude or []:
        if not n.isdigit() or not 1 <= int(n) <= len(args.tier):
            sys.exit(f"--tier-exclude needs a tier number (1-{len(args.tier)}) first, got {n!r}")
        extra.setdefault(int(n), []).extend(titles)
    for n in args.headline_tier or []:
        if not 1 <= n <= len(args.tier):
            sys.exit(f"--headline-tier {n}: there are only {len(args.tier)} tiers")
    cascade = []
    for i, titles in enumerate(args.tier, 1):
        tier = {"include_title": titles, "exclude_title": (args.exclude_title or []) + extra.get(i, []),
                "location": args.location}
        if i in (args.headline_tier or []):
            tier["include_headline_search"] = True
        cascade.append(tier)
    return cascade


def people_search_body(company_url, tier):
    """The single-title search for one company, from the one-tier cascade."""
    people = {"job_title": {"include": tier["include_title"], "exclude": tier["exclude_title"],
                            "include_linkedin_headline": tier.get("include_headline_search", False)}}
    if "WORLD" not in tier["location"]:
        people["location"] = {"country_code": tier["location"]}
    return {"company": {"linkedin_url": [company_url]}, "people": people, "max_results": 1}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--companies", required=True, help="companies CSV to search (name, domain, linkedin_url)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--tier", action="append", nargs="+", metavar="TITLE",
                      help="titles for one cascade tier; repeat for each tier, highest priority first (Waterfall ICP)")
    mode.add_argument("--title", nargs="+", metavar="TITLE",
                      help="one title list, no cascade (People Search)")
    parser.add_argument("--exclude-title", action="extend", nargs="+", metavar="TITLE",
                        help="titles to exclude on every tier")
    parser.add_argument("--tier-exclude", action="append", nargs="+", metavar="N_THEN_TITLES",
                        help="extra excludes for one tier only: tier number, then titles")
    parser.add_argument("--headline-tier", action="append", type=int, metavar="N",
                        help="also search the LinkedIn headline on this tier (repeatable)")
    parser.add_argument("--location", action="extend", nargs="+", required=True,
                        help="contact location, e.g. WORLD or US")
    parser.add_argument("--dry-run", action="store_true", help="print the request body and exit without calling Blitz")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    parser.add_argument("--limit", type=int, help="max companies to process this run (default: all remaining)")
    parser.add_argument("--date", default=date.today().isoformat(), help="file date stamp to write/resume")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rps", type=float, default=4.5, help="request starts per second (plan limit: 5)")
    args = parser.parse_args()
    global ENV_FILE
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    if args.title:
        args.tier = [args.title]
    cascade = build_cascade(args)

    def request(company_url):
        if args.title:
            return PEOPLE_URL, people_search_body(company_url, cascade[0])
        return WATERFALL_URL, {"company_linkedin_url": company_url, "max_results": 1, "cascade": cascade}

    if args.dry_run:
        url, body = request("<each company>")
        print(f"POST {url}\n{json.dumps(body, indent=2)}")
        return

    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )

    companies_csv = Path(args.companies)
    raw_file = ROOT / "data" / "raw" / f"contacts_blitz_{args.date}.jsonl"
    raw_csv_file = raw_file.with_suffix(".csv")
    csv_file = ROOT / "data" / "processed" / f"contacts_blitz_{args.date}.csv"
    for d in (raw_file.parent, csv_file.parent):
        d.mkdir(parents=True, exist_ok=True)

    with open(companies_csv, newline="") as f:
        companies = [{k: r[k] for k in ("name", "domain", "linkedin_url")} for r in csv.DictReader(f)]

    # Resume: a company counts as done once its result (match or no-match) is in the raw file.
    done = set()
    if raw_file.exists():
        done = {json.loads(l)["company"]["linkedin_url"] for l in raw_file.read_text().splitlines() if l}
    todo = [c for c in companies if c["linkedin_url"] not in done][: args.limit]
    logging.info("companies: %d total, %d already done, %d to process this run", len(companies), len(done), len(todo))

    api_key = env_get("Blitz_APIKEY")
    limiter = RateLimiter(args.rps)

    def search(company):
        url, body = request(company["linkedin_url"])
        return company, post(api_key, url, body, limiter, company["linkedin_url"])

    found = no_match = errors = 0
    tiers = {}
    last_fair = {}
    raw_csv_out, raw_writer = open_csv(raw_csv_file, RAW_CSV_COLUMNS)
    csv_out, writer = open_csv(csv_file, CSV_COLUMNS)
    with open(raw_file, "a") as raw_out, raw_csv_out, csv_out, ThreadPoolExecutor(args.workers) as pool:
        for future in as_completed([pool.submit(search, c) for c in todo]):
            company, resp = future.result()
            if resp is None:
                errors += 1
                continue  # not marked done, so a re-run retries it
            record = {"company": company, "response": resp}
            raw_out.write(json.dumps(record) + "\n")
            raw_writer.writerow(flatten(record, RAW_CSV_COLUMNS))
            if resp.get("results"):
                writer.writerow(flatten(record, CSV_COLUMNS))
            for f in (raw_out, raw_csv_out, csv_out):
                f.flush()
            results = resp.get("results") or []
            if results:
                found += 1
                tier = results[0].get("icp", 1)
                tiers[tier] = tiers.get(tier, 0) + 1
            else:
                no_match += 1
            last_fair = resp.get("fair_usage") or last_fair

    logging.info(
        "done: %d found, %d no match, %d errors%s | tiers %s | records remaining %s",
        found, no_match, errors,
        f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "",
        dict(sorted(tiers.items())), last_fair.get("records_remaining"),
    )


if __name__ == "__main__":
    main()
