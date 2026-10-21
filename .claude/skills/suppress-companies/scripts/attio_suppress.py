#!/usr/bin/env python3
"""Stage 3 of 3: suppress a target list against the downloaded Attio suppression list. Never changes the database.

The target is a CSV (--target-csv FILE) or Supabase (--target-supabase: gtm.companies at domain level,
gtm.contacts at contact level; downloaded to data/processed/<companies|contacts>_supabase_<date>.csv).
Domain level matches on company domain. Contact level matches on EMAIL ONLY, on both sides (never LinkedIn URL),
and refuses to run if the target has no email column or no emails. Rows without an email can't be checked:
they go to an _unchecked file, never to clean.

Without --apply (the default) this is a preview: it profiles the target (rows, blanks, duplicates) and shows
exactly what would be suppressed, writing nothing but the Supabase download. With --apply it writes:
    data/processed/<target>_suppressed_<date>.csv   matched rows, with suppression_reason and suppress_until
    data/processed/<target>_clean_<date>.csv        rows safe to enrich
    data/processed/<target>_unchecked_<date>.csv    contact level only: rows with no email (not checked)

Usage (from the project folder):
    S=.claude/skills/suppress-companies/scripts
    .venv/bin/python $S/attio_suppress.py --level domain --target-supabase              # preview
    .venv/bin/python $S/attio_suppress.py --level domain --target-supabase --apply      # after sign-off
    .venv/bin/python $S/attio_suppress.py --level contact --target-csv leads.csv --email-column "Work Email"
"""
import collections
import csv
import sys
from pathlib import Path

import attio_common as ac


def supabase_rows(sql, out):
    import psycopg  # only needed for this source; lives in the project .venv
    with psycopg.connect(ac.env_get("SUPABASE_DB_URL_POOLER"), prepare_threshold=None, connect_timeout=10) as conn:
        cur = conn.execute(sql)
        columns = [d.name for d in cur.description]
        rows = [dict(zip(columns, r)) for r in cur]
    ac.write_csv(out, columns, rows)
    ac.logging.info("downloaded %d rows from Supabase to %s", len(rows), out.relative_to(ac.ROOT))
    return rows, columns


def load_target(args):
    """The list to suppress against: (rows, columns, match column, file stem)."""
    if args.target_supabase and args.level == "domain":
        rows, columns = supabase_rows(
            "select name, domain, linkedin_url, industry, employees_on_linkedin, hq_country_code, "
            "exists (select 1 from gtm.contacts p where p.company_domain = c.domain) as has_contact "
            "from gtm.companies c order by domain", ac.PROCESSED / f"companies_supabase_{args.date}.csv")
        return rows, columns, "domain", "companies_supabase"
    if args.target_supabase:
        import psycopg
        with psycopg.connect(ac.env_get("SUPABASE_DB_URL_POOLER"), prepare_threshold=None, connect_timeout=10) as conn:
            has_email = conn.execute("select 1 from information_schema.columns where table_schema = 'gtm' "
                                     "and table_name = 'contacts' and column_name = %s", (args.email_column,)).fetchone()
        if not has_email:
            sys.exit(f"gtm.contacts has no '{args.email_column}' column yet (emails come from the email-enrichment step). "
                     "Contact-level suppression matches on email only, so it can't run on this list.")
        rows, columns = supabase_rows(
            f"select person_linkedin_url, company_domain, first_name, last_name, job_title, icp_tier, {args.email_column} "
            "from gtm.contacts order by company_domain", ac.PROCESSED / f"contacts_supabase_{args.date}.csv")
        return rows, columns, args.email_column, "contacts_supabase"
    path = Path(args.target_csv)
    if not path.is_file():
        sys.exit(f"Target CSV not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows, columns = list(reader), reader.fieldnames
    key = args.domain_column if args.level == "domain" else args.email_column
    if key not in columns:
        flag = "--domain-column" if args.level == "domain" else "--email-column"
        sys.exit(f"{path} has no '{key}' column (columns: {columns}). Pass {flag} NAME."
                 + ("" if args.level == "domain" else " Contact-level suppression matches on email only."))
    # Drop a trailing _YYYY-MM-DD so outputs get today's stamp, not two dates.
    stem = path.stem[:-11] if len(path.stem) > 11 and path.stem[-11] == "_" and path.stem[-10:-6].isdigit() else path.stem
    return rows, columns, key, stem


def main():
    parser = ac.base_parser(__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--target-csv", help="CSV to suppress against")
    target.add_argument("--target-supabase", action="store_true",
                        help="gtm.companies (domain level) or gtm.contacts (contact level)")
    parser.add_argument("--domain-column", default="domain", help="domain column in --target-csv (default: domain)")
    parser.add_argument("--email-column", default="email",
                        help="email column of the target, contact level (default: email). Contact level matches on email only.")
    parser.add_argument("--suppression", help="suppression list CSV (default: suppression_attio_<level>_<date>.csv)")
    parser.add_argument("--apply", action="store_true", help="write the suppressed and clean CSVs (default: preview only)")
    args = ac.setup(parser)

    supp_file = Path(args.suppression) if args.suppression else ac.suppression_file(args.level, args.date)
    if not supp_file.is_file():
        sys.exit(f"No suppression list at {supp_file}: run attio_download.py --level {args.level} first, "
                 "or pass --suppression FILE")
    with open(supp_file, newline="") as f:
        supp = list(csv.DictReader(f))
    rows, columns, key, stem = load_target(args)

    if args.level == "domain":
        index = {r["domain"]: r for r in supp}
        ident = lambda r: ac.norm_domain(r[key])
    else:
        index = {e.strip(): r for r in supp for e in r["email"].split(";") if e.strip()}
        ident = lambda r: str(r[key] or "").strip().lower()

    ids = [ident(r) for r in rows]
    seen = collections.Counter(i for i in ids if i)
    unit = "domains" if args.level == "domain" else "people"
    print(f"\nSuppression list: {supp_file.name} ({len(supp)} {unit})")
    print(f"Target: {len(rows)} rows | match on {key} | unique {len(seen)} | "
          f"blank {ids.count('')} | duplicates {sum(1 for n in seen.values() if n > 1)}")
    if args.level == "contact" and not seen:
        sys.exit("The target has no emails: contact-level suppression matches on email only, so it won't run. "
                 "Get emails for the lead list first, or use --level domain.")

    matched, clean, unchecked, hits = [], [], [], []
    for r, i in zip(rows, ids):
        hit = index.get(i) if i else None
        if not i:
            unchecked.append(r)
        elif hit:
            matched.append(dict(r, suppression_reason=hit["suppression_reason"], suppress_until=hit["suppress_until"]))
            hits.append(hit)
        else:
            clean.append(r)
    ac.report(hits, args.detail_threshold, "Suppressed" if args.apply else "Would be suppressed", args.level)
    print(f"\n  clean (safe to enrich): {len(clean)}")
    if unchecked:
        print(f"  unchecked (no {'domain' if args.level == 'domain' else 'email'}, can't be matched): {len(unchecked)}")
    if "has_contact" in columns:
        print(f"  suppressed companies that already have a contact: {sum(1 for m in matched if m['has_contact'])}")
    if not args.apply:
        print("\n  preview only: nothing written. Re-run with --apply after sign-off.")
        return
    ac.write_csv(ac.PROCESSED / f"{stem}_suppressed_{args.date}.csv", columns + ["suppression_reason", "suppress_until"], matched)
    ac.write_csv(ac.PROCESSED / f"{stem}_clean_{args.date}.csv", columns, clean)
    if unchecked:
        ac.write_csv(ac.PROCESSED / f"{stem}_unchecked_{args.date}.csv", columns, unchecked)
    ac.logging.info("suppress (%s level): %d suppressed → %s_suppressed_%s.csv, %d clean → %s_clean_%s.csv "
                    "(database unchanged)", args.level, len(matched), stem, args.date, len(clean), stem, args.date)


if __name__ == "__main__":
    main()
