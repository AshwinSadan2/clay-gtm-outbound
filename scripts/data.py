#!/usr/bin/env python3
"""Data helper for the GTM project.

Usage:
    python3 scripts/data.py migrate                 # apply new files in db/migrations
    python3 scripts/data.py import-accounts FILE    # load an accounts CSV (needs a 'domain' column)
    python3 scripts/data.py import-contacts FILE    # load a contacts CSV (needs an 'email' column)
    python3 scripts/data.py stats                   # row counts per table

Uses only the Python standard library. Every run is logged to logs/data.log.
"""
import csv
import logging
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = ROOT / "db" / "migrations"
LOG_FILE = ROOT / "logs" / "data.log"

ACCOUNT_COLUMNS = ["domain", "name", "industry", "employee_count", "country", "icp_tier", "source"]
CONTACT_COLUMNS = ["first_name", "last_name", "title", "email", "email_status", "linkedin_url", "persona"]


def load_env():
    """Read KEY=value lines from .env into os.environ (without printing anything)."""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


def connect():
    db_path = ROOT / os.environ.get("DATABASE_PATH", "db/gtm.sqlite")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT DEFAULT (datetime('now')))")
    applied = {row[0] for row in conn.execute("SELECT filename FROM schema_migrations")}
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in applied:
            continue
        conn.executescript(path.read_text())
        conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,))
        conn.commit()
        logging.info("applied migration %s", path.name)
    logging.info("migrations up to date")


def import_csv(conn, file, table, columns, key):
    with open(file, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if rows and key not in rows[0]:
        sys.exit(f"{file} has no '{key}' column")
    inserted = skipped = 0
    for row in rows:
        values = [row.get(c) or None for c in columns]
        cur = conn.execute(
            f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
            values,
        )
        inserted += cur.rowcount
        skipped += 1 - cur.rowcount
    conn.commit()
    logging.info("%s: %d inserted, %d skipped (duplicates) from %s", table, inserted, skipped, file)


def stats(conn):
    for table in ["accounts", "contacts", "campaigns", "outreach_events"]:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table:<16} {count}")


def main():
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
    )
    load_env()
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    command = sys.argv[1]
    conn = connect()
    if command == "migrate":
        migrate(conn)
    elif command == "import-accounts" and len(sys.argv) == 3:
        import_csv(conn, sys.argv[2], "accounts", ACCOUNT_COLUMNS, "domain")
    elif command == "import-contacts" and len(sys.argv) == 3:
        import_csv(conn, sys.argv[2], "contacts", CONTACT_COLUMNS, "email")
    elif command == "stats":
        stats(conn)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
