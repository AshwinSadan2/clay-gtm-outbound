#!/usr/bin/env python3
"""Supabase helper for the GTM project: run migrations and load CSVs into the gtm schema.

Usage (needs the project virtualenv: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt):
    .venv/bin/python scripts/data.py migrate                 # apply new files in db/migrations
    .venv/bin/python scripts/data.py load-companies FILE     # upsert into gtm.companies on domain
    .venv/bin/python scripts/data.py load-contacts FILE      # upsert into gtm.contacts on person_linkedin_url
    .venv/bin/python scripts/data.py stats                   # row counts and link checks

Loads are upserts, so re-running is safe; unchanged rows are left untouched (updated_at
only moves when something changed). Each row commits on its own: a bad row is logged to
logs/data_errors.log and the load carries on. Contacts with no first name are skipped
(decision 2026-10-19: they can't get {FIRST_NAME}).
Migrations use SUPABASE_DB_URL_DIRECT; loads use SUPABASE_DB_URL_POOLER.
"""
import csv
import json
import logging
import sys
import time
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

ROOT = Path(__file__).resolve().parent.parent
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


def load(table, columns, key, file, skip=None):
    sql = upsert_sql(table, columns, key)
    inserted = updated = unchanged = skipped = errors = 0
    with connect(pooled=True) as conn, open(file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            missing = [c for c in columns if c not in row]
            if missing:
                sys.exit(f"{file} is missing columns: {missing}")
            reason = skip(row) if skip else None
            if reason:
                skipped += 1
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


def main():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
    args = sys.argv[1:]
    if args == ["migrate"]:
        migrate()
    elif len(args) == 2 and args[0] == "load-companies":
        load("companies", COMPANY_COLUMNS, "domain", args[1])
    elif len(args) == 2 and args[0] == "load-contacts":
        load("contacts", CONTACT_COLUMNS, "person_linkedin_url", args[1],
             skip=lambda r: None if r["first_name"].strip() else "no first name")
    elif args == ["stats"]:
        stats()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
