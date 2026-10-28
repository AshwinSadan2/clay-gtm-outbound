#!/usr/bin/env python3
"""Write the AI {OPENER} merge variable in two passes with OpenAI: Stage 1 insight -> Stage 2 compose.

The script holds no prompt text and no campaign values. Both prompts live in versioned Markdown files
(docs/prompts/stage1_insight_vN.md, stage2_compose_vN.md), each with a "## Variant A" (contact About) and a
"## Variant B" (company About fallback) section holding "### System" and "### User" blocks, and a
"**Model:** ... (`model-id`)" line. {{variables}} are filled from the input CSV's columns of the same name,
plus {{angle}} (the Stage 1 result) in Stage 2. API facts: docs/openai-api-reference.md.

Per row: Variant A if the contact About (--about-column) has at least --min-about-words words, else Variant B.
    Stage 1 -> {"angle": ...}   Stage 2 (gets the angle) -> {"opener": ...}

    S=.claude/skills/mail-merge-variables/scripts/openai_opener.py
    F=(--input data/processed/mailable_contacts_<date>.csv --insight-prompt docs/prompts/stage1_insight_v1.md
       --compose-prompt docs/prompts/stage2_compose_v1.md --min-about-words 50)
    python3 $S --probe ...F                  # key works + both models available (free)
    python3 $S ...F --limit 1 --dry-run      # print the exact prompts for the next row, no calls
    python3 $S ...F --limit 1                # first row
    python3 $S ...F --resume --limit 10      # next 10 (never re-pays for a done row)

Writes (after every row, so a crash loses nothing):
    data/raw/openers_<input name>.jsonl   one line per row: id, variant, both requests' outputs + usage, untouched
    --input (updated in place)           the OUT_COLUMNS below, filled for each done row
Cost: tokens x the model's per-1M price (PRICES). Confidence: exp(mean log-probability) of the generated text,
only available with --effort none (OpenAI refuses log-probabilities for reasoning).
Run log: logs/openai_opener.log. Failed calls: logs/openai_opener_errors.log.
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
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
LOG_FILE = ROOT / "logs" / "openai_opener.log"
ERROR_LOG = ROOT / "logs" / "openai_opener_errors.log"

# OpenAI API facts (docs/openai-api-reference.md), not run settings.
RESPONSES_URL = "https://api.openai.com/v1/responses"
MODELS_URL = "https://api.openai.com/v1/models"
RETRY_CODES = {429, 500, 503}
MAX_TRIES = 5
# USD per 1M tokens: (input, cached input, output). Standard tier, read 2026-10-28.
PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6.1-terra": (1.00, 0.05, 5.00),
    "gpt-6.1-sol": (2.00, 0.10, 10.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-5.6-luna": (0.20, 0.02, 1.20),
}

OUT_COLUMNS = ["opener_variant", "insight", "opener", "input_tokens", "output_tokens", "cost_usd",
               "insight_confidence", "opener_confidence", "opener_flags", "opener_model", "opener_prompts",
               "opener_at"]

csv.field_size_limit(10_000_000)


class StopRun(Exception):
    """Billing/quota problem: retrying cannot fix it."""


# ---------- prompts ----------

def load_prompt(path):
    """Markdown prompt file -> {"model", "version", "A": {"system", "user"}, "B": {...}}."""
    text = Path(path).read_text()
    m = re.search(r"^\*\*Model:\*\*.*?`([^`]+)`", text, re.M)
    if not m:
        sys.exit(f"{path}: no '**Model:** ... (`model-id`)' line")
    out = {"model": m.group(1), "version": Path(path).stem}
    for variant in ("A", "B"):
        sec = re.search(rf"^## Variant {variant}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
        if not sec:
            sys.exit(f"{path}: no '## Variant {variant}' section")
        blocks = {}
        for role in ("System", "User"):
            b = re.search(rf"^### {role}\s*$(.*?)(?=^### |^---\s*$|\Z)", sec.group(1), re.M | re.S)
            if not b or not b.group(1).strip():
                sys.exit(f"{path}: Variant {variant} has no '### {role}' block")
            blocks[role.lower()] = b.group(1).strip()
        out[variant] = blocks
    return out


def variables(prompt):
    return {v for variant in ("A", "B") for block in prompt[variant].values()
            for v in re.findall(r"\{\{(\w+)\}\}", block)}


def fill(template, values):
    return re.sub(r"\{\{(\w+)\}\}", lambda m: values.get(m.group(1), ""), template)


# ---------- API ----------

def read_key(env_file):
    for line in Path(env_file).read_text().splitlines():
        if line.startswith("OPENAI_API_KEY="):
            return line.split("=", 1)[1].strip()
    return ""


def log_error(row_id, stage, code, message):
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ERROR_LOG.open("a") as f:  # never the request headers: the key is in Authorization
        f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "id": row_id, "stage": stage,
                            "http": code, "message": message}) + "\n")


def post(key, body, row_id, stage):
    """POST /v1/responses with retries on 429/500/503. Returns the JSON, or None after logging a failure."""
    for attempt in range(1, MAX_TRIES + 1):
        req = urllib.request.Request(RESPONSES_URL, data=json.dumps(body).encode(),
                                     headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            try:
                err = json.load(e).get("error") or {}
            except Exception:
                err = {}
            code, msg = e.code, err.get("message", str(e))
            if err.get("code") == "insufficient_quota" or "spend limit" in msg.lower():
                log_error(row_id, stage, code, msg)
                raise StopRun(f"{code} {err.get('code')}: {msg}")
            if code in RETRY_CODES and attempt < MAX_TRIES:
                wait = float(e.headers.get("Retry-After") or 2 ** attempt) + random.random()
                logging.warning("%s %s: HTTP %s, retry %d in %.1fs", row_id, stage, code, attempt, wait)
                time.sleep(wait)
                continue
            log_error(row_id, stage, code, msg)
            return None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < MAX_TRIES:
                time.sleep(2 ** attempt)
                continue
            log_error(row_id, stage, None, str(e))
            return None


def parse(resp, field):
    """Responses JSON -> (value, confidence, problem). Confidence uses only the value's own tokens."""
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
                    value = json.loads(c["text"])[field].strip()
                except (ValueError, KeyError):
                    return None, None, f"bad JSON: {c.get('text', '')[:200]}"
                return value, confidence(c.get("logprobs"), c["text"], field), None
    return None, None, "no text in output"


def confidence(logprobs, text, field):
    """exp(mean logprob) over the tokens inside the JSON string value (skips the forced {"field":" scaffolding)."""
    if not logprobs:
        return None
    start = text.find(f'"{field}"')
    start = text.find('"', text.find(":", start) + 1) + 1
    end = text.rfind('"')
    pos, picked = 0, []
    for t in logprobs:
        tok_end = pos + len(t["token"])
        if tok_end > start and pos < end:
            picked.append(t["logprob"])
        pos = tok_end
    return round(math.exp(sum(picked) / len(picked)), 4) if picked else None


def usage_cost(model, usage):
    """(input_tokens, output_tokens, cost_usd or None)."""
    inp, out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    cached = (usage.get("input_tokens_details") or {}).get("cached_tokens", 0)
    if model not in PRICES:
        return inp, out, None
    p_in, p_cached, p_out = PRICES[model]
    return inp, out, ((inp - cached) * p_in + cached * p_cached + out * p_out) / 1_000_000


def check_opener(opener, first_name):
    """Rule checks from the compose prompt: flag, never fix."""
    flags = []
    if not opener:
        return "empty"
    if re.search(r"[—–]|\s-\s|\s-$|^-", opener):
        flags.append("dash")
    if len(opener.split()) > 20:
        flags.append(f"{len(opener.split())} words")
    if "?" in opener:
        flags.append("question")
    if re.match(r"(hey|hi|hello)\b", opener, re.I) or (first_name and re.match(rf"{re.escape(first_name)}\b", opener, re.I)):
        flags.append("repeats greeting")
    return "; ".join(flags)


# ---------- run ----------

def write_csv(path, fields, rows):
    fd, tmp = tempfile.mkstemp(dir=Path(path).parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="CSV; updated in place with OUT_COLUMNS")
    ap.add_argument("--insight-prompt", required=True, help="Stage 1 prompt .md")
    ap.add_argument("--compose-prompt", required=True, help="Stage 2 prompt .md")
    ap.add_argument("--min-about-words", type=int, required=True, help="contact About shorter than this -> Variant B")
    ap.add_argument("--about-column", default="about_me")
    ap.add_argument("--id-column", default="person_linkedin_url")
    ap.add_argument("--first-name-column", default="first_name")
    ap.add_argument("--effort", default="none", help="reasoning effort; confidence needs 'none'")
    ap.add_argument("--max-output-tokens", type=int, default=1000)
    ap.add_argument("--limit", type=int, help="rows to process this run")
    ap.add_argument("--resume", action="store_true", help="skip rows already done in the raw file")
    ap.add_argument("--dry-run", action="store_true", help="print the filled prompts, no calls")
    ap.add_argument("--probe", action="store_true", help="check key + models, free")
    ap.add_argument("--env", default=str(ENV_FILE))
    args = ap.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])

    p1, p2 = load_prompt(args.insight_prompt), load_prompt(args.compose_prompt)
    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    missing = (variables(p1) | variables(p2) | {args.about_column, args.id_column}) - set(fields) - {"angle"}
    if missing:
        sys.exit(f"prompt variables with no CSV column: {', '.join(sorted(missing))}")
    fields += [c for c in OUT_COLUMNS if c not in fields]

    key = "" if args.dry_run else read_key(args.env)
    if not args.dry_run and not key:
        sys.exit(f"OPENAI_API_KEY is empty in {args.env}")

    if args.probe:
        req = urllib.request.Request(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
        try:
            ids = {m["id"] for m in json.load(urllib.request.urlopen(req, timeout=30))["data"]}
        except urllib.error.HTTPError as e:
            sys.exit(f"probe FAILED: HTTP {e.code}")
        for p in (p1, p2):
            logging.info("probe: %s -> %s %s", p["version"], p["model"],
                         "available" if p["model"] in ids else "NOT AVAILABLE")
            if p["model"] not in PRICES:
                logging.warning("probe: no price for %s, cost will be blank", p["model"])
        return

    raw = ROOT / "data" / "raw" / f"openers_{Path(args.input).stem}.jsonl"
    raw.parent.mkdir(parents=True, exist_ok=True)
    done = {}
    if raw.exists():
        for line in raw.read_text().splitlines():
            rec = json.loads(line)
            if rec.get("ok"):
                done[rec["id"]] = rec
    if done and not args.resume and not args.dry_run:
        sys.exit(f"{len(done)} rows already done in {raw}: add --resume to continue")

    todo = [r for r in rows if r[args.id_column] not in done][: args.limit]
    logging.info("%d rows, %d done, %d this run | %s + %s | effort %s | Variant B under %d words",
                 len(rows), len(done), len(todo), p1["version"], p2["version"], args.effort, args.min_about_words)

    def request(prompt, variant, values, field):
        body = {"model": prompt["model"], "instructions": fill(prompt[variant]["system"], values),
                "input": fill(prompt[variant]["user"], values), "reasoning": {"effort": args.effort},
                "max_output_tokens": args.max_output_tokens, "store": False,
                "text": {"format": {"type": "json_schema", "name": field, "strict": True, "schema": {
                    "type": "object", "properties": {field: {"type": "string"}},
                    "required": [field], "additionalProperties": False}}}}
        if args.effort == "none":
            body["include"] = ["message.output_text.logprobs"]
        return body

    errors = total_cost = 0
    by_id = {r[args.id_column]: r for r in rows}
    try:
        for row in todo:
            rid = row[args.id_column]
            variant = "A" if len(row[args.about_column].split()) >= args.min_about_words else "B"
            b1 = request(p1, variant, row, "angle")
            if args.dry_run:
                print(f"\n=== {rid} | Variant {variant}\n--- Stage 1 instructions ---\n{b1['instructions']}"
                      f"\n--- Stage 1 input ---\n{b1['input']}")
                b2 = request(p2, variant, {**row, "angle": "<Stage 1 angle>"}, "opener")
                print(f"--- Stage 2 instructions ---\n{b2['instructions']}\n--- Stage 2 input ---\n{b2['input']}")
                continue

            rec = {"id": rid, "variant": variant, "prompts": [p1["version"], p2["version"]], "ok": False,
                   "at": datetime.now(timezone.utc).isoformat()}
            r1 = post(key, b1, rid, "insight")
            angle, conf1, prob = parse(r1, "angle") if r1 else (None, None, "call failed")
            rec["insight_response"] = r1
            if angle:
                r2 = post(key, request(p2, variant, {**row, "angle": angle}, "opener"), rid, "compose")
                opener, conf2, prob = parse(r2, "opener") if r2 else (None, None, "call failed")
                rec["compose_response"] = r2
            if prob:
                errors += 1
                log_error(rid, "parse", None, prob)
                rec["problem"] = prob
            else:
                i1, o1, c1 = usage_cost(p1["model"], r1["usage"])
                i2, o2, c2 = usage_cost(p2["model"], r2["usage"])
                cost = None if c1 is None or c2 is None else round(c1 + c2, 8)
                total_cost += cost or 0
                rec.update(ok=True, angle=angle, opener=opener, out={
                    "opener_variant": variant, "insight": angle, "opener": opener,
                    "input_tokens": i1 + i2, "output_tokens": o1 + o2, "cost_usd": "" if cost is None else f"{cost:.6f}",
                    "insight_confidence": "" if conf1 is None else conf1,
                    "opener_confidence": "" if conf2 is None else conf2,
                    "opener_flags": check_opener(opener, row.get(args.first_name_column, "")),
                    "opener_model": " + ".join(dict.fromkeys([p1["model"], p2["model"]])),
                    "opener_prompts": f"{p1['version']} + {p2['version']}", "opener_at": rec["at"]})
                done[rid] = rec
                logging.info("%s | %s | %s | $%s | conf %s/%s | flags: %s", rid, variant, opener,
                             rec["out"]["cost_usd"], conf1, conf2, rec["out"]["opener_flags"] or "none")
            with raw.open("a") as f:
                f.write(json.dumps(rec) + "\n")
                f.flush()
            for rid_done, d in done.items():  # rewrite the CSV after every row
                if rid_done in by_id:
                    by_id[rid_done].update(d["out"])
            write_csv(args.input, fields, rows)
    except StopRun as e:
        logging.error("stopped: %s (billing/quota; retrying will not help)", e)
    except KeyboardInterrupt:
        logging.warning("interrupted: progress saved, re-run with --resume")

    if not args.dry_run:
        logging.info("run done: %d ok, %d errors, cost this run $%.6f | %d/%d rows done overall",
                     len(todo) - errors, errors, total_cost, len(done), len(rows))


if __name__ == "__main__":
    main()
