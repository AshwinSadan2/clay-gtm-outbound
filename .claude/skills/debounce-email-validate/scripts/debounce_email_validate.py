#!/usr/bin/env python3
"""Validate emails in a CSV with Debounce: one synchronous call per email, a few at a time.

Debounce answers each call directly (docs/debounce-api-reference.md), so there is no polling. Calls run
in parallel up to --concurrency (Debounce allows 5 at once). Each answer is written the moment it arrives.
The script holds no run values: the input file, its column names and the output file are flags.

Sample, then scale:
    S=.claude/skills/debounce-email-validate/scripts/debounce_email_validate.py
    python3 $S --probe                                                                 # key + credit balance, free
    python3 $S --input data/processed/contacts_email_enriched_<date>.csv \
      --output data/processed/contacts_email_validated_<date>.csv \
      --email-column email --id-column person_linkedin_url --limit 5 --dry-run           # show the emails, no calls
    python3 $S ...same flags... --limit 5                                              # sample: 5 emails
    python3 $S ...same flags... --resume --limit 95                                    # next batch
    python3 $S ...same flags... --resume                                               # everyone left

Input:  any CSV with an email column; rows with no email are skipped. --id-column must be unique per person.
Writes (appended as each answer arrives; --resume never re-validates a person already done):
    --output                                  input columns + the RESULT_COLUMNS below (one file, appended each run)
    data/raw/<output name>.jsonl              one line per answer: our id + the API response, untouched
    data/raw/<output name>.state.json         people done (resume point)
Credits: 1 per validation. A run never starts more validations than the balance covers, and stops on 402.
Run log: logs/debounce_email_validate.log. Failed calls: logs/debounce_email_validate_errors.log.
"""
import argparse
import csv
import json
import logging
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
LOG_FILE = ROOT / "logs" / "debounce_email_validate.log"
ERROR_LOG = ROOT / "logs" / "debounce_email_validate_errors.log"

# Debounce API facts (docs/debounce-api-reference.md), not run settings.
VALIDATE_URL = "https://api.debounce.io/v1/"
BALANCE_URL = "https://api.debounce.io/v1/balance/"
MAX_CONCURRENCY = 5  # concurrent calls per account (2 with data enrichment, which this script never asks for)

# email_validation / email_validation_at are named after gtm.contacts (migration 004); the rest stay in the CSV.
RESULT_COLUMNS = ["email_validation", "email_validation_at", "email_validation_reason", "email_validation_code",
                  "email_role", "email_free", "email_send_transactional", "email_did_you_mean", "validation_raw"]

csv.field_size_limit(10_000_000)  # raw JSON cells


class OutOfCredits(Exception):
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
            "request": request,  # never the URL: it carries the API key
        }) + "\n")


def get(api_key, url, params, label, attempts=4):
    """Return the parsed response, or None after logging the error. Raises OutOfCredits on 402."""
    full = url + "?" + urllib.parse.urlencode({**params, "api": api_key})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(full, timeout=60) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            code, message = e.code, e.read().decode(errors="replace")[:1000].replace(api_key, "***")
        except (urllib.error.URLError, TimeoutError) as e:
            # Not retried: Debounce may already have charged for the call.
            log_error("network", str(e).replace(api_key, "***"), params)
            return None
        if code == 402:
            log_error(code, message, params)
            raise OutOfCredits(message)
        if code in (429, 500, 503) and attempt < attempts:
            pause = 5 * attempt if code == 429 else 2 ** attempt
            logging.warning("HTTP %s for %s, retrying in %ss", code, label, pause)
            time.sleep(pause)
            continue
        log_error(code, message, params)
        return None


def balance(api_key):
    resp = get(api_key, BALANCE_URL, {}, "balance", attempts=1)
    try:
        return int(resp["balance"])
    except (TypeError, KeyError, ValueError):
        return None


def load_state(path):
    if path.is_file():
        return json.loads(path.read_text())
    return {"input": None, "done": []}


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
    parser.add_argument("--input", help="CSV holding the emails to validate")
    parser.add_argument("--output", help="results CSV, appended each run (e.g. data/processed/contacts_email_validated_<date>.csv)")
    parser.add_argument("--email-column", help="input column holding the email")
    parser.add_argument("--id-column", help="input column unique per person, used to join results back")
    parser.add_argument("--limit", type=int, help="validate at most N new emails this run (sample / next batch)")
    parser.add_argument("--resume", action="store_true", help="continue a run: validate the emails not done yet")
    parser.add_argument("--dry-run", action="store_true", help="print the emails; call nothing")
    parser.add_argument("--probe", action="store_true", help="check the API key and credit balance, then exit")
    parser.add_argument("--concurrency", type=int, default=3, help=f"calls at once (max {MAX_CONCURRENCY})")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    if not 0 < args.concurrency <= MAX_CONCURRENCY:
        parser.error(f"--concurrency must be 1 to {MAX_CONCURRENCY} (Debounce limit)")

    if args.probe:
        credits = balance(env_get("DEBOUNCE_API_KEY"))
        if credits is None:
            logging.info("Debounce key: FAIL (see %s)", ERROR_LOG.relative_to(ROOT))
            sys.exit(1)
        logging.info("Debounce key: PASS")
        logging.info("Debounce credits: %d", credits)
        return

    # No defaults: a forgotten flag stops the run instead of guessing.
    missing_flags = [f for f, v in [("--input", args.input), ("--output", args.output),
                                    ("--email-column", args.email_column), ("--id-column", args.id_column)] if not v]
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

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        in_columns = reader.fieldnames
        missing = [c for c in [args.email_column, args.id_column] if c not in in_columns]
        if missing:
            sys.exit(f"{args.input} has no column(s): {', '.join(missing)}. Columns: {', '.join(in_columns)}")
        clash = [c for c in RESULT_COLUMNS if c in in_columns]
        if clash:
            sys.exit(f"{args.input} already has result column(s) {', '.join(clash)}: pass the un-validated list")
        rows, duplicates, no_email = {}, 0, 0
        for r in reader:
            k = r[args.id_column].strip()
            if not k:
                continue
            if not r[args.email_column].strip():
                no_email += 1
                continue
            duplicates += k in rows
            rows[k] = r
    if duplicates:
        sys.exit(f"--id-column {args.id_column} is not unique ({duplicates} repeats): pick a column unique per person")

    state = load_state(state_path)
    if state["done"] and not args.resume and not args.dry_run:
        sys.exit(f"{state_path.relative_to(ROOT)} already has {len(state['done'])} validated emails. "
                 "Re-run with --resume to continue it (nothing is re-validated).")
    if state["input"] and state["input"] != str(args.input):
        sys.exit(f"This run was started on {state['input']}, not {args.input}. Use another --output.")

    done = set(state["done"])
    todo = [k for k in rows if k not in done]
    if args.limit is not None:
        todo = todo[:args.limit]

    if args.dry_run:
        print(f"DRY RUN: would validate {len(todo)} emails ({len(todo)} credits). {len(rows) - len(done)} of "
              f"{len(rows)} emails not yet validated; {no_email} rows have no email and are skipped. No calls made.")
        for k in todo:
            print(rows[k][args.email_column].strip())
        return

    api_key = env_get("DEBOUNCE_API_KEY")
    credits = balance(api_key)
    if credits is None:
        sys.exit(f"Could not read the Debounce balance (see {ERROR_LOG.relative_to(ROOT)}). Nothing validated.")
    if credits < len(todo):
        logging.warning("only %d credits for %d emails: validating the first %d", credits, len(todo), credits)
        todo = todo[:credits]
    state["input"] = str(args.input)

    stop = threading.Event()

    def validate(k):
        if stop.is_set():
            return k, None
        try:
            return k, get(api_key, VALIDATE_URL, {"email": rows[k][args.email_column].strip()}, k)
        except OutOfCredits:
            stop.set()
            return k, None

    new_file = not out_path.is_file()
    counts, errors = {}, 0
    with open(out_path, "a", newline="") as out_f, open(raw_path, "a") as raw_f, \
            ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        writer = csv.DictWriter(out_f, fieldnames=in_columns + RESULT_COLUMNS, extrasaction="ignore")
        if new_file:
            writer.writeheader()
        queue, running = list(todo), set()
        while queue or running:
            while queue and len(running) < args.concurrency and not stop.is_set():
                running.add(pool.submit(validate, queue.pop(0)))
            if not running:
                break
            finished, running = wait(running, return_when=FIRST_COMPLETED)
            for future in finished:
                k, resp = future.result()
                result = (resp or {}).get("debounce") or {}
                if not resp or str(resp.get("success")) != "1" or not result.get("result"):
                    if resp is None and stop.is_set():
                        continue  # not validated: credits ran out; --resume picks it up
                    if resp:
                        log_error("api", json.dumps(resp)[:1000], {"email": rows[k][args.email_column].strip()})
                    errors += 1
                    continue
                raw_f.write(json.dumps({"id": k, "response": resp}) + "\n")
                raw_f.flush()
                writer.writerow({**rows[k],
                                 "email_validation": result["result"],
                                 "email_validation_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 "email_validation_reason": result.get("reason", ""),
                                 "email_validation_code": result.get("code", ""),
                                 "email_role": result.get("role", ""),
                                 "email_free": result.get("free_email", ""),
                                 "email_send_transactional": result.get("send_transactional", ""),
                                 "email_did_you_mean": result.get("did_you_mean", ""),
                                 "validation_raw": json.dumps(resp, separators=(",", ":"))})
                out_f.flush()
                state["done"].append(k)
                save_state(state_path, state)
                counts[result["result"]] = counts.get(result["result"], 0) + 1

    logging.info("validated %d emails: %s", sum(counts.values()),
                 ", ".join(f"{s} {n}" for s, n in sorted(counts.items())) or "none")
    if stop.is_set():
        logging.warning("stopped: Debounce credits ran out (HTTP 402). Add credits, then re-run with --resume.")
    logging.info("errors this run: %d%s", errors, f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "")
    logging.info("credits left: %s", balance(api_key))
    logging.info("progress: %d of %d emails done; results: %s", len(state["done"]), len(rows),
                 out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path)


if __name__ == "__main__":
    main()
