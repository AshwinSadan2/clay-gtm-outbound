#!/usr/bin/env python3
"""Summarise an email-enrichment results CSV for the user's review at each gate. Reads only; calls nothing.

    python3 .claude/skills/icypeas-email-fetch/scripts/review_results.py --results FILE --domain-column company_domain \
      [--last N] [--group-column icp_tier] [--show N]

--last N        only the newest N rows (the batch just run); default: the whole file
--group-column  also show the found rate per value of this column (e.g. title tier)
--show N        also list up to N rows (name, domain, email, status) for a quick look
"""
import argparse
import csv
import sys
from collections import Counter


def pct(n, total):
    return f"{n} ({100 * n / total:.0f}%)" if total else "0"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--results", required=True, help="results CSV written by icypeas_email_search.py")
    parser.add_argument("--domain-column", required=True, help="column holding the company domain")
    parser.add_argument("--last", type=int, help="only the newest N rows")
    parser.add_argument("--group-column", help="show the found rate per value of this column")
    parser.add_argument("--show", type=int, default=0, help="list up to N rows")
    parser.add_argument("--first-name-column", default="first_name", help="for --show")
    parser.add_argument("--last-name-column", default="last_name", help="for --show")
    args = parser.parse_args()

    csv.field_size_limit(10_000_000)
    with open(args.results, newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit(f"{args.results} has no rows yet")
    for col in [args.domain_column, args.group_column]:
        if col and col not in rows[0]:
            sys.exit(f"{args.results} has no column {col}")
    batch = rows[-args.last:] if args.last else rows
    total = len(batch)
    found = [r for r in batch if r["email_status"] == "found"]

    print(f"Rows reviewed: {total} (file has {len(rows)}, unique people "
          f"{len({r['email_search_id'] for r in rows})})")
    print(f"  found       {pct(len(found), total)}")
    print(f"  not_found   {pct(total - len(found), total)}")
    print("Icypeas status: " + ", ".join(f"{s} {n}" for s, n in Counter(r["email_provider_status"] for r in batch).most_common()))
    off_domain = [r for r in found if r["email"].split("@")[-1].lower() != r[args.domain_column].strip().lower()]
    print(f"Emails not on the company domain: {len(off_domain)}")
    print(f"People with more than one email returned: {sum(int(r['emails_found'] or 0) > 1 for r in batch)}")
    print("Mail providers: " + ", ".join(f"{p} {n}" for p, n in Counter(r["email_mx_provider"] for r in found).most_common()))
    print(f"Credits used (1 per email found): about {len(found)}")
    if args.group_column:
        print(f"Found by {args.group_column}:")
        for value in sorted({r[args.group_column] for r in batch}):
            group = [r for r in batch if r[args.group_column] == value]
            print(f"  {value:<12} {sum(r['email_status'] == 'found' for r in group)}/{len(group)}")
    for r in off_domain:
        print(f"  off-domain: {r['email']} (company {r[args.domain_column]})")
    for r in batch[:args.show]:
        print(f"  {r.get(args.first_name_column, '')} {r.get(args.last_name_column, '')} | {r[args.domain_column]} | "
              f"{r['email'] or '—'} | {r['email_status']}")


if __name__ == "__main__":
    main()
