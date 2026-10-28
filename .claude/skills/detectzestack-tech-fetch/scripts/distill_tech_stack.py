#!/usr/bin/env python3
"""Distil a tech-stack CSV down to one client's signals: keep only that client's allowlisted tools, ranked.

Input: any CSV with a tech-stack column holding the {type: [tools]} map, i.e. the full results CSV written by
detectzestack_tech_search.py, or a Supabase export (data.py export-companies --tech-scanned). The allowlist and the
ranking come from the client's distiller doc (--distiller), so no client is built into this script.

Writes one row per company (overwritten each run) with two signal columns:
    tech_tool    the allowlisted tools found, highest-ranked type first, "; "-separated (blank when none)
    tech_type    each tool's type, in the same order (e.g. "CRM; Ad pixel")
Prints the hit rate and, with --project-to N, the expected number of companies with a signal in a list of N.

    python3 .claude/skills/detectzestack-tech-fetch/scripts/distill_tech_stack.py \
      --input data/processed/tech_stack_companies_<date>.csv \
      --output data/processed/distilled_tech_stack_companies_<date>.csv \
      --distiller docs/<client>-tech-distiller.md --keep-columns name,domain,website,linkedin_url \
      [--types "CRM,Ad pixel"] [--project-to 1000]

Distiller doc format: a markdown table under a heading "## Allowlist" with the columns
    | Rank | Type | Tool | Relation |
Rank = the type's priority (1 = highest; the same for every tool of a type). Tool = the exact name the API
returns (matched case-insensitively). Relation = corresponding / adjacent (documentation for the copy step).
Example: docs/clay-tech-distiller.md.
"""
import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()

csv.field_size_limit(10_000_000)  # JSON cells


def read_distiller(path):
    """Return {type: rank} and {tool name (lower): (tool name, type)} from the doc's "## Allowlist" table."""
    text = Path(path).read_text()
    section = re.search(r"^##\s+Allowlist\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not section:
        sys.exit(f"{path} has no '## Allowlist' section (see the format in this script's --help)")
    lines = [l.strip() for l in section.group(1).splitlines() if l.strip().startswith("|")]
    header = [c.strip().lower() for c in lines[0].strip("|").split("|")] if lines else []
    if header[:4] != ["rank", "type", "tool", "relation"]:
        sys.exit(f"{path}: the Allowlist table must start with columns Rank | Type | Tool | Relation, got {header}")
    ranks, tools = {}, {}
    for line in lines[2:]:  # skip the header and the |---| row
        rank, type_, tool, relation = [c.strip() for c in line.strip("|").split("|")][:4]
        if not (rank.isdigit() and type_ and tool):
            sys.exit(f"{path}: bad Allowlist row: {line}")
        if ranks.setdefault(type_, int(rank)) != int(rank):
            sys.exit(f"{path}: type {type_!r} has two ranks ({ranks[type_]} and {rank}); rank is per type")
        if tool.lower() in tools and tools[tool.lower()][1] != type_:
            sys.exit(f"{path}: tool {tool!r} is listed under two types; a tool belongs to one type")
        tools[tool.lower()] = (tool, type_)
    if not tools:
        sys.exit(f"{path}: the Allowlist table is empty")
    return ranks, tools


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="CSV with a tech-stack column (results CSV or Supabase export)")
    parser.add_argument("--output", required=True, help="distilled CSV to write (overwritten each run)")
    parser.add_argument("--distiller", required=True, help="the client's distiller doc (markdown with a '## Allowlist' table)")
    parser.add_argument("--keep-columns", required=True, help="comma-separated input columns to copy (e.g. name,domain)")
    parser.add_argument("--types", help="comma-separated subset of the doc's types to keep (default: all)")
    parser.add_argument("--stack-column", default="tech_stack", help="column holding the {type: [tools]} map")
    parser.add_argument("--project-to", type=int, help="also print the expected companies with a signal in a list of N")
    args = parser.parse_args()

    ranks, tools = read_distiller(args.distiller)
    if args.types:
        wanted = [t.strip() for t in args.types.split(",") if t.strip()]
        unknown = [t for t in wanted if t not in ranks]
        if unknown:
            parser.error(f"type(s) {unknown} not in {args.distiller}; it has {sorted(ranks, key=ranks.get)}")
        tools = {k: v for k, v in tools.items() if v[1] in wanted}
    keep = [c.strip() for c in args.keep_columns.split(",") if c.strip()]

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in keep + [args.stack_column] if c not in reader.fieldnames]
        if missing:
            sys.exit(f"{args.input} has no column(s): {', '.join(missing)}. Columns: {', '.join(reader.fieldnames)}")
        rows = list(reader)

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    scanned = found = 0
    hits_by_tool = Counter()
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keep + ["tech_tool", "tech_type"])
        writer.writeheader()
        for row in rows:
            cell = row[args.stack_column].strip()
            stack = json.loads(cell) if cell else None  # blank = never scanned, or the scan failed
            hits = {}
            for names in (stack or {}).values():
                for name in names:
                    match = tools.get(name.strip().lower())
                    if match:
                        hits.setdefault(match[0], match[1])
            ordered = sorted(hits.items(), key=lambda kv: (ranks[kv[1]], kv[0].lower()))
            writer.writerow({**{c: row[c] for c in keep},
                             "tech_tool": "; ".join(name for name, _ in ordered),
                             "tech_type": "; ".join(t for _, t in ordered)})
            scanned += stack is not None
            found += bool(hits)
            hits_by_tool.update(f"{name} ({t})" for name, t in ordered)

    rate = found / scanned if scanned else 0
    print(f"{len(rows)} companies, {scanned} with a scan: {found} with a signal ({rate:.0%} hit rate), "
          f"{scanned - found} without, {len(rows) - scanned} not scanned / failed")
    print("tools: " + (", ".join(f"{k} {n}" for k, n in hits_by_tool.most_common()) or "none"))
    if args.project_to and scanned:
        # A rough range: ±1 standard error of the sample hit rate.
        spread = math.sqrt(rate * (1 - rate) / scanned)
        low, high = max(rate - spread, 0), min(rate + spread, 1)
        print(f"projection for {args.project_to} companies: ~{round(rate * args.project_to)} with a signal "
              f"(likely {round(low * args.project_to)}–{round(high * args.project_to)})")
    print(f"written: {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")


if __name__ == "__main__":
    main()
