#!/usr/bin/env python3
"""Distil a tech-stack CSV down to one client's signals: keep only that client's allowlisted tools, ranked.

Two steps:
  config    Turn the client's distiller doc (markdown, written by Claude from what the user says about the client)
            into the distiller config JSON this script reads. Re-run whenever the doc changes.
  distill   Apply a distiller config to any CSV with a tech-stack column holding the {type: [tools]} map: the
            full results CSV written by detectzestack_tech_search.py, or a Supabase export
            (data.py export-companies --tech scanned).

    S=.claude/skills/detectzestack-tech-stack/scripts/distill_tech_stack.py
    python3 $S config --doc docs/<client>-tech-distiller.md --config data/processed/distiller_<client>_<date>.json
    python3 $S distill --config data/processed/distiller_<client>_<date>.json \
      --input data/processed/tech_stack_companies_<date>.csv \
      --output data/processed/distilled_tech_stack_companies_<date>.csv \
      --keep-columns name,domain,website,linkedin_url [--types "CRM,Ad pixel"] [--project-to 1000]

distill writes one row per company (overwritten each run) with two signal columns:
    tech_tool    the allowlisted tools found, highest-ranked type first, "; "-separated (blank when none)
    tech_type    each tool's type, in the same order (e.g. "CRM; Ad pixel")
and prints the hit rate and, with --project-to N, the expected number of companies with a signal in a list of N.

Distiller doc format (see docs/clay-tech-distiller.md): a "# Tech distiller — <client> ..." title and a markdown
table under a heading "## Allowlist" with the columns
    | Rank | Type | Tool | Relation |
Rank = the type's priority (1 = highest; the same for every tool of a type). Tool = the exact name the API
returns (matched case-insensitively). Relation = corresponding / adjacent.
"""
import argparse
import csv
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path.cwd()

csv.field_size_limit(10_000_000)  # JSON cells


def project_path(path):
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def shown(path):
    return path.relative_to(ROOT) if path.is_relative_to(ROOT) else path


def build_config(doc):
    """Parse the doc's title and "## Allowlist" table into the config dict (exits with a clear message if malformed)."""
    text = Path(doc).read_text()
    title = re.search(r"^#\s+Tech distiller\s*[—-]\s*(.+?)\s*$", text, re.M)
    section = re.search(r"^##\s+Allowlist\s*$(.*?)(?=^##\s|\Z)", text, re.M | re.S)
    if not section:
        sys.exit(f"{doc} has no '## Allowlist' section (format: see this script's --help)")
    lines = [l.strip() for l in section.group(1).splitlines() if l.strip().startswith("|")]
    header = [c.strip().lower() for c in lines[0].strip("|").split("|")] if lines else []
    if header[:4] != ["rank", "type", "tool", "relation"]:
        sys.exit(f"{doc}: the Allowlist table must start with columns Rank | Type | Tool | Relation, got {header}")
    types, seen = {}, {}
    for line in lines[2:]:  # skip the header and the |---| row
        rank, type_, tool, relation = [c.strip() for c in line.strip("|").split("|")][:4]
        if not (rank.isdigit() and type_ and tool):
            sys.exit(f"{doc}: bad Allowlist row: {line}")
        if relation.lower() not in ("corresponding", "adjacent"):
            sys.exit(f"{doc}: Relation must be corresponding or adjacent, got {relation!r} in: {line}")
        entry = types.setdefault(type_, {"type": type_, "rank": int(rank), "tools": []})
        if entry["rank"] != int(rank):
            sys.exit(f"{doc}: type {type_!r} has two ranks ({entry['rank']} and {rank}); rank is per type")
        if seen.setdefault(tool.lower(), type_) != type_:
            sys.exit(f"{doc}: tool {tool!r} is listed under two types; a tool belongs to one type")
        entry["tools"].append({"name": tool, "relation": relation.lower()})
    if not types:
        sys.exit(f"{doc}: the Allowlist table is empty")
    return {"client": title.group(1) if title else Path(doc).stem,
            "source_doc": str(shown(project_path(doc))),
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "types": sorted(types.values(), key=lambda t: t["rank"])}


def load_config(path):
    try:
        config = json.loads(Path(path).read_text())
        ranks = {t["type"]: int(t["rank"]) for t in config["types"]}
        tools = {tool["name"].lower(): (tool["name"], t["type"]) for t in config["types"] for tool in t["tools"]}
    except (OSError, ValueError, KeyError, TypeError) as e:
        sys.exit(f"{path} is not a distiller config ({e}). Build one with: config --doc DOC --config {path}")
    return config, ranks, tools


def cmd_config(args):
    config = build_config(args.doc)
    out = project_path(args.config)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(config, indent=1) + "\n")
    print(f"distiller config for {config['client']}: " + " > ".join(
        f"{t['type']} ({len(t['tools'])} tools)" for t in config["types"]))
    print(f"written: {shown(out)}")


def cmd_distill(args):
    config, ranks, tools = load_config(args.config)
    if args.types:
        wanted = [t.strip() for t in args.types.split(",") if t.strip()]
        unknown = [t for t in wanted if t not in ranks]
        if unknown:
            sys.exit(f"type(s) {unknown} not in {args.config}; it has {sorted(ranks, key=ranks.get)}")
        tools = {k: v for k, v in tools.items() if v[1] in wanted}
    keep = [c.strip() for c in args.keep_columns.split(",") if c.strip()]

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in keep + [args.stack_column] if c not in reader.fieldnames]
        if missing:
            sys.exit(f"{args.input} has no column(s): {', '.join(missing)}. Columns: {', '.join(reader.fieldnames)}")
        rows = list(reader)

    out_path = project_path(args.output)
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
    print(f"{config['client']}: {len(rows)} companies, {scanned} with a scan: {found} with a signal ({rate:.0%} hit "
          f"rate), {scanned - found} without, {len(rows) - scanned} not scanned / failed")
    print("tools: " + (", ".join(f"{k} {n}" for k, n in hits_by_tool.most_common()) or "none"))
    if args.project_to and scanned:
        # A rough range: ±1 standard error of the sample hit rate.
        spread = math.sqrt(rate * (1 - rate) / scanned)
        low, high = max(rate - spread, 0), min(rate + spread, 1)
        print(f"projection for {args.project_to} companies: ~{round(rate * args.project_to)} with a signal "
              f"(likely {round(low * args.project_to)}–{round(high * args.project_to)})")
    print(f"written: {shown(out_path)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("config", help="build the distiller config JSON from the client's distiller doc")
    c.add_argument("--doc", required=True, help="the client's distiller doc (docs/<client>-tech-distiller.md)")
    c.add_argument("--config", required=True, help="config JSON to write (data/processed/distiller_<client>_<date>.json)")
    d = sub.add_parser("distill", help="apply a distiller config to a tech-stack CSV")
    d.add_argument("--config", required=True, help="distiller config JSON (from the config step)")
    d.add_argument("--input", required=True, help="CSV with a tech-stack column (results CSV or Supabase export)")
    d.add_argument("--output", required=True, help="distilled CSV to write (overwritten each run)")
    d.add_argument("--keep-columns", required=True, help="comma-separated input columns to copy (e.g. name,domain)")
    d.add_argument("--types", help="comma-separated subset of the config's types to keep (default: all)")
    d.add_argument("--stack-column", default="tech_stack", help="column holding the {type: [tools]} map")
    d.add_argument("--project-to", type=int, help="also print the expected companies with a signal in a list of N")
    args = parser.parse_args()
    cmd_config(args) if args.command == "config" else cmd_distill(args)


if __name__ == "__main__":
    main()
