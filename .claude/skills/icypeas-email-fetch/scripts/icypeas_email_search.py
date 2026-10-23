#!/usr/bin/env python3
"""Find work emails for a contacts CSV with Icypeas: submit one search per person, then poll for results.

Icypeas is asynchronous (docs/icypeas-api-reference.md): a search call only returns a search id.
This script submits, saves each id, then polls the results route until every search reaches a
final status. Polling is capped by Icypeas at 30 calls/min, so it reads up to 100 results per call.
The script holds no run values: the input file, its column names and the output file are flags.

Sample, then scale:
    S=.claude/skills/icypeas-email-fetch/scripts/icypeas_email_search.py
    python3 $S --probe --account-email YOU@COMPANY.COM                                 # key + credits check, free
    python3 $S --contacts IN.csv --output data/processed/contacts_email_enriched_<date>.csv \
      --first-name-column first_name --last-name-column last_name \
      --domain-column company_domain --id-column person_linkedin_url \
      --limit 5 --dry-run                                                              # show requests, no calls
    python3 $S ...same flags... --limit 5                                              # sample: 5 people
    python3 $S ...same flags... --resume --limit 50                                    # next 50
    python3 $S ...same flags... --resume                                               # everyone left

Input:  any contacts CSV; --id-column must be unique per person (it joins results back to the database)
Writes (appended as each search finishes; --resume never resubmits a person already submitted):
    --output                                  input columns + the RESULT_COLUMNS below (one file, appended each run)
    data/raw/<output name>.jsonl              one line per finished search: our id + the API item, untouched
    data/raw/<output name>.state.json         submitted search ids and finished people (resume point)
Credits: 1 per email found; a search with no email costs nothing.
Run log: logs/icypeas_email_search.log. Failed calls: logs/icypeas_email_search_errors.log.
"""
import argparse
import csv
import json
import logging
import math
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
LOG_FILE = ROOT / "logs" / "icypeas_email_search.log"
ERROR_LOG = ROOT / "logs" / "icypeas_email_search_errors.log"

# Icypeas API facts (docs/icypeas-api-reference.md), not run settings.
SEARCH_URL = "https://app.icypeas.com/api/email-search"
READ_URL = "https://app.icypeas.com/api/bulk-single-searchs/read"
SUBSCRIPTION_URL = "https://app.icypeas.com/api/a/actions/subscription-information"
MAX_SUBMIT_RPS = 10      # /email-search limit
MAX_READS_PER_MIN = 30   # /bulk-single-searchs/read limit (polling)
READ_PAGE = 100          # max results per read call
FIRST_POLL_AFTER = 5     # Icypeas: wait a few seconds before the first read
FINAL_STATUSES = {"FOUND", "DEBITED", "NOT_FOUND", "DEBITED_NOT_FOUND",
                  "BAD_INPUT", "INSUFFICIENT_FUNDS", "ABORTED"}
CERTAINTY_RANK = {"ultra_sure": 3, "very_sure": 3, "probable": 2}  # picks one email if several come back

# email_* columns are named after gtm.contacts (migration 004), so the loader maps them 1:1.
RESULT_COLUMNS = ["email", "email_status", "email_mx_provider", "email_enriched_at", "email_search_id",
                  "email_provider_status", "email_certainty", "emails_found", "raw"]


class RateLimiter:
    """At most one request start per `interval` seconds."""

    def __init__(self, interval):
        self.interval = interval
        self.next_at = 0.0

    def wait(self):
        now = time.monotonic()
        time.sleep(max(0.0, self.next_at - now))
        self.next_at = max(now, self.next_at) + self.interval


def env_get(key):
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env (expected a line starting {key}=)")


def log_error(code, message, body):
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "code": code,
            "message": message,
            "request": body,
        }) + "\n")


def post(api_key, url, body, limiter, label, attempts=3):
    """Return the parsed response, or None after logging the error (never raises).
    Icypeas reports validation errors as HTTP 200 with success: false, so callers check `success`."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, attempts + 1):
        limiter.wait()
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            code, message = e.code, e.read().decode(errors="replace")[:1000]
        except (urllib.error.URLError, TimeoutError) as e:
            # A timed-out search is not retried: Icypeas may already have queued it.
            log_error("network", str(e), body)
            return None
        if code in (429, 500, 503) and attempt < attempts:
            wait = 60 if code == 429 else 2 ** attempt
            logging.warning("HTTP %s for %s, retrying in %ss", code, label, wait)
            time.sleep(wait)
            continue
        log_error(code, message, body)
        return None


def load_state(path):
    if path.is_file():
        return json.loads(path.read_text())
    return {"contacts": None, "submitted": {}, "done": []}


def save_state(path, state):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1))
    tmp.replace(path)


def best_email(item):
    emails = (item.get("results") or {}).get("emails") or []
    if not emails:
        return {}, 0
    best = max(emails, key=lambda e: CERTAINTY_RANK.get(e.get("certainty"), 0))
    return best, len(emails)


def items_of(resp):
    """The read route's list of search items (list reads use `items`; tolerate `item` too)."""
    if not resp or not resp.get("success"):
        return []
    if isinstance(resp.get("items"), list):
        return resp["items"]
    return [resp["item"]] if isinstance(resp.get("item"), dict) else []


def read_round(api_key, waiting_ids, limiter):
    """One polling round. Few searches: read each by id. Many: page through recent single
    email searches, 100 per call, and stop once every waiting id has been seen."""
    if len(waiting_ids) <= 3:
        found = []
        for sid in waiting_ids:
            found += items_of(post(api_key, READ_URL, {"id": sid}, limiter, f"read {sid}"))
        return found
    found, sorts = [], None
    max_pages = math.ceil(len(waiting_ids) / READ_PAGE) + 2  # our searches are the newest
    for _ in range(max_pages):
        body = {"mode": "single", "type": "email-search", "limit": READ_PAGE}
        if sorts:
            body.update(next=True, sorts=sorts)
        resp = post(api_key, READ_URL, body, limiter, "read page")
        page = items_of(resp)
        if not page:
            break
        found += [i for i in page if i.get("_id") in waiting_ids]
        if waiting_ids <= {i.get("_id") for i in found}:
            break
        sorts = resp.get("sorts")
        if not sorts:
            break
    return found


def credit_fields(obj, path=""):
    """Every number in the subscription response whose key mentions credits, as (path, value)."""
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else k
            if isinstance(v, (int, float)) and not isinstance(v, bool) and "credit" in here.lower():
                found.append((here, v))
            else:
                found += credit_fields(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found += credit_fields(v, f"{path}[{i}]")
    return found


def main():
    global ENV_FILE
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--contacts", help="contacts CSV to enrich")
    parser.add_argument("--output", help="results CSV, appended each run (e.g. data/processed/contacts_email_enriched_<date>.csv)")
    parser.add_argument("--first-name-column", help="input column holding the first name")
    parser.add_argument("--last-name-column", help="input column holding the last name")
    parser.add_argument("--domain-column", help="input column holding the company domain (or company name)")
    parser.add_argument("--id-column", help="input column unique per person, used to join results back")
    parser.add_argument("--limit", type=int, help="submit at most N new people this run (sample / next batch)")
    parser.add_argument("--resume", action="store_true", help="continue a run: poll what's pending, submit the rest")
    parser.add_argument("--dry-run", action="store_true", help="print the requests; call nothing")
    parser.add_argument("--probe", action="store_true", help="check the API key (and credits with --account-email), then exit")
    parser.add_argument("--account-email", help="--probe: the Icypeas account's login email, to read the credit balance")
    parser.add_argument("--submit-rps", type=float, default=5, help=f"searches sent per second (max {MAX_SUBMIT_RPS})")
    parser.add_argument("--reads-per-min", type=float, default=27, help=f"polling reads per minute (max {MAX_READS_PER_MIN})")
    parser.add_argument("--poll-every", type=int, default=10, help="seconds between polling rounds")
    parser.add_argument("--max-wait", type=int, default=600, help="seconds to poll before saving and exiting")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    if not 0 < args.submit_rps <= MAX_SUBMIT_RPS:
        parser.error(f"--submit-rps must be above 0 and at most {MAX_SUBMIT_RPS} (Icypeas limit)")
    if not 0 < args.reads_per_min <= MAX_READS_PER_MIN:
        parser.error(f"--reads-per-min must be above 0 and at most {MAX_READS_PER_MIN} (Icypeas limit)")
    read_limiter = RateLimiter(60 / args.reads_per_min)

    if args.probe:
        resp = post(env_get("ICYPEAS_API_KEY"), READ_URL, {"mode": "single", "limit": 1},
                    read_limiter, "probe", attempts=1)
        ok = bool(resp and resp.get("success"))
        logging.info("Icypeas key: %s", "PASS" if ok else f"FAIL (see {ERROR_LOG.relative_to(ROOT)})")
        if ok and args.account_email:
            sub = post(env_get("ICYPEAS_API_KEY"), SUBSCRIPTION_URL, {"email": args.account_email},
                       read_limiter, "subscription", attempts=1)
            credits = credit_fields(sub) if sub and sub.get("success") else []
            if credits:
                for name, value in credits:
                    logging.info("Icypeas credits: %s = %s", name, value)
            else:
                ok = False
                logging.info("Icypeas credits: FAIL, no credit balance returned (see %s)", ERROR_LOG.relative_to(ROOT))
                if sub:
                    log_error("subscription", json.dumps(sub)[:1000], {"email": "<account email>"})
        sys.exit(0 if ok else 1)

    # No defaults: a forgotten flag stops the run instead of guessing.
    columns = {"first": args.first_name_column, "last": args.last_name_column,
               "domain": args.domain_column, "id": args.id_column}
    missing_flags = [f for f, v in [("--contacts", args.contacts), ("--output", args.output),
                                    ("--first-name-column", columns["first"]), ("--last-name-column", columns["last"]),
                                    ("--domain-column", columns["domain"]), ("--id-column", columns["id"])] if not v]
    if missing_flags:
        parser.error("missing " + ", ".join(missing_flags) + " (all are required unless --probe)")

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    raw_dir = ROOT / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"{out_path.stem}.jsonl"
    state_path = raw_dir / f"{out_path.stem}.state.json"

    with open(args.contacts, newline="") as f:
        reader = csv.DictReader(f)
        in_columns = reader.fieldnames
        missing = [c for c in columns.values() if c not in in_columns]
        if missing:
            sys.exit(f"{args.contacts} has no column(s): {', '.join(missing)}. Columns: {', '.join(in_columns)}")
        clash = [c for c in RESULT_COLUMNS if c in in_columns]
        if clash:
            sys.exit(f"{args.contacts} already has result column(s) {', '.join(clash)}: pass the un-enriched list")
        rows, duplicates = {}, 0
        for r in reader:
            k = r[columns["id"]].strip()
            if not k:
                continue
            duplicates += k in rows
            rows[k] = r
    if duplicates:
        sys.exit(f"--id-column {columns['id']} is not unique ({duplicates} repeats): pick a column unique per person")

    state = load_state(state_path)
    if state["submitted"] and not args.resume and not args.dry_run:
        sys.exit(f"{state_path.relative_to(ROOT)} already has {len(state['submitted'])} submitted searches. "
                 "Re-run with --resume to continue it (nothing is resubmitted).")
    if state["contacts"] and state["contacts"] != str(args.contacts):
        sys.exit(f"This run was started on {state['contacts']}, not {args.contacts}. Use another --output.")

    to_submit = [k for k in rows if k not in state["submitted"]]
    if args.limit is not None:
        to_submit = to_submit[:args.limit]

    def body_for(row):
        return {"firstname": row[columns["first"]].strip(), "lastname": row[columns["last"]].strip(),
                "domainOrCompany": row[columns["domain"]].strip(),
                "custom": {"externalId": row[columns["id"]].strip()}}

    if args.dry_run:
        print(f"DRY RUN: would submit {len(to_submit)} searches (max {len(to_submit)} credits) "
              f"and poll {len(state['submitted']) - len(state['done'])} pending. "
              f"{len(rows) - len(state['submitted'])} of {len(rows)} people not yet submitted. No calls made.")
        for k in to_submit:
            print(json.dumps(body_for(rows[k])))
        return

    api_key = env_get("ICYPEAS_API_KEY")
    state["contacts"] = str(args.contacts)
    submit_limiter = RateLimiter(1 / args.submit_rps)
    errors = 0

    # 1. Submit. Each id is saved the moment it comes back.
    for k in to_submit:
        body = body_for(rows[k])
        resp = post(api_key, SEARCH_URL, body, submit_limiter, k)
        if not resp:
            errors += 1
            continue
        if not resp.get("success"):
            log_error("validation", json.dumps(resp.get("validationErrors"))[:1000], body)
            errors += 1
            continue
        state["submitted"][k] = {"id": resp["item"]["_id"], "at": time.strftime("%Y-%m-%d %H:%M:%S")}
        save_state(state_path, state)
    logging.info("submitted %d searches (%d errors)", len(to_submit) - errors, errors)

    # 2. Poll until every submitted search is final, streaming each result as it finishes.
    done = set(state["done"])
    waiting = {v["id"]: k for k, v in state["submitted"].items() if k not in done}
    new_file = not out_path.is_file()
    deadline = time.monotonic() + args.max_wait
    counts = {}
    with open(out_path, "a", newline="") as out_f, open(raw_path, "a") as raw_f:
        writer = csv.DictWriter(out_f, fieldnames=in_columns + RESULT_COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        if waiting:
            time.sleep(FIRST_POLL_AFTER)
        while waiting and time.monotonic() < deadline:
            for item in read_round(api_key, set(waiting), read_limiter):
                sid, status = item.get("_id"), item.get("status")
                if sid not in waiting or status not in FINAL_STATUSES:
                    continue
                k = waiting.pop(sid)
                email, n = best_email(item)
                raw_f.write(json.dumps({"id": k, "search_id": sid, "item": item}) + "\n")
                raw_f.flush()
                writer.writerow({**rows.get(k, {columns["id"]: k}),
                                 "email": email.get("email", ""),
                                 "email_status": "found" if email.get("email") else "not_found",
                                 "email_mx_provider": email.get("mxProvider", ""),
                                 "email_enriched_at": (item.get("system") or {}).get("modifiedAt", ""),
                                 "email_search_id": sid, "email_provider_status": status,
                                 "email_certainty": email.get("certainty", ""), "emails_found": n,
                                 "raw": json.dumps(item, separators=(",", ":"))})
                out_f.flush()
                state["done"].append(k)
                save_state(state_path, state)
                counts[status] = counts.get(status, 0) + 1
            if waiting:
                logging.info("%d searches still running; next check in %ss", len(waiting), args.poll_every)
                time.sleep(args.poll_every)

    logging.info("finished %d searches: %s", sum(counts.values()),
                 ", ".join(f"{s} {n}" for s, n in sorted(counts.items())) or "none")
    if waiting:
        logging.warning("%d searches not finished after %ss. Re-run with --resume to keep polling "
                        "(nothing is resubmitted).", len(waiting), args.max_wait)
    logging.info("errors this run: %d%s", errors, f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "")
    logging.info("progress: %d of %d people done; results: %s", len(state["done"]), len(rows),
                 out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path)


if __name__ == "__main__":
    main()
