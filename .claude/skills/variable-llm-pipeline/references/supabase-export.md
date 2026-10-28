# Exporting the input CSV from Supabase (written fresh at each run)

Use this when the user has no CSV, but the rows are in Supabase. The pipeline's columns depend on the prompts,
so there is no fixed export script. Claude writes a small **read-only** export for this run, from these notes.

## Rules

- **Read only.** `SELECT` only. Never `INSERT/UPDATE/DELETE/ALTER`.
- **Schema `gtm` only.** Never `public`: it holds an unrelated movies project.
- **Where the code lives:** the export script goes in the session **scratchpad**, not the project (scratch code
  doesn't belong there).
- **Where the CSV goes:** `data/processed/<what>_supabase_<YYYY-MM-DD>.csv`.
- **Connection:** `SUPABASE_DB_URL_POOLER` from `.env`, read by the script. Never print it.
  - Run the masked `.env` view first, as its own command.
  - Use `psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=10)`. The transaction
    pooler can't hold prepared statements.
- **Run it with** the project's `.venv/bin/python` (psycopg is installed there), from the project root.
- **Before writing:** show the user the SQL. After the run: show the header, the row count and how full each
  needed column is. Never print the rows themselves (personal data).

## What is where

| Need | Table.column | Notes |
|---|---|---|
| Row id (one per person) | `gtm.contacts.person_linkedin_url` | Primary key. Use it as `--id-column` |
| First / last name, title, headline | `gtm.contacts.first_name, last_name, job_title, headline` | |
| Contact's LinkedIn About | `gtm.contacts.about_me` | Often empty or short: plan a fallback variant |
| Seniority tier | `gtm.contacts.icp_tier` | 1 = most senior |
| Email + checks | `gtm.contacts.email, email_status, email_validation` | Mailable = `email_validation in ('Safe to Send','Risky')` |
| Company name, domain, About | `gtm.companies.name, domain, about` | Join on `contacts.company_domain = companies.domain` |
| Company size, industry, country | `gtm.companies.employees_on_linkedin, industry, hq_country_code` | |
| Full tech stack | `gtm.companies.tech_stack` (jsonb type → tools), `tech_enriched_at` | Campaign-distilled signals are NOT in the DB: they live in `data/processed/distilled_tech_stack_*.csv` |
| Anything else from the source API | `raw` jsonb on both tables | e.g. `c.raw->>'founded_year'` |

Full designs: `docs/schema-contacts.md`, `docs/schema-companies.md`.

## Shape of the export (adapt the columns and the filter)

```python
import csv, sys, psycopg
from pathlib import Path
url = next(l.split("=", 1)[1].strip() for l in Path(".env").read_text().splitlines()
           if l.startswith("SUPABASE_DB_URL_POOLER="))
sql = """
select p.person_linkedin_url, p.first_name, p.last_name, p.job_title, p.headline, p.about_me, p.icp_tier,
       p.email, p.email_validation, c.name as company_name, c.domain as company_domain, c.about as company_about
from gtm.contacts p join gtm.companies c on c.domain = p.company_domain
where p.email_validation in ('Safe to Send', 'Risky')
order by c.name
"""
out = sys.argv[1]
with psycopg.connect(url, autocommit=True, prepare_threshold=None, connect_timeout=10) as conn, \
        open(out, "w", newline="") as f:
    cur = conn.execute(sql)
    w = csv.writer(f)
    w.writerow([d.name for d in cur.description])
    n = 0
    for row in cur:          # stream: write each row as it arrives
        w.writerow(row)
        n += 1
print(f"{n} rows -> {out}")
```

Name columns after the `{{variables}}` the prompts use (e.g. `c.about as company_about`). Then no `--var`
mapping is needed.

**Joining local-only data** (e.g. distilled tech signals, a role column from a deterministic script): load the
export and the local CSV in the same scratchpad script, join on `company_domain` / `person_linkedin_url`, and
write one combined CSV.
