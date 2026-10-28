#!/usr/bin/env python3
"""Distil a tech-stack CSV down to the campaign's signals: keep only allowlisted tools, drop the plumbing.

Reads the full results CSV written by detectzestack_tech_search.py (its raw-response column), matches every
detected technology by exact name (case-insensitive) against the allowlist below, and writes one row per
company with two signal columns:
    tech_tool    the allowlisted tools found, "; "-separated (blank when none)
    tech_type    each tool's type, in the same order (e.g. "CRM; Ad pixel")
The full CSV is never changed: it stays the source for the Supabase push, and a new campaign can re-distil it
with other --types without paying to re-scan.

    python3 .claude/skills/detectzestack-tech-fetch/scripts/distill_tech_stack.py \
      --input data/processed/tech_stack_companies_<date>.csv \
      --output data/processed/distilled_tech_stack_companies_<date>.csv \
      --keep-columns name,domain,website,linkedin_url --types "CRM,Sequencer,Ad pixel"

The allowlist comes from docs/clay-relevant-tech-providers.md (Clay-relevant, publicly detectable tools; only the
CRM, sequencer and ad-pixel groups are carried here; HubSpot CMS Hub is deliberately not counted as CRM), spelled
the way detection APIs return them. Names drift (Sendinblue -> Brevo): when a known tool is missed, add its
exact detected name here.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path.cwd()

# type -> detected names. A tool belongs to one type only.
ALLOWLIST = {
    "CRM": ["Salesforce", "HubSpot", "Zoho CRM", "Zoho", "Pipedrive", "Close", "Microsoft Dynamics 365",
            "Freshsales", "Freshworks CRM", "SugarCRM", "Copper", "Insightly", "Attio", "amoCRM", "Bitrix24"],
    "Sequencer": ["Outreach", "Salesloft", "Apollo", "Apollo.io", "Smartlead", "SmartLead", "Instantly",
                  "lemlist", "Reply.io", "Woodpecker"],
    "Ad pixel": ["Linkedin Ads", "LinkedIn Insight Tag", "Linkedin Insight Tag", "Google Ads",
                 "Google Ads Conversion Tracking", "Google Remarketing", "Facebook Pixel", "Meta Pixel",
                 "Twitter Ads", "X Ads", "Reddit Ads", "Reddit Pixel", "TikTok Pixel"],
}

csv.field_size_limit(10_000_000)  # raw JSON cells


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--input", required=True, help="full tech-stack CSV (from detectzestack_tech_search.py)")
    parser.add_argument("--output", required=True, help="distilled CSV to write (overwritten each run)")
    parser.add_argument("--keep-columns", required=True, help="comma-separated input columns to copy (e.g. name,domain)")
    parser.add_argument("--types", required=True, help=f"comma-separated signal types to keep, from: {', '.join(ALLOWLIST)}")
    parser.add_argument("--raw-column", default="tech_raw", help="column holding the raw API response")
    args = parser.parse_args()

    types = [t.strip() for t in args.types.split(",") if t.strip()]
    unknown = [t for t in types if t not in ALLOWLIST]
    if unknown:
        parser.error(f"unknown type(s) {unknown}; choose from {list(ALLOWLIST)}")
    lookup = {name.lower(): t for t in types for name in ALLOWLIST[t]}
    keep = [c.strip() for c in args.keep_columns.split(",") if c.strip()]

    with open(args.input, newline="") as f:
        reader = csv.DictReader(f)
        missing = [c for c in keep + [args.raw_column] if c not in reader.fieldnames]
        if missing:
            sys.exit(f"{args.input} has no column(s): {', '.join(missing)}. Columns: {', '.join(reader.fieldnames)}")
        rows = list(reader)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    found, tools = 0, Counter()
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keep + ["tech_tool", "tech_type"])
        writer.writeheader()
        for row in rows:
            hits = {}
            raw = json.loads(row[args.raw_column]) if row[args.raw_column].strip() else {}  # blank = failed scan
            for tech in raw.get("technologies") or []:
                t = lookup.get((tech.get("name") or "").strip().lower())
                if t:
                    hits.setdefault(tech["name"], t)
            ordered = sorted(hits.items(), key=lambda kv: (types.index(kv[1]), kv[0].lower()))
            writer.writerow({**{c: row[c] for c in keep},
                             "tech_tool": "; ".join(name for name, _ in ordered),
                             "tech_type": "; ".join(t for _, t in ordered)})
            found += bool(hits)
            tools.update(f"{name} ({t})" for name, t in ordered)

    print(f"{len(rows)} companies: {found} with a signal, {len(rows) - found} without")
    print("tools: " + (", ".join(f"{k} {n}" for k, n in tools.most_common()) or "none"))
    print(f"written: {out_path.relative_to(ROOT) if out_path.is_relative_to(ROOT) else out_path}")


if __name__ == "__main__":
    main()
