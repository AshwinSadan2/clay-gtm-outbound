#!/usr/bin/env python3
"""Supabase helper for the GTM project: run migrations and load CSVs into the gtm schema.

Usage (needs the project virtualenv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt):
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py migrate                 # apply new files in db/migrations
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py load --companies FILE --contacts FILE [--limit N]   # both, companies first
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py load-companies FILE [--limit N]   # upsert into gtm.companies on domain
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py load-contacts FILE [--limit N]    # upsert into gtm.contacts on person_linkedin_url
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py export-companies [--all]  # companies CSV for the contact search
    .venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py stats                   # row counts and link checks

Loads are upserts, so re-running is safe; unchanged rows are left untouched (updated_at
only moves when something changed). Each row commits on its own: a bad row is logged to
logs/data_errors.log and the load carries on. Contacts are skipped if they have no first name
(decision 2026-10-19: they can't get {FIRST_NAME}) or their company isn't loaded yet.
ORDER MATTERS: companies first, then contacts. Each contact links to its company (foreign key), so
a contact whose company isn't loaded is skipped. `load` does both in the right order.
Migrations use SUPABASE_DB_URL_DIRECT; loads use SUPABASE_DB_URL_POOLER (transaction pooler, port 6543).
"""
import argparse
import csv
import json
import logging
import sys
import time
from datetime import date
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
if not (ROOT / ".env").is_file():
    sys.exit(f"No .env in {ROOT}: run this from the GTM project folder")
MIGRATIONS_DIR = ROOT / "db" / "migrations"
LOG_FILE = ROOT / "logs" / "data.log"
ERROR_LOG = ROOT / "logs" / "data_errors.log"

csv.field_size_limit(10_000_000)  # raw JSON cells

COMPANY_COLUMNS = ["domain", "name", "website", "linkedin_url", "industry",
                   "employees_on_linkedin", "hq_country_code", "about", "raw"]
CONTACT_COLUMNS = ["person_linkedin_url", "company_domain", "icp_tier", "first_name", "last_name",
                   "job_title", "headline", "location_country_code", "about_me", "raw"]
INTEGER_COLUMNS = {"employees_on_linkedin", "icp_tier"}


def env_get(key):
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env")


def connect(pooled):
    url = env_get("SUPABASE_DB_URL_POOLER" if pooled else "SUPABASE_DB_URL_DIRECT")
    # The transaction pooler can't hold prepared statements across calls.
    return psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=10)


def log_error(table, key, error, row):
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({
            "at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "table": table,
            "key": key,
            "error": str(error).strip(),
            "row": {k: v for k, v in row.items() if k != "raw"},
        }) + "\n")


def migrate():
    with connect(pooled=False) as conn:
        conn.execute("create schema if not exists gtm")
        conn.execute("""create table if not exists gtm.schema_migrations (
                            filename text primary key,
                            applied_at timestamptz not null default now())""")
        applied = {r[0] for r in conn.execute("select filename from gtm.schema_migrations")}
        for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if path.name in applied:
                continue
            # The file and its bookkeeping row commit together, or not at all.
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("insert into gtm.schema_migrations (filename) values (%s)", (path.name,))
            logging.info("applied migration %s", path.name)
    logging.info("migrations up to date")


def upsert_sql(table, columns, key):
    cols = ", ".join(columns)
    updates = [c for c in columns if c != key]
    return (
        f"insert into gtm.{table} ({cols}) values ({', '.join(['%s'] * len(columns))}) "
        f"on conflict ({key}) do update set "
        + ", ".join(f"{c} = excluded.{c}" for c in updates)
        + f" where ({', '.join(f'gtm.{table}.{c}' for c in updates)}) "
        f"is distinct from ({', '.join(f'excluded.{c}' for c in updates)}) "
        "returning (xmax = 0) as inserted"
    )


def to_value(column, value):
    if value is None or value.strip() == "":
        return None
    if column == "raw":
        return Jsonb(json.loads(value))
    if column in INTEGER_COLUMNS:
        return int(value)
    return value


def load(table, columns, key, file, skip=None, limit=None):
    """Upsert rows from a CSV. `skip(row, conn)` returns a reason to skip a row, or None.
    `limit` caps the rows written (inserted + updated + unchanged) this run, for samples.
    Returns {skip reason: count}."""
    sql = upsert_sql(table, columns, key)
    inserted = updated = unchanged = skipped = errors = 0
    reasons = {}
    with connect(pooled=True) as conn, open(file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if limit is not None and inserted + updated + unchanged >= limit:
                break
            missing = [c for c in columns if c not in row]
            if missing:
                sys.exit(f"{file} is missing columns: {missing}")
            reason = skip(row, conn) if skip else None
            if reason:
                skipped += 1
                reasons[reason] = reasons.get(reason, 0) + 1
                logging.info("skipped %s: %s", row[key], reason)
                continue
            try:
                result = conn.execute(sql, [to_value(c, row[c]) for c in columns]).fetchone()
            except (psycopg.Error, ValueError) as e:
                errors += 1
                log_error(table, row.get(key), e, row)
                continue
            if result is None:
                unchanged += 1
            elif result[0]:
                inserted += 1
            else:
                updated += 1
    logging.info(
        "%s: %d inserted, %d updated, %d unchanged, %d skipped, %d errors%s",
        table, inserted, updated, unchanged, skipped, errors,
        f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "",
    )
    return reasons


def load_contacts(file, limit=None):
    logging.info("loading contacts: their companies must already be loaded (companies first, then contacts)")
    reasons = load("contacts", CONTACT_COLUMNS, "person_linkedin_url", file, skip=skip_contact, limit=limit)
    missing = reasons.get("company not loaded yet")
    if missing:
        logging.warning("%d contacts skipped because their company isn't in gtm.companies. "
                        "Load the matching companies file first, then re-run this contacts load.", missing)


def stats():
    with connect(pooled=True) as conn:
        for label, sql in [
            ("companies", "select count(*) from gtm.companies"),
            ("contacts", "select count(*) from gtm.contacts"),
            ("companies with a contact", "select count(distinct company_domain) from gtm.contacts"),
            ("companies without a contact",
             "select count(*) from gtm.companies c where not exists "
             "(select 1 from gtm.contacts p where p.company_domain = c.domain)"),
        ]:
            print(f"{label:<28} {conn.execute(sql).fetchone()[0]}")
        tiers = conn.execute("select icp_tier, count(*) from gtm.contacts group by 1 order by 1").fetchall()
        print("contacts by icp_tier         " + ", ".join(f"{t}: {n}" for t, n in tiers))


def export_companies(include_with_contact):
    """Write companies from gtm.companies (by default only those with no contact yet) to a CSV
    the contact search can read. Returns the file path."""
    out = ROOT / "data" / "processed" / f"companies_supabase_{date.today().isoformat()}.csv"
    sql = "select name, domain, linkedin_url from gtm.companies c"
    if not include_with_contact:
        sql += " where not exists (select 1 from gtm.contacts p where p.company_domain = c.domain)"
    rows = 0
    with connect(pooled=True) as conn, open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "domain", "linkedin_url"])
        for row in conn.execute(sql + " order by domain"):
            writer.writerow(row)
            rows += 1
    logging.info("exported %d companies%s to %s", rows,
                 "" if include_with_contact else " without a contact", out.relative_to(ROOT))
    return out


def skip_contact(row, conn):
    if not row["first_name"].strip():
        return "no first name"
    # Only load contacts whose company is already in the database, so a sample load
    # (or a partial companies load) never breaks the companies <- contacts link.
    if conn.execute("select 1 from gtm.companies where domain = %s", (row["company_domain"],)).fetchone() is None:
        return "company not loaded yet"
    return None


def main():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["migrate", "load", "load-companies", "load-contacts", "export-companies", "stats"])
    parser.add_argument("file", nargs="?", help="CSV to load (load-companies / load-contacts)")
    parser.add_argument("--companies", help="companies CSV (load command)")
    parser.add_argument("--contacts", help="contacts CSV (load command)")
    parser.add_argument("--limit", type=int, help="max rows to load this run (sample-before-scale)")
    parser.add_argument("--all", action="store_true", help="export-companies: include companies that already have a contact")
    args = parser.parse_args()
    if args.command.startswith("load-") and not args.file:
        parser.error(f"{args.command} needs a CSV file")
    if args.command == "load" and not (args.companies and args.contacts):
        parser.error("load needs --companies FILE and --contacts FILE")
    for path in [args.file, args.companies, args.contacts]:
        if path and not Path(path).is_file():
            parser.error(f"file not found: {path}")

    if args.command == "migrate":
        migrate()
    elif args.command == "load":
        load("companies", COMPANY_COLUMNS, "domain", args.companies, limit=args.limit)
        load_contacts(args.contacts, limit=args.limit)
    elif args.command == "load-companies":
        load("companies", COMPANY_COLUMNS, "domain", args.file, limit=args.limit)
    elif args.command == "load-contacts":
        load_contacts(args.file, limit=args.limit)
    elif args.command == "export-companies":
        export_companies(args.all)
    else:
        stats()


if __name__ == "__main__":
    main()
