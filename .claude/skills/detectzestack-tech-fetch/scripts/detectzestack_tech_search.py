#!/usr/bin/env python3
"""Detect each company's tech stack with DetectZeStack (via RapidAPI): one synchronous call per website.

GET /analyze?url=<site> answers directly (docs/detectzestack-api-reference.md): no polling. RapidAPI counts
every call against the monthly quota, so the script reads the quota left from each response's headers and
stops before going over. The script holds no run values: the input file, its column names and the output
file are flags.

Sample, then scale:
    S=.claude/skills/detectzestack-tech-fetch/scripts/detectzestack_tech_search.py
    python3 $S --input data/processed/companies_supabase_<date>.csv \
      --output data/processed/companies_tech_enriched_<date>.csv \
      --url-column domain --id-column domain --limit 5 --dry-run                       # show the sites, no calls
    python3 $S ...same flags... --limit 5                                              # sample: 5 companies
    python3 $S ...same flags... --resume                                               # everyone left

Input:  any CSV with a website/domain column; --id-column must be unique per company (the domain for Supabase).
Writes (appended as each answer arrives; --resume never re-calls a company already done or failed):
    --output                                  input columns + the RESULT_COLUMNS below (one file, appended each run)
    data/raw/<output name>.jsonl              one line per answer: our id + the API response, untouched
    data/raw/<output name>.state.json         companies done / failed, last quota seen (resume point)
Quota: 1 request per call. --keep N leaves N requests unused; the run stops when the quota left reaches it.
Run log: logs/detectzestack_tech_search.log. Failed calls: logs/detectzestack_tech_search_errors.log.
"""
import argparse
import csv
import json
import logging
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
LOG_FILE = ROOT / "logs" / "detectzestack_tech_search.log"
ERROR_LOG = ROOT / "logs" / "detectzestack_tech_search_errors.log"

# DetectZeStack / RapidAPI facts (docs/detectzestack-api-reference.md), not run settings.
ANALYZE_PATH = "/analyze"
QUOTA_HEADER = "X-RateLimit-Requests-Remaining"  # RapidAPI's monthly counter (counts every call)
USER_AGENT = "Mozilla/5.0 (compatible; gtm-tech-enrichment)"  # the API's firewall blocks Python's default agent
MAX_RPS = 2

# tech_stack / tech_enriched_at are named after gtm.companies (migration 005); the rest stay in the CSV.
# A failed scan still gets a row: tech_enriched_at set, tech_stack blank, tech_status_code = the error code.
RESULT_COLUMNS = ["tech_names", "tech_stack", "tech_count", "tech_scan_depth", "tech_status_code",
                  "tech_enriched_at", "tech_cached", "tech_raw"]

csv.field_size_limit(10_000_000)  # raw JSON cells


class QuotaReached(Exception):
    pass


def env_get(key):
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env (expected a line starting {key}=)")


def log_error(code, message, request):
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "message": message,
            "request": request,
        }) + "\n")


def analyze(host, key, site, timeout, attempts=3):
    """Return (response, quota left, error code) or (None, quota left, error code) after logging.
    Raises QuotaReached on a quota 429."""
    req = urllib.request.Request(
        f"https://{host}{ANALYZE_PATH}?" + urllib.parse.urlencode({"url": site}),
        headers={"x-rapidapi-host": host, "x-rapidapi-key": key, "User-Agent": USER_AGENT},
    )
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                left = resp.headers.get(QUOTA_HEADER)
                return json.load(resp), int(left) if left else None, None
        except urllib.error.HTTPError as e:
            code, message = e.code, e.read().decode(errors="replace")[:1000].replace(key, "***")
            left = e.headers.get(QUOTA_HEADER)
            left = int(left) if left else None
        except (urllib.error.URLError, TimeoutError) as e:
            # Not retried: the call may already have been counted. --retry-failed tries again later.
            log_error("network", str(e).replace(key, "***"), {"url": site})
            return None, None, "network"
        lowered = message.lower()
        if code == 429 and ("quota" in lowered or ("limit" in lowered and "used" in lowered) or left == 0):
            log_error(code, message, {"url": site})
            raise QuotaReached(message)
        if code in (429, 500, 503) and attempt < attempts:
            pause = 10 * attempt if code == 429 else 2 ** attempt
            logging.warning("HTTP %s for %s, retrying in %ss", code, site, pause)
            time.sleep(pause)
            continue
        log_error(code, message, {"url": site})
        return None, left, code


def load_state(path):
    if path.is_file():
        return json.loads(path.read_text())
    return {"input": None, "done": [], "failed": [], "quota_left": None}


def save_state(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)


def main():
    global ENV_FILE
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", help="companies CSV")
    parser.add_argument("--output", help="results CSV, appended each run (e.g. data/processed/companies_tech_enriched_<date>.csv)")
    parser.add_argument("--url-column", help="input column holding the website or domain to scan")
    parser.add_argument("--id-column", help="input column unique per company, used to join results back")
    parser.add_argument("--limit", type=int, help="scan at most N new companies this run (sample / next batch)")
    parser.add_argument("--resume", action="store_true", help="continue a run: scan the companies not done yet")
    parser.add_argument("--retry-failed", action="store_true", help="with --resume: also retry companies that failed")
    parser.add_argument("--dry-run", action="store_true", help="print the sites; call nothing")
    parser.add_argument("--keep", type=int, default=0, help="leave this many monthly requests unused")
    parser.add_argument("--rps", type=float, default=1, help=f"calls per second (max {MAX_RPS})")
    parser.add_argument("--timeout", type=int, default=60, help="seconds to wait for one scan before giving up")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    if not 0 < args.rps <= MAX_RPS:
        parser.error(f"--rps must be above 0 and at most {MAX_RPS}")

    # No defaults: a forgotten flag stops the run instead of guessing.
    missing_flags = [f for f, v in [("--input", args.input), ("--output", args.output),
                                    ("--url-column", args.url_column), ("--id-column", args.id_column)] if not v]
    if missing_flags:
        parser.error("missing " + ", ".join(missing_flags))

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{out_path.stem}.jsonl"
    state_path = raw_dir / f"{out_path.stem}.state.json"

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        in_columns = reader.fieldnames
        missing = [c for c in [args.url_column, args.id_column] if c not in in_columns]
        if missing:
            sys.exit(f"{args.input} has no column(s): {', '.join(missing)}. Columns: {', '.join(in_columns)}")
        clash = [c for c in RESULT_COLUMNS if c in in_columns]
        if clash:
            sys.exit(f"{args.input} already has result column(s) {', '.join(clash)}: pass the un-enriched list")
        rows, duplicates, no_url = {}, 0, 0
        for r in reader:
            k = r[args.id_column].strip()
            if not k:
                continue
            if not r[args.url_column].strip():
                no_url += 1
                continue
            duplicates += k in rows
            rows[k] = r
    if duplicates:
        sys.exit(f"--id-column {args.id_column} is not unique ({duplicates} repeats): pick a column unique per company")

    state = load_state(state_path)
    if (state["done"] or state["failed"]) and not args.resume and not args.dry_run:
        sys.exit(f"{state_path.relative_to(ROOT)} already has {len(state['done'])} done and {len(state['failed'])} "
                 "failed companies. Re-run with --resume to continue it (nothing is re-scanned).")
    if state["input"] and state["input"] != str(args.input):
        sys.exit(f"This run was started on {state['input']}, not {args.input}. Use another --output.")

    skip = set(state["done"]) | (set() if args.retry_failed else set(state["failed"]))
    todo = [k for k in rows if k not in skip]
    if args.limit is not None:
        todo = todo[:args.limit]

    if args.dry_run:
        print(f"DRY RUN: would scan {len(todo)} companies ({len(todo)} requests). {len(rows) - len(state['done'])} of "
              f"{len(rows)} not yet done ({len(state['failed'])} failed earlier); {no_url} rows have no "
              f"{args.url_column} and are skipped. Quota left at the last run: {state['quota_left']}. No calls made.")
        for k in todo:
            print(rows[k][args.url_column].strip())
        return

    host, key = env_get("RAPIDAPI_HOST"), env_get("RAPIDAPI_KEY")
    state["input"] = str(args.input)
    # The quota resets monthly (or with an upgrade), so only counts seen in this run's responses are trusted.
    state["quota_left"] = None
    if args.retry_failed:
        state["failed"] = [k for k in state["failed"] if k not in todo]
    new_file = not out_path.is_file()
    counts = {"done": 0, "failed": 0}
    stopped = None
    with open(out_path, "a", newline="") as out_f, open(raw_path, "a") as raw_f:
        writer = csv.DictWriter(out_f, fieldnames=in_columns + RESULT_COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        for k in todo:
            if state["quota_left"] is not None and state["quota_left"] <= args.keep:
                stopped = f"quota left ({state['quota_left']}) reached --keep {args.keep}"
                break
            time.sleep(1 / args.rps)
            try:
                resp, left, error_code = analyze(host, key, rows[k][args.url_column].strip(), args.timeout)
            except QuotaReached:
                stopped = "monthly quota used up (HTTP 429)"
                state["quota_left"] = 0
                save_state(state_path, state)
                break
            if left is not None:
                state["quota_left"] = left
            if not resp or "technologies" not in resp:
                if resp:
                    log_error("api", json.dumps(resp)[:1000], {"url": rows[k][args.url_column].strip()})
                # Attempted but failed: a row with the date and error code, no stack (the loader stores the date).
                writer.writerow({**rows[k], "tech_status_code": error_code or "api",
                                 "tech_enriched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
                out_f.flush()
                state["failed"].append(k)
                save_state(state_path, state)
                counts["failed"] += 1
                continue
            techs = resp.get("technologies") or []
            meta = resp.get("meta") or {}
            raw_f.write(json.dumps({"id": k, "response": resp}) + "\n")
            raw_f.flush()
            writer.writerow({**rows[k],
                             "tech_names": "; ".join(t.get("name", "") for t in techs),
                             "tech_stack": json.dumps(resp.get("categories") or {}, separators=(",", ":")),
                             "tech_count": len(techs),
                             "tech_scan_depth": meta.get("scan_depth", ""),
                             "tech_status_code": meta.get("status_code", ""),
                             "tech_enriched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "tech_cached": resp.get("cached", ""),
                             "tech_raw": json.dumps(resp, separators=(",", ":"))})
            out_f.flush()
            state["done"].append(k)
            save_state(state_path, state)
            counts["done"] += 1

    logging.info("scanned %d companies, %d failed%s", counts["done"], counts["failed"],
                 f" (see {ERROR_LOG.relative_to(ROOT)}; --resume --retry-failed tries them again)" if counts["failed"] else "")
    if stopped:
        logging.warning("stopped early: %s. Re-run with --resume when there is quota.", stopped)
    logging.info("quota left this month: %s", state["quota_left"])
    logging.info("progress: %d of %d companies done; results: %s", len(state["done"]), len(rows),
                 out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path)


if __name__ == "__main__":
    main()
