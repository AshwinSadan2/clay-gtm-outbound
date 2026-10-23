#!/usr/bin/env python3
"""Supabase helper for the GTM project: run migrations and load CSVs into the gtm schema.

Usage (needs the project virtualenv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt):
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py migrate                 # apply new files in db/migrations
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py load --companies FILE --contacts FILE [--limit N]   # both, companies first
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py load-companies FILE [--limit N]   # upsert into gtm.companies on domain
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py load-contacts FILE [--limit N]    # upsert into gtm.contacts on person_linkedin_url
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py load-emails FILE --id-column COL [--limit N]   # email-enrichment CSV -> email columns of existing contacts
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py export-companies [--all]  # companies CSV for the contact search
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py export-contacts [--all] [--exclude-domains FILE --exclude-column COL]
                                                                    # contacts CSV for email enrichment (default: never searched)
    .venv/bin/python .claude/skills/fetch-contacts-push/scripts/data.py stats                   # row counts and link checks

Loads are upserts, so re-running is safe; unchanged rows are left untouched (updated_at
only moves when something changed). Each row commits on its own: a bad row is logged to
logs/data_errors.log and the load carries on. Contacts are skipped if they have no first name
(decision 2026-10-19: they can't get {FIRST_NAME}) or their company isn't loaded yet.
ORDER MATTERS: companies first, then contacts. Each contact links to its company (foreign key), so
a contact whose company isn't loaded is skipped. `load` does both in the right order.
load-emails only updates contacts already in gtm.contacts: --id-column names the CSV column holding the
person's LinkedIn URL (matched on person_linkedin_url). It never inserts. It reads the CSV columns named after
the database columns (EMAIL_COLUMNS); email_status is computed by the database (migration 004).
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
ENV_FILE = ROOT / ".env"  # --env overrides
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
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
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


# Email-enrichment CSV columns, named exactly as in gtm.contacts (migration 004).
EMAIL_COLUMNS = ["email", "email_mx_provider", "email_enriched_at", "email_search_id"]
EMAIL_SQL = """
update gtm.contacts set email = %(email)s, email_mx_provider = %(email_mx_provider)s,
                        email_enriched_at = %(email_enriched_at)s, email_search_id = %(email_search_id)s
where person_linkedin_url = %(key)s
  and (email, email_mx_provider, email_enriched_at, email_search_id)
      is distinct from (%(email)s::extensions.citext, %(email_mx_provider)s,
                        %(email_enriched_at)s::timestamptz, %(email_search_id)s)
returning 1
"""


def load_emails(file, id_column, limit=None):
    """Write email-enrichment results to the email columns of existing contacts (update only)."""
    updated = unchanged = skipped = errors = 0
    with connect(pooled=True) as conn, open(file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in [id_column] + EMAIL_COLUMNS if c not in reader.fieldnames]
        if missing:
            sys.exit(f"{file} is missing columns: {missing}")
        for row in reader:
            if limit is not None and updated + unchanged >= limit:
                break
            key = row[id_column].strip()
            try:
                params = {"key": key, **{c: row[c].strip() or None for c in EMAIL_COLUMNS}}
                if conn.execute(EMAIL_SQL, params).fetchone():
                    updated += 1
                elif conn.execute("select 1 from gtm.contacts where person_linkedin_url = %s", (key,)).fetchone():
                    unchanged += 1
                else:
                    skipped += 1
                    logging.info("skipped %s: contact not in gtm.contacts", key)
            except (psycopg.Error, ValueError, KeyError) as e:
                errors += 1
                log_error("contacts.email", key, e, {k: v for k, v in row.items() if k != "raw"})
    logging.info("contacts email: %d updated, %d unchanged, %d skipped (not in gtm.contacts), %d errors%s",
                 updated, unchanged, skipped, errors, f" (see {ERROR_LOG.relative_to(ROOT)})" if errors else "")


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
        status = conn.execute("select coalesce(email_status, 'not searched'), count(*) from gtm.contacts "
                              "group by 1 order by 1").fetchall()
        print("contacts by email_status     " + ", ".join(f"{s}: {n}" for s, n in status))


def export_companies(include_with_contact):
    """Write companies from gtm.companies (by default only those with no contact yet) to a CSV
    the contact search can read. Returns the file path."""
    out = ROOT / "data" / "processed" / f"companies_supabase_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
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


EXPORT_CONTACT_COLUMNS = ["first_name", "last_name", "job_title", "icp_tier", "company_name", "company_domain",
                          "website", "person_linkedin_url", "location_country_code", "headline"]


def export_contacts(include_searched, exclude_file=None, exclude_column=None):
    """Write contacts from gtm.contacts (by default only those never email-searched) to a CSV the
    email search can read, skipping companies listed in `exclude_file` (e.g. a suppression CSV)."""
    excluded = []
    if exclude_file:
        with open(exclude_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            if exclude_column not in reader.fieldnames:
                sys.exit(f"{exclude_file} has no column {exclude_column}. Columns: {', '.join(reader.fieldnames)}")
            excluded = sorted({r[exclude_column].strip().lower() for r in reader if r[exclude_column].strip()})
    out = ROOT / "data" / "processed" / f"contacts_supabase_{date.today().isoformat()}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    sql = ("select p.first_name, p.last_name, p.job_title, p.icp_tier, c.name as company_name, p.company_domain, "
           "c.website, p.person_linkedin_url, p.location_country_code, p.headline "
           "from gtm.contacts p join gtm.companies c on c.domain = p.company_domain "
           "where p.company_domain <> all(%s::extensions.citext[])")
    if not include_searched:
        sql += " and p.email_enriched_at is null"
    rows = 0
    with connect(pooled=True) as conn, open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(EXPORT_CONTACT_COLUMNS)
        for row in conn.execute(sql + " order by p.icp_tier, c.name", (excluded,)):
            writer.writerow(row)
            rows += 1
    logging.info("exported %d contacts%s%s to %s", rows, "" if include_searched else " never email-searched",
                 f", excluding {len(excluded)} domains from {exclude_file}" if excluded else "", out.relative_to(ROOT))
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
    parser.add_argument("command", choices=["migrate", "load", "load-companies", "load-contacts", "load-emails",
                                            "export-companies", "export-contacts", "stats"])
    parser.add_argument("file", nargs="?", help="CSV to load (load-companies / load-contacts / load-emails)")
    parser.add_argument("--companies", help="companies CSV (load command)")
    parser.add_argument("--contacts", help="contacts CSV (load command)")
    parser.add_argument("--limit", type=int, help="max rows to load this run (sample-before-scale)")
    parser.add_argument("--id-column", help="load-emails: CSV column holding the person's LinkedIn URL")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    parser.add_argument("--all", action="store_true", help="export-companies: include companies that already have a "
                        "contact; export-contacts: include contacts already email-searched")
    parser.add_argument("--exclude-domains", help="export-contacts: CSV of company domains to leave out (e.g. suppression)")
    parser.add_argument("--exclude-column", help="export-contacts: the domain column in --exclude-domains")
    args = parser.parse_args()
    global ENV_FILE
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    if args.command.startswith("load-") and not args.file:
        parser.error(f"{args.command} needs a CSV file")
    if args.command == "load-emails" and not args.id_column:
        parser.error("load-emails needs --id-column COL (the CSV column holding the LinkedIn URL)")
    if bool(args.exclude_domains) != bool(args.exclude_column):
        parser.error("--exclude-domains and --exclude-column go together")
    if args.command == "load" and not (args.companies and args.contacts):
        parser.error("load needs --companies FILE and --contacts FILE")
    for path in [args.file, args.companies, args.contacts, args.exclude_domains]:
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
    elif args.command == "load-emails":
        load_emails(args.file, args.id_column, limit=args.limit)
    elif args.command == "export-companies":
        export_companies(args.all)
    elif args.command == "export-contacts":
        export_contacts(args.all, args.exclude_domains, args.exclude_column)
    else:
        stats()


if __name__ == "__main__":
    main()
