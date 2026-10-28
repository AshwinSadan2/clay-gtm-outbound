#!/usr/bin/env python3
"""Set a deterministic {ROLE} merge variable from each contact's job title, using first-match-wins keyword rules.

No API calls and no database change: reads a CSV, adds two columns, writes it back (or to --output).
The script holds no campaign values: the rules, the default role and the column names are flags.

Rules are checked top to bottom; the first rule with a keyword in the title wins. A keyword matches whole words
only, case-insensitive, with hyphens read as spaces ("co founder" matches "Co-Founder"). End a keyword with *
to match the start of a word ("demand gen*" matches "Demand Generation").

    S=.claude/skills/mail-merge-variables/scripts/role_variable.py
    python3 $S --input data/processed/mailable_contacts_<date>.csv \
      --rule "founders=founder,co founder,cofounder,ceo,chief executive,owner" \
      --rule "marketing leaders=marketing,demand gen*,cmo,chief marketing" \
      --rule "revenue leaders=sales,revenue,revops,rev ops,gtm,go to market,business development,cro,chief revenue" \
      --default "marketing leaders" --dry-run          # show the counts and the non-obvious titles, write nothing
    python3 $S ...same flags...                         # write the columns

Writes:  <role column> (the value) and <role column>_rule (which rule fired, or "default") into --output
         (default: overwrite --input). Re-running replaces both columns, so it is safe to repeat.
Run log: logs/role_variable.log.
"""
import argparse
import csv
import logging
import os
import re
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()
LOG_FILE = ROOT / "logs" / "role_variable.log"

csv.field_size_limit(10_000_000)


def parse_rule(text):
    """'label=kw1,kw2*' -> (label, compiled pattern)."""
    if "=" not in text:
        raise argparse.ArgumentTypeError(f"rule needs label=keywords: {text!r}")
    label, kws = (s.strip() for s in text.split("=", 1))
    parts = []
    for kw in (k.strip().lower().replace("-", " ") for k in kws.split(",")):
        if not kw:
            continue
        prefix = kw.endswith("*")
        body = r"\s+".join(re.escape(w) for w in kw.rstrip("*").split())
        parts.append(rf"\b{body}" + ("" if prefix else r"\b"))
    if not label or not parts:
        raise argparse.ArgumentTypeError(f"rule has no label or keywords: {text!r}")
    return label, re.compile("|".join(parts))


def classify(title, rules, default):
    """Return (role, rule label that fired or 'default')."""
    norm = title.lower().replace("-", " ")
    for label, pattern in rules:
        if pattern.search(norm):
            return label, label
    return default, "default"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="CSV with a job-title column")
    ap.add_argument("--output", help="where to write (default: overwrite --input)")
    ap.add_argument("--rule", action="append", type=parse_rule, required=True,
                    help='"label=kw1,kw2,..." (repeat; order = priority)')
    ap.add_argument("--default", required=True, help="role when no rule matches")
    ap.add_argument("--title-column", default="job_title")
    ap.add_argument("--role-column", default="role")
    ap.add_argument("--dry-run", action="store_true", help="print counts and edge cases, write nothing")
    args = ap.parse_args()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)])

    src = Path(args.input)
    with src.open(newline="") as f:
        reader = csv.DictReader(f)
        fields = list(reader.fieldnames or [])
        rows = list(reader)
    if args.title_column not in fields:
        sys.exit(f"column {args.title_column!r} not in {src} (has: {', '.join(fields)})")

    rule_col = f"{args.role_column}_rule"
    for col in (args.role_column, rule_col):
        if col not in fields:
            fields.append(col)

    counts, blanks, edge = Counter(), 0, []
    for r in rows:
        title = (r.get(args.title_column) or "").strip()
        blanks += not title
        role, fired = classify(title, args.rule, args.default)
        r[args.role_column], r[rule_col] = role, fired
        counts[(role, fired)] += 1
        # Worth a look: titles that fell to the default, or landed outside the default role.
        if fired == "default" or role != args.default:
            edge.append((role, fired, title))

    logging.info("%s: %d rows, %d with no title", src, len(rows), blanks)
    for (role, fired), n in counts.most_common():
        logging.info("  %-20s via %-20s %d", role, fired, n)
    for role, fired, title in sorted(edge):
        logging.info("  check: %-20s (%s) <- %s", role, fired, title or "(no title)")

    if args.dry_run:
        logging.info("dry run: nothing written")
        return

    # Write to a temp file, then swap in, so a crash never leaves a half-written CSV.
    dst = Path(args.output or args.input)
    fd, tmp = tempfile.mkstemp(dir=dst.parent, suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fields)
        w.writeheader()
        w.writerows(rows)
    os.replace(tmp, dst)
    logging.info("wrote %s (%s, %s)", dst, args.role_column, rule_col)


if __name__ == "__main__":
    main()
