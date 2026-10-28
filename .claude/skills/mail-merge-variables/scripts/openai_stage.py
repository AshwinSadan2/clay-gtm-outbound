#!/usr/bin/env python3
"""Run ONE prompt over every row of a CSV with OpenAI and write its answer to a column. One call per row.

The script does not know about pipelines or stage numbers. A multi-stage pipeline is several runs, each with
its own prompt file; a later prompt reads what an earlier run wrote by naming that column as a {{variable}}
(or mapping it with --var). The script holds no prompt text and no campaign values.

Prompt file (Markdown, versioned by file name, e.g. stage2_compose_v3.md):
    **Model:** ... (`gpt-6-luna`)          required
    **Output field:** `opener`             required: the JSON field the model must return
    **Effort:** none                       optional reasoning effort (none = log-probability confidence)
    **Temperature:** 1.0                   optional, only with effort none (OpenAI refuses it otherwise)
    **Top p:** 0.98                        optional, same rule
    **Max output tokens:** 1000            optional (default 1000)
    ## Variant A ... ### System ... ### User ...   one section per variant, or a single "## Prompt" section
Every setting can be overridden for a run (--model, --effort, --temperature, --top-p, --max-output-tokens);
the settings actually used are written to the row. {{variables}} are filled from the CSV's columns of the same
name, or from the column --var NAME=COLUMN points to. API facts: docs/openai-api-reference.md.

    S=.claude/skills/mail-merge-variables/scripts/openai_stage.py
    F=(--input data/processed/mailable_contacts_<date>.csv --prompt docs/prompts/stage1_insight_v2.md
       --output-column insight --variant-when "A:about_me>=50" --variant-default B --checks review)
    python3 $S --probe "${F[@]}"              # key, model, settings combination (free)
    python3 $S "${F[@]}" --limit 1 --dry-run  # print the exact prompt for the next row, no calls
    python3 $S "${F[@]}" --limit 1            # one row
    python3 $S "${F[@]}" --resume             # everyone left (never re-pays for a row done with these settings)

Writes:
    data/raw/llm_<input name>__<column>.jsonl  one line per row as it arrives: id, variant, request settings,
                                               the full API response (never the key). This is the resume point.
    --output (default: --input, updated in place, every --csv-every seconds and at the end):
        <column>                      the answer
        <column>_variant              which prompt section ran
        <column>_input_tokens / _output_tokens / _cost_usd
        <column>_confidence           exp(mean log-probability) of the answer's own tokens (effort none only)
        <column>_flags                rule checks (--checks); flag, never fix
        <column>_settings / _prompt / _at
        cost_usd_total                sum of every *_cost_usd column in the row (all runs so far)
Checks: dash · words (--max-words) · list · dated · question · greeting (needs --first-name-column) · review
(--review-phrases). --fail-on CHECKS makes those hard fails: the call is retried (--fail-retries), and if it
still fails the row is left empty, marked not done, and retried by the next --resume.
Run log: logs/openai_stage.log. Failed calls: logs/openai_stage_errors.log.
"""
import argparse
import csv
import json
import logging
import math
import os
import random
import re
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
LOG_FILE = ROOT / "logs" / "openai_stage.log"
ERROR_LOG = ROOT / "logs" / "openai_stage_errors.log"

# OpenAI API facts (docs/openai-api-reference.md), not run settings.
RESPONSES_URL = "https://api.openai.com/v1/responses"
MODELS_URL = "https://api.openai.com/v1/models"
RETRY_CODES = {429, 500, 503}
# USD per 1M tokens: (input, cached input, output). Standard tier, read 2026-10-28. --price overrides.
PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
}
ALL_CHECKS = ["dash", "words", "list", "dated", "question", "greeting", "review"]
SUFFIXES = ["variant", "input_tokens", "output_tokens", "cost_usd", "confidence", "flags", "settings", "prompt", "at"]

csv.field_size_limit(10_000_000)
_error_lock = threading.Lock()


class StopRun(Exception):
    """Billing/quota problem: retrying cannot fix it."""


# ---------- prompt file ----------

def load_prompt(path):
    """Markdown prompt file -> {"version", "model", "field", "settings": {...}, "sections": {name: {system, user}}}."""
    text = Path(path).read_text()

    def line(name):
        m = re.search(rf"^\*\*{name}:\*\*\s*(.+?)\s*$", text, re.M | re.I)
        return m.group(1) if m else None

    def ticked(name):
        v = line(name)
        m = re.search(r"`([^`]+)`", v or "")
        if not m:
            sys.exit(f"{path}: needs a '**{name}:** ... `value`' line")
        return m.group(1)

    def number(name, cast):
        v = line(name)
        m = re.match(r"[-\d.]+", v or "")
        return cast(m.group(0)) if m else None

    effort = line("Effort")
    sections = {}
    for m in re.finditer(r"^## (?:Variant (\w+)|Prompt)\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S):
        name, body = m.group(1) or "-", m.group(2)
        blocks = {}
        for role in ("System", "User"):
            b = re.search(rf"^### {role}\s*$(.*?)(?=^### |^---\s*$|\Z)", body, re.M | re.S)
            blocks[role.lower()] = b.group(1).strip() if b else ""
        if not blocks["user"]:
            sys.exit(f"{path}: section '{name}' has no '### User' block")
        sections[name] = blocks
    if not sections:
        sys.exit(f"{path}: no '## Variant X' or '## Prompt' section")
    return {"version": Path(path).stem, "model": ticked("Model"), "field": ticked("Output field"),
            "settings": {"effort": effort.split()[0].lower() if effort else None,
                         "temperature": number("Temperature", float), "top_p": number("Top p", float),
                         "max_output_tokens": number("Max output tokens", int)},
            "sections": sections}


def variables(prompt):
    return {v for s in prompt["sections"].values() for block in s.values() for v in re.findall(r"\{\{(\w+)\}\}", block)}


def fill(template, values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), ""), template)


def parse_when(text):
    """'A:about_me>=50' -> (variant, column, op, words): the variant runs when the column's word count passes."""
    m = re.fullmatch(r"\s*(\w+)\s*:\s*(\w+)\s*(>=|<=|>|<)\s*(\d+)\s*", text)
    if not m:
        raise argparse.ArgumentTypeError(f"--variant-when needs VARIANT:COLUMN>=WORDS, got {text!r}")
    return m.group(1), m.group(2), m.group(3), int(m.group(4))


def pick_variant(row, prompt, rules, default):
    if list(prompt["sections"]) == ["-"]:
        return "-"
    ops = {">=": int.__ge__, "<=": int.__le__, ">": int.__gt__, "<": int.__lt__}
    for variant, col, op, n in rules:
        if ops[op](len((row.get(col) or "").split()), n):
            return variant
    return default


# ---------- API ----------

def read_key(env_file):
    for ln in Path(env_file).read_text().splitlines():
        if ln.startswith("OPENAI_API_KEY="):
            return ln.split("=", 1)[1].strip()
    return ""


def log_error(row_id, code, message):
    with _error_lock, ERROR_LOG.open("a") as f:  # never the request headers: the key is in Authorization
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "id": row_id, "http": code,
                            "message": message}) + "\n")


def post(key, body, row_id, timeout, max_tries):
    """POST /v1/responses, retrying 429/500/503. Returns the JSON, or None after logging the failure."""
    for attempt in range(1, max_tries + 1):
        req = urllib.request.Request(RESPONSES_URL, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                err = json.load(e).get("error") or {}
            except Exception:
                err = {}
            code, msg = e.code, err.get("message", str(e))
            if err.get("code") == "insufficient_quota" or "spend limit" in msg.lower():
                log_error(row_id, code, msg)
                raise StopRun(f"{code} {err.get('code')}: {msg}")
            if code in RETRY_CODES and attempt < max_tries:
                wait_s = float(e.headers.get("Retry-After") or 2 ** attempt) + random.random()
                logging.warning("%s: HTTP %s, retry %d in %.1fs", row_id, code, attempt, wait_s)
                time.sleep(wait_s)
                continue
            log_error(row_id, code, msg)
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < max_tries:
                time.sleep(2 ** attempt + random.random())
                continue
            log_error(row_id, None, str(e))
            return None


def parse(resp, field):
    """Responses JSON -> (value, confidence, problem)."""
    if resp.get("status") != "completed":
        return None, None, f"status {resp.get('status')} {resp.get('incomplete_details')}"
    for item in resp.get("output", []):
        if item.get("type") != "message":
            continue
        for c in item.get("content", []):
            if c.get("type") == "refusal":
                return None, None, f"refusal: {c.get('refusal')}"
            if c.get("type") == "output_text":
                try:
                    value = str(json.loads(c["text"])[field]).strip()
                except (ValueError, KeyError):
                    return None, None, f"bad JSON: {c.get('text', '')[:200]}"
                return value, confidence(c.get("logprobs"), c["text"], field), None
    return None, None, "no text in output"


def confidence(logprobs, text, field):
    """exp(mean logprob) over the tokens inside the JSON string value (skips the forced {"field":" scaffolding)."""
    if not logprobs:
        return None
    start = text.find('"', text.find(":", text.find(f'"{field}"')) + 1) + 1
    end = text.rfind('"')
    pos, picked = 0, []
    for t in logprobs:
        tok_end = pos + len(t["token"])
        if tok_end > start and pos < end:
            picked.append(t["logprob"])
        pos = tok_end
    return round(math.exp(sum(picked) / len(picked)), 4) if picked else None


def usage_cost(price, usage):
    inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    if not price:
        return inp, out, None
    return inp, out, ((inp - cached) * price[0] + cached * price[1] + out * price[2]) / 1_000_000


def run_checks(value, checks, max_words, first_name, review_phrases):
    """-> list of (check, message). Flag, never fix."""
    found = []
    if not value:
        return [("empty", "empty")]
    if "dash" in checks and re.search(r"[—–]|\s-\s|\s-$|^-", value):
        found.append(("dash", "dash"))
    if "words" in checks and max_words and len(value.split()) > max_words:
        found.append(("words", f"{len(value.split())} words"))
    if "list" in checks and (value.count(",") >= 3 or re.search(r",[^,]+,[^,]+\band\b", value)):
        found.append(("list", "list"))
    if "dated" in checks and re.search(r"\b(19|20)\d\d\b", value):
        found.append(("dated", "dated"))
    if "question" in checks and "?" in value:
        found.append(("question", "question"))
    if "greeting" in checks and (re.match(r"(hey|hi|hello)\b", value, re.I)
                                 or (first_name and re.match(rf"{re.escape(first_name)}\b", value, re.I))):
        found.append(("greeting", "repeats greeting"))
    if "review" in checks and any(ph in value.lower().replace("’", "'") for ph in review_phrases):
        found.append(("review", "review: no clear link"))
    return found


def write_csv(path, fields, rows):
    fd, tmp = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


# ---------- run ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("input / output")
    g.add_argument("--input", required=True, help="CSV, one row per call")
    g.add_argument("--prompt", required=True, help="prompt .md (see the format above)")
    g.add_argument("--output", help="CSV to write (default: update --input in place)")
    g.add_argument("--output-column", help="column for the answer (default: the prompt's Output field)")
    g.add_argument("--var", action="append", default=[], metavar="NAME=COLUMN",
                   help="fill {{NAME}} from COLUMN (repeat)")
    g.add_argument("--id-column", default="person_linkedin_url", help="unique per row")
    g.add_argument("--raw", help="raw JSONL path (default: data/raw/llm_<input>__<column>.jsonl)")
    g = ap.add_argument_group("which rows")
    g.add_argument("--limit", type=int, help="rows this run")
    g.add_argument("--ids", help="file with one id per line: run only these rows")
    g.add_argument("--skip-column", action="append", default=[], help="skip rows where this column is filled (repeat)")
    g.add_argument("--require", action="append", default=[], help="skip rows where this column is empty (repeat)")
    g.add_argument("--resume", action="store_true", help="skip rows already done with these settings")
    g = ap.add_argument_group("variants")
    g.add_argument("--variant-when", action="append", type=parse_when, default=[],
                   help='"A:about_me>=50": first match wins (word count of the column)')
    g.add_argument("--variant-default", help="variant when no --variant-when matches")
    g = ap.add_argument_group("model settings (override the prompt file)")
    g.add_argument("--model")
    g.add_argument("--effort", help="none | minimal | low | medium | high | xhigh | max")
    g.add_argument("--temperature", type=float)
    g.add_argument("--top-p", type=float)
    g.add_argument("--max-output-tokens", type=int)
    g.add_argument("--price", help="IN,CACHED,OUT USD per 1M tokens, for a model the script has no price for")
    g = ap.add_argument_group("checks")
    g.add_argument("--checks", default=",".join(ALL_CHECKS), help=f"comma list from: {', '.join(ALL_CHECKS)}")
    g.add_argument("--max-words", action="append", default=[], metavar="[VARIANT=]N", help="words check limit")
    g.add_argument("--first-name-column", default="first_name", help="for the greeting check")
    g.add_argument("--review-phrases", default="unclear,doesn't describe,does not describe,no specific,not clear,"
                   "no clear,no direct,doesn't mention,does not mention,not mentioned")
    g.add_argument("--fail-on", default="", help="checks that block a row instead of flagging it")
    g.add_argument("--fail-retries", type=int, default=2, help="new calls for a row that hits --fail-on")
    g = ap.add_argument_group("run control")
    g.add_argument("--concurrency", type=int, default=25)
    g.add_argument("--max-cost", type=float, help="stop starting new rows once this run has spent this (USD)")
    g.add_argument("--timeout", type=int, default=120, help="seconds per call")
    g.add_argument("--max-tries", type=int, default=5, help="tries per call on 429/500/503")
    g.add_argument("--csv-every", type=float, default=5, help="rewrite the CSV at most every N seconds")
    g.add_argument("--dry-run", action="store_true", help="print the filled prompt, no calls")
    g.add_argument("--probe", action="store_true", help="check key, model and settings (free)")
    g.add_argument("--env", default=str(ENV_FILE))
    args = ap.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])

    # --- settings: prompt file, then overrides ---
    prompt = load_prompt(args.prompt)
    s = dict(prompt["settings"], model=prompt["model"])
    overridden = []
    for k in ("model", "effort", "temperature", "top_p", "max_output_tokens"):
        v = getattr(args, k)
        if v is not None:
            s[k] = v
            overridden.append(k)
    s["max_output_tokens"] = s["max_output_tokens"] or 1000
    if (s["temperature"] is not None or s["top_p"] is not None) and (s["effort"] or "medium") != "none":
        sys.exit("temperature/top_p only work with effort none (OpenAI refuses them with reasoning)")
    price = tuple(float(x) for x in args.price.split(",")) if args.price else PRICES.get(s["model"])
    settings_text = " ".join(f"{k}={s[k]}" for k in ("model", "effort", "temperature", "top_p", "max_output_tokens")
                             if s[k] is not None) + (f" (override: {', '.join(overridden)})" if overridden else "")

    checks = {c.strip() for c in args.checks.split(",") if c.strip()}
    fail_on = {c.strip() for c in args.fail_on.split(",") if c.strip()}
    for c in checks | fail_on:
        if c not in ALL_CHECKS:
            sys.exit(f"unknown check {c!r}: use {', '.join(ALL_CHECKS)}")
    checks |= fail_on
    max_words = {}
    for mw in args.max_words:
        v, _, n = mw.rpartition("=")
        max_words[v or "*"] = int(n)
    review_phrases = [p.strip().lower() for p in args.review_phrases.split(",") if p.strip()]
    varmap = dict(v.split("=", 1) for v in args.var)

    # --- rows and columns ---
    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    needed = {varmap.get(v, v) for v in variables(prompt)} | {args.id_column} | set(args.skip_column) \
        | set(args.require) | {c for _, c, _, _ in args.variant_when}
    if missing := needed - set(fields):
        sys.exit(f"columns not in {args.input}: {', '.join(sorted(missing))}")
    names = set(prompt["sections"])
    if names != {"-"}:
        used = {v for v, *_ in args.variant_when} | {args.variant_default}
        if not args.variant_default or used - names:
            sys.exit(f"prompt variants are {sorted(names)}: set --variant-when/--variant-default to those")
    col = args.output_column or prompt["field"]
    out_cols = [col] + [f"{col}_{x}" for x in SUFFIXES]
    fields += [c for c in out_cols + ["cost_usd_total"] if c not in fields]

    key = "" if args.dry_run else read_key(args.env)
    if not args.dry_run and not key:
        sys.exit(f"OPENAI_API_KEY is empty in {args.env}")

    if args.probe:
        req = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
        try:
            ids = {m["id"] for m in json.load(urllib.request.urlopen(req, timeout=30))["data"]}
        except urllib.error.HTTPError as e:
            sys.exit(f"probe FAILED: HTTP {e.code}")
        logging.info("probe: key OK | %s -> %s | %s | price %s | variants %s | output column %s",
                     prompt["version"], s["model"], "available" if s["model"] in ids else "NOT AVAILABLE",
                     price or "UNKNOWN (cost blank; use --price)", sorted(names), col)
        return

    raw = Path(args.raw) if args.raw else ROOT / "data" / "raw" / f"llm_{Path(args.input).stem}__{col}.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    run_key = f"{prompt['version']} | {settings_text}"
    done = {}
    if raw.exists():
        for ln in raw.read_text().splitlines():
            rec = json.loads(ln)
            if rec.get("ok") and rec.get("run_key") == run_key:  # new prompt version or settings -> not done
                done[rec["id"]] = rec
    if done and not args.resume and not args.dry_run:
        sys.exit(f"{len(done)} rows already done with {run_key} in {raw}: add --resume to continue")

    only = None
    if args.ids:
        only = {ln.strip() for ln in Path(args.ids).read_text().splitlines() if ln.strip()} - {args.id_column}
    todo = [r for r in rows if r[args.id_column] not in done
            and (only is None or r[args.id_column] in only)
            and not any((r.get(c) or "").strip() for c in args.skip_column)
            and all((r.get(c) or "").strip() for c in args.require)][: args.limit]
    logging.info("%s -> column %s | %d rows, %d done, %d this run | %s | concurrency %d",
                 prompt["version"], col, len(rows), len(done), len(todo), settings_text, args.concurrency)

    def body_for(row, variant):
        values = {v: row.get(varmap.get(v, v), "") for v in variables(prompt)}
        sec = prompt["sections"][variant]
        body = {"model": s["model"], "input": fill(sec["user"], values),
                "max_output_tokens": s["max_output_tokens"], "store": False,
                "text": {"format": {"type": "json_schema", "name": prompt["field"], "strict": True, "schema": {
                    "type": "object", "properties": {prompt["field"]: {"type": "string"}},
                    "required": [prompt["field"]], "additionalProperties": False}}}}
        if sec["system"]:
            body["instructions"] = fill(sec["system"], values)
        if s["effort"]:
            body["reasoning"] = {"effort": s["effort"]}
        for k in ("temperature", "top_p"):
            if s[k] is not None:
                body[k] = s[k]
        if s["effort"] == "none":
            body["include"] = ["message.output_text.logprobs"]
        return body

    if args.dry_run:
        for row in todo:
            v = pick_variant(row, prompt, args.variant_when, args.variant_default)
            b = body_for(row, v)
            print(f"\n=== {row[args.id_column]} | variant {v} | {settings_text}\n--- instructions ---\n"
                  f"{b.get('instructions', '(none)')}\n--- input ---\n{b['input']}")
        return

    def process(row):
        """One row: call, parse, check; new calls on a --fail-on hit. Returns the raw record."""
        rid = row[args.id_column]
        variant = pick_variant(row, prompt, args.variant_when, args.variant_default)
        body = body_for(row, variant)
        rec = {"id": rid, "run_key": run_key, "variant": variant, "ok": False,
               "at": datetime.now(timezone.utc).isoformat(), "responses": []}
        tokens_in = tokens_out = 0
        cost = 0.0 if price else None
        for attempt in range(args.fail_retries + 1):
            resp = post(key, body, rid, args.timeout, args.max_tries)
            if resp is None:
                rec["problem"] = "call failed"
                break
            rec["responses"].append(resp)
            i, o, c = usage_cost(price, resp.get("usage", {}))
            tokens_in, tokens_out = tokens_in + i, tokens_out + o
            cost = None if c is None or cost is None else cost + c
            value, conf, problem = parse(resp, prompt["field"])
            if problem:
                rec["problem"] = problem
                break
            found = run_checks(value, checks, max_words.get(variant, max_words.get("*")),
                               row.get(args.first_name_column, ""), review_phrases)
            blocking = [m for c_, m in found if c_ in fail_on]
            if blocking:
                rec["problem"] = f"blocked: {', '.join(blocking)} (try {attempt + 1}): {value}"
                continue
            rec.pop("problem", None)
            rec.update(ok=True, value=value)
            rec["out"] = {col: value, f"{col}_variant": variant, f"{col}_input_tokens": tokens_in,
                          f"{col}_output_tokens": tokens_out,
                          f"{col}_cost_usd": "" if cost is None else f"{cost:.6f}",
                          f"{col}_confidence": "" if conf is None else conf,
                          f"{col}_flags": "; ".join(m for _, m in found),
                          f"{col}_settings": settings_text, f"{col}_prompt": prompt["version"],
                          f"{col}_at": rec["at"]}
            break
        rec["cost"] = cost or 0
        if rec.get("problem"):
            log_error(rid, None, rec["problem"])
        return rec

    by_id = {r[args.id_column]: r for r in rows}
    out_path = args.output or args.input
    cost_cols = lambda: [c for c in fields if c.endswith("_cost_usd")]

    def flush_csv():
        for rid, d in done.items():
            if rid in by_id:
                by_id[rid].update(d["out"])
        for r in rows:
            vals = [float(r[c]) for c in cost_cols() if (r.get(c) or "").strip()]
            r["cost_usd_total"] = f"{sum(vals):.6f}" if vals else ""
        write_csv(out_path, fields, rows)

    spent, ok, failed, last_flush, stop = 0.0, 0, 0, 0.0, None
    queue = iter(todo)
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool, raw.open("a") as rawf:
        running = set()
        try:
            while True:
                while not stop and len(running) < args.concurrency:
                    if args.max_cost is not None and spent >= args.max_cost:
                        stop = f"--max-cost ${args.max_cost} reached"
                        break
                    row = next(queue, None)
                    if row is None:
                        break
                    running.add(pool.submit(process, row))
                if not running:
                    break
                finished, running = wait(running, return_when=FIRST_COMPLETED)
                for fut in finished:
                    try:
                        rec = fut.result()
                    except StopRun as e:
                        stop = f"billing/quota, retrying will not help: {e}"
                        continue
                    rawf.write(json.dumps(rec) + "\n")
                    rawf.flush()
                    spent += rec["cost"]
                    if rec["ok"]:
                        ok += 1
                        done[rec["id"]] = rec
                        o = rec["out"]
                        logging.info("%s | %s | %s | $%s | conf %s | %s", rec["id"], rec["variant"], o[col],
                                     o[f"{col}_cost_usd"], o[f"{col}_confidence"], o[f"{col}_flags"] or "-")
                    else:
                        failed += 1
                        logging.warning("%s | %s", rec["id"], rec.get("problem"))
                if time.time() - last_flush >= args.csv_every:
                    flush_csv()
                    last_flush = time.time()
        except KeyboardInterrupt:
            stop = "interrupted"
            for fut in running:
                fut.cancel()
    flush_csv()
    if stop:
        logging.warning("stopped: %s. Progress saved; re-run with --resume", stop)
    logging.info("run done: %d ok, %d failed (see %s), spent $%.6f | %d/%d rows done for %s",
                 ok, failed, ERROR_LOG.name, spent, len(done), len(rows), col)


if __name__ == "__main__":
    main()
