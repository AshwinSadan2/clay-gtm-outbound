#!/usr/bin/env python3
"""Find work emails for a contacts CSV with Icypeas: submit one search per person, then poll for results.

Icypeas is asynchronous (docs/icypeas-api-reference.md): a search call only returns a search id.
This script submits, saves each id, then polls the results route until every search reaches a
final status. Polling is capped by Icypeas at 30 calls/min, so it reads up to 100 results per call.

Sample, then scale:
    python3 .claude/skills/enrich-emails/scripts/icypeas_email_search.py --probe          # key check, free
    python3 .claude/skills/enrich-emails/scripts/icypeas_email_search.py \
      --contacts data/processed/contacts_clean_2026-10-23.csv --limit 5 --dry-run        # show requests, no calls
    python3 .claude/skills/enrich-emails/scripts/icypeas_email_search.py \
      --contacts data/processed/contacts_clean_2026-10-23.csv --limit 5                  # sample: 5 people
    python3 .claude/skills/enrich-emails/scripts/icypeas_email_search.py \
      --contacts data/processed/contacts_clean_2026-10-23.csv --resume                   # scale: everyone left

Input:  any contacts CSV with first_name, last_name, company_domain, person_linkedin_url columns
Writes (appended as each search finishes; --resume never resubmits a person already submitted):
    data/raw/emails_icypeas_<date>.jsonl         one line per finished search: our id + the API item, untouched
    data/raw/emails_icypeas_<date>.state.json    submitted search ids and finished people (resume point)
    data/processed/contacts_email_enriched_<date>.csv   input columns + email, certainty, status, raw (one file, appended each run)
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
from datetime import date
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
SEARCH_URL = "https://app.icypeas.com/api/email-search"
READ_URL = "https://app.icypeas.com/api/bulk-single-searchs/read"
LOG_FILE = ROOT / "logs" / "icypeas_email_search.log"
ERROR_LOG = ROOT / "logs" / "icypeas_email_search_errors.log"

REQUIRED_COLUMNS = ["first_name", "last_name", "company_domain", "person_linkedin_url"]
RESULT_COLUMNS = ["email", "email_certainty", "email_mx_provider", "emails_found",
                  "icypeas_status", "icypeas_search_id", "raw"]
FINAL_STATUSES = {"FOUND", "DEBITED", "NOT_FOUND", "DEBITED_NOT_FOUND",
                  "BAD_INPUT", "INSUFFICIENT_FUNDS", "ABORTED"}
CERTAINTY_RANK = {"ultra_sure": 3, "very_sure": 3, "probable": 2}
READ_PAGE = 100          # max results per read call
SUBMIT_RPS = 5           # Icypeas allows 10/s on /email-search; stay at half
READ_INTERVAL = 2.2      # Icypeas allows 30 reads/min = one per 2 s; keep a margin


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
    parser.add_argument("--limit", type=int, help="submit at most N new people this run (the sample)")
    parser.add_argument("--resume", action="store_true", help="continue a run: poll what's pending, submit the rest")
    parser.add_argument("--dry-run", action="store_true", help="print the requests; call nothing")
    parser.add_argument("--probe", action="store_true", help="one free read call to check the API key, then exit")
    parser.add_argument("--date", default=date.today().isoformat(), help="output file date (default today; "
                        "pass the original date to --resume a run started on another day)")
    parser.add_argument("--max-wait", type=int, default=600, help="seconds to poll before saving and exiting")
    parser.add_argument("--poll-every", type=int, default=10, help="seconds between polling rounds")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()

    if args.probe:
        resp = post(env_get("ICYPEAS_API_KEY"), READ_URL, {"mode": "single", "limit": 1},
                    RateLimiter(READ_INTERVAL), "probe", attempts=1)
        ok = bool(resp and resp.get("success"))
        logging.info("Icypeas key: %s", "PASS" if ok else f"FAIL (see {ERROR_LOG.relative_to(ROOT)})")
        sys.exit(0 if ok else 1)

    if not args.contacts:
        parser.error("--contacts is required (unless --probe)")
    raw_dir, out_dir = ROOT / "data" / "raw", ROOT / "data" / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"emails_icypeas_{args.date}.jsonl"
    state_path = raw_dir / f"emails_icypeas_{args.date}.state.json"
    out_path = out_dir / f"contacts_email_enriched_{args.date}.csv"

    with open(args.contacts, newline="") as f:
        reader = csv.DictReader(f)
        in_columns = reader.fieldnames
        missing = [c for c in REQUIRED_COLUMNS if c not in in_columns]
        if missing:
            sys.exit(f"{args.contacts} is missing columns: {', '.join(missing)}")
        rows = {r["person_linkedin_url"]: r for r in reader if r["person_linkedin_url"]}

    state = load_state(state_path)
    if state["submitted"] and not args.resume and not args.dry_run:
        sys.exit(f"{state_path.relative_to(ROOT)} already has {len(state['submitted'])} submitted searches. "
                 "Re-run with --resume to continue it (nothing is resubmitted).")
    if state["contacts"] and state["contacts"] != str(args.contacts):
        sys.exit(f"This run was started on {state['contacts']}, not {args.contacts}. Use another --date.")

    to_submit = [k for k in rows if k not in state["submitted"]]
    if args.limit is not None:
        to_submit = to_submit[:args.limit]

    def body_for(row):
        return {"firstname": row["first_name"].strip(), "lastname": row["last_name"].strip(),
                "domainOrCompany": row["company_domain"].strip(),
                "custom": {"externalId": row["person_linkedin_url"]}}

    if args.dry_run:
        print(f"DRY RUN: would submit {len(to_submit)} searches (max {len(to_submit)} credits) "
              f"and poll {len(state['submitted']) - len(state['done'])} pending. No calls made.")
        for k in to_submit:
            print(json.dumps(body_for(rows[k])))
        return

    api_key = env_get("ICYPEAS_API_KEY")
    state["contacts"] = str(args.contacts)
    submit_limiter, read_limiter = RateLimiter(1 / SUBMIT_RPS), RateLimiter(READ_INTERVAL)
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
            time.sleep(5)  # Icypeas: wait a few seconds before the first read
        while waiting and time.monotonic() < deadline:
            for item in read_round(api_key, set(waiting), read_limiter):
                sid, status = item.get("_id"), item.get("status")
                if sid not in waiting or status not in FINAL_STATUSES:
                    continue
                k = waiting.pop(sid)
                email, n = best_email(item)
                raw_f.write(json.dumps({"person_linkedin_url": k, "search_id": sid, "item": item}) + "\n")
                raw_f.flush()
                writer.writerow({**rows.get(k, {"person_linkedin_url": k}),
                                 "email": email.get("email", ""), "email_certainty": email.get("certainty", ""),
                                 "email_mx_provider": email.get("mxProvider", ""), "emails_found": n,
                                 "icypeas_status": status, "icypeas_search_id": sid,
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
    logging.info("results: %s", out_path.relative_to(ROOT))


if __name__ == "__main__":
    main()
