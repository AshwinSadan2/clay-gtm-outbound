# Clay GTM Outbound — Project Guide

This project runs a sample outbound / go-to-market campaign for **Clay**, set up the way a real GTM team would run it: research and strategy docs, prospect data, enrichment, a local database of accounts/contacts/outreach, and scripts that tie it together.

The owner is not a developer. Explain work in plain English and make technical calls yourself.

## Folder map — where every file goes

| Folder | What goes here | Examples |
|---|---|---|
| `docs/` | Strategy and written work: ICP, personas, messaging, sequences, campaign briefs, research notes, results write-ups | `docs/icp.md`, `docs/personas.md`, `docs/sequences/email-v1.md`, `docs/campaign-brief.md` |
| `data/raw/` | Files exactly as they came in — never edited | Clay / Apollo / LinkedIn exports, purchased lists |
| `data/processed/` | Cleaned, deduped, enriched versions of raw files | `accounts_clean_2026-10-19.csv` |
| `data/exports/` | Final lists ready to load into a sending tool or CRM | `smartlead_upload_tier-a.csv` |
| `scripts/` | Code that does work: importing, cleaning, enriching, scoring, syncing | `scripts/data.py`, `scripts/score_accounts.py` |
| `db/` | The local SQLite database (`db/gtm.sqlite`, created automatically, not committed) | — |
| `db/migrations/` | SQL files that create or change database tables, numbered in order | `001_initial_schema.sql`, `002_add_lead_score.sql` |
| `logs/` | Output from script runs | `logs/data.log` |
| project root | Only config: `CLAUDE.md`, `.env`, `.env.template`, `.gitignore` | — |

### Rules for placing files

- **Never put data files (CSV, JSON, XLSX) in the root, `docs/` or `scripts/`.** They go in `data/raw`, `data/processed` or `data/exports`.
- **Never edit a file in `data/raw/`.** Write a cleaned copy to `data/processed/` instead.
- **Name data files with a date:** `<what>_<YYYY-MM-DD>.csv` (e.g. `contacts_clay_2026-10-19.csv`).
- **Never put markdown/strategy docs in `scripts/` or `data/`.** They go in `docs/`.
- **Database changes go in a new migration file**, never by editing an old one. Use the next number: `002_...sql`, `003_...sql`.
- **Scripts write their logs to `logs/`**, not to the terminal only.
- **Temporary/scratch files** don't belong in this project — use the session scratchpad.

## Secrets (`.env`)

- All API keys live in `.env` (`KEY=value` format). The owner fills it in themselves.
- `.env.template` lists every key name with no values. When a new key is needed, add the name to **both** files — never put a real value in `.env.template`.
- Never print, echo or paste `.env` values. When checking `.env`, first look at it masked (`sed -E 's/[A-Za-z0-9]/x/g' .env`), then report only key names and whether they're filled in.
- `.env`, the database, data files and logs are all in `.gitignore` — prospect data is personal information and must not be committed.

## The data script

`scripts/data.py` (standard Python only, no installs needed):

```
python3 scripts/data.py migrate                  # create/update the database tables
python3 scripts/data.py import-accounts FILE     # load accounts CSV (needs a 'domain' column)
python3 scripts/data.py import-contacts FILE     # load contacts CSV (needs an 'email' column)
python3 scripts/data.py stats                    # how many rows in each table
```

Duplicates (same domain / same email) are skipped automatically.

## API fetch rules (every script that calls an external API)

1. **Stream, never buffer.** Write each record to disk the moment it arrives (append + flush). Never collect results in memory to write at the end.
2. **Resumable.** Save progress (cursor, page, or last processed ID) after every write. A re-run with `--resume` continues from there and never re-fetches or re-pays for done records.
3. **Log errors separately, don't panic.** Write every failed call to `logs/<script>_errors.log` with timestamp, HTTP code, message, and the input/request that failed. Retry only `429`/`500`/`503`; on any other error, log it and move to the next record. If a paginated pull can't continue, save the cursor and exit cleanly. Print an error count at the end of the run for review.

## Connection check

`bash scripts/probe_connections.sh` tests Blitz and Supabase (URL, direct DB, pooler DB) and prints pass/fail only, never key values. Run it before any batch job.

## API references

- Blitz (people/company data, emails): `docs/blitz-api-reference.md`. Our plan is a free trial with ~1,000 records/month and 5 req/s per endpoint, so cap every pull.

## Database tables (Supabase, schema `gtm`)

Never touch the `public` schema: it belongs to an unrelated movies project.

- `gtm.companies` — target companies. Primary key `domain` (case-insensitive `citext`). Design: `docs/schema-companies.md`
- `gtm.contacts` — one marketing/RevOps leader per company. Primary key `linkedin_url`; `company_domain` → `companies.domain`. Design: `docs/schema-contacts.md`
- Both keep the full API response in a `raw` jsonb column. No surrogate ID keys.
- Every schema change is a new numbered file in `db/migrations/`.

## Before sending anything

Nothing gets sent to real prospects, pushed to a CRM, or uploaded to a sending tool without the owner's explicit go-ahead.
