# Clay GTM Outbound — Project Guide

This project runs a sample outbound / go-to-market campaign for **Clay**, set up the way a real GTM team would run it: research and strategy docs, prospect data, enrichment, a local database of accounts/contacts/outreach, and scripts that tie it together.

The owner is not a developer. Explain work in plain English and make technical calls yourself.

**At the start of every session, read `handoff.md` first.** Session history: `sessions/YYYY-MM-DD.md` and the older `docs/build-log*.md`; settled questions: `decisions.md` (check it before reopening a choice).

## Folder map — where every file goes

| Folder | What goes here | Examples |
|---|---|---|
| `docs/` | Strategy and written work: ICP, personas, messaging, sequences, campaign briefs, research notes, results write-ups. LLM prompt files in `docs/prompts/<variable>/` | `docs/icp.md`, `docs/personas.md`, `docs/sequences/email-v1.md`, `docs/campaign-brief.md` |
| `data/raw/` | Files exactly as they came in — never edited | Clay / Apollo / LinkedIn exports, purchased lists |
| `data/processed/` | Cleaned, deduped, enriched versions of raw files | `accounts_clean_2026-10-19.csv` |
| `data/exports/` | Final lists ready to load into a sending tool or CRM | `smartlead_upload_tier-a.csv` |
| `.claude/skills/<skill>/` | Skills and the code they run: `SKILL.md`, `scripts/`, `references/`, `assets/` | `.claude/skills/fetch-companies-push/scripts/data.py` |
| `db/` | The local SQLite database (`db/gtm.sqlite`, created automatically, not committed) | — |
| `db/migrations/` | SQL files that create or change database tables, numbered in order | `001_initial_schema.sql`, `002_add_lead_score.sql` |
| `logs/` | Output from script runs | `logs/data.log` |
| `sessions/` | One session log per working day (`YYYY-MM-DD.md`) | `sessions/2026-10-30.md` |
| project root | Config plus the handoff files: `CLAUDE.md`, `handoff.md`, `decisions.md`, `.env`, `.env.template`, `.gitignore` | — |

### Rules for placing files

- **Never put data files (CSV, JSON, XLSX) in the root, `docs/` or `.claude/skills/`.** They go in `data/raw`, `data/processed` or `data/exports`.
- **Never edit a file in `data/raw/`.** Write a cleaned copy to `data/processed/` instead.
- **Name data files with a date:** `<what>_<YYYY-MM-DD>.csv` (e.g. `contacts_clay_2026-10-19.csv`).
- **Never put markdown/strategy docs in `data/`.** Campaign docs go in `docs/`; a skill's own reference notes go in its `references/`.
- **Database changes go in a new migration file**, never by editing an old one. Use the next number: `002_...sql`, `003_...sql`.
- **Scripts write their logs to `logs/`**, not to the terminal only.
- **Temporary/scratch files** don't belong in this project — use the session scratchpad.

## Secrets (`.env`)

- All API keys live in `.env` (`KEY=value` format). The owner fills it in themselves.
- `.env.template` lists every key name with no values. When a new key is needed, add the name to **both** files — never put a real value in `.env.template`.
- Never print, echo or paste `.env` values. When checking `.env`, first look at it masked (`sed -E 's/[A-Za-z0-9]/x/g' .env`), then report only key names and whether they're filled in.
- `.env`, the database, data files and logs are all in `.gitignore` — prospect data is personal information and must not be committed.

## The skills (list building + suppression + emails + validation + tech stack + LLM variables)

All pipeline code lives in seven local project skills, each with `SKILL.md`, `scripts/`, `references/` and `assets/`:

- **`/fetch-companies-push`** (`.claude/skills/fetch-companies-push/`): Blitz company search → `gtm.companies`. Ends by offering the contacts skill.
- **`/fetch-contacts-push`** (`.claude/skills/fetch-contacts-push/`): reads companies from Supabase → Blitz contact search (title cascade via Waterfall ICP, or a single designation via People Search) → `gtm.contacts`.
- **`/suppression-gate`** (`.claude/skills/suppression-gate/`, with its own `.env.template`): Attio suppression in three gated stages: `attio_profile.py` → `attio_download.py` → `attio_suppress.py` (preview, then `--apply`). Flags: `--level domain|contact`, `--categories`, `--days` (default 90). CSV output only, never a DB change. **Contact level matches on email only and never runs without emails.** Agreed rules: `docs/build-log.md` Session 2.
- **`/icypeas-email-fetch`** (`.claude/skills/icypeas-email-fetch/`, own `.env.template`): CSV or Supabase export → Icypeas email search (submit, then poll) → `gtm.contacts` email columns. Gates: probe (key + credits) → 5 → 100 → rest (batches of 50,000 when large) → push.
- **`/debounce-email-validate`** (`.claude/skills/debounce-email-validate/`, own `.env.template`): email CSV → Debounce validation (synchronous, ≤5 at once) → `gtm.contacts.email_validation` (Debounce `result`). Gates: probe (key + credits) → 5 → 100 → rest → push.
- **`/detectzestack-tech-stack`** (`.claude/skills/detectzestack-tech-stack/`, own `.env.template`): companies CSV or Supabase export → DetectZeStack scan (RapidAPI, synchronous) → full stack to `gtm.companies.tech_stack`; per-client signals distilled to a CSV via a Claude-written `docs/<client>-tech-distiller.md` → config JSON. Gates: 1 → 10 → client distiller + ranking → 100 (hit rate, projection) → full → distil → push. Distilled signals never go to Supabase.
- **`/variable-llm-pipeline`** (`.claude/skills/variable-llm-pipeline/`, own `.env.template`): a CSV column that needs judgment (e.g. `{OPENER}`) via OpenAI GPT-6 Luna. `scripts/openai_stage.py` runs ONE prompt file per run (no stage logic); a pipeline is several runs, each later prompt reading earlier columns. Prompts live only in `docs/prompts/<variable>/stage<N>_<job>_v<K>.md` (settings in the file header; never edit a version that has run). Gates: design → prompts → probe → dry run → 1 → 10 → iterate on a separate sample sheet (10, 20, 30…) → scale choice (now vs Batch, Batch not built yet) → full run. Rule-based variables (`{ROLE}`, `{PS_LINE}`) are never LLM calls: deterministic scripts, e.g. `.claude/skills/mail-merge-variables/scripts/role_variable.py`.

The scripts hold no campaign values. Every filter, title cascade and input file is a flag, so **never edit the scripts for a new campaign**: take the values from the new brief or ask the user. Every run follows: dry run → sign-off → 10-record sample → profile → scale → ask → push. Scripts treat the folder they're run from as the project (creating `data/` and `logs/` if missing) and read `.env` from it, so run them from the project root. Every script, including `probe_connections.sh`, takes `--env PATH` for a `.env` stored elsewhere.

`data.py` (Supabase loader) and `probe_connections.sh` are identical copies in every skill's `scripts/` that has them. **If you change one, change all.** Loader commands (`.venv/bin/python .claude/skills/<skill>/scripts/data.py ...`):

```
migrate                                  # apply new files in db/migrations (direct connection)
load --companies FILE --contacts FILE    # both, companies first
load-companies FILE / load-contacts FILE # upsert into gtm.companies (domain) / gtm.contacts (person_linkedin_url)
load-emails FILE --id-column COL        # email-enrichment CSV → email columns of existing contacts (update only)
load-validation FILE --id-column COL    # email-validation CSV → email_validation(_at), only where the stored email matches
export-companies [--all]                 # companies with no contact yet (--all: every company) → CSV for the contact search
export-companies --email-validation V --tech not-scanned|scanned --output FILE   # filters combine; scanned adds tech_stack
load-tech FILE --id-column domain       # tech-stack CSV → tech_stack + tech_enriched_at (update only)
export-contacts [--all] [--exclude-domains FILE --exclude-column COL]  # never email-searched contacts → CSV for the email search
stats                                    # row counts, companies without a contact, tiers
```

Loads are upserts: re-running is safe and leaves unchanged rows untouched. Bad rows go to `logs/data_errors.log` and the load carries on. Contacts without a first name are skipped.

**Companies always load before contacts**: each contact links to its company (foreign key), so a contact whose company isn't in `gtm.companies` is skipped with a warning. Tell the user this order before any load.

## API fetch rules (every script that calls an external API)

1. **Stream, never buffer.** Write each record to disk the moment it arrives (append + flush). Never collect results in memory to write at the end.
2. **Resumable.** Save progress (cursor, page, or last processed ID) after every write. A re-run with `--resume` continues from there and never re-fetches or re-pays for done records.
3. **Log errors separately, don't panic.** Write every failed call to `logs/<script>_errors.log` with timestamp, HTTP code, message, and the input/request that failed. Retry only `429`/`500`/`503`; on any other error, log it and move to the next record. If a paginated pull can't continue, save the cursor and exit cleanly. Print an error count at the end of the run for review.

## Connection check

`bash .claude/skills/fetch-companies-push/scripts/probe_connections.sh` tests Blitz and Supabase (URL, direct DB, pooler DB) and prints pass/fail only, never key values. Run it before any batch job.

## API references

- Blitz (people/company data, emails): `docs/blitz-api-reference.md`. Our plan is a free trial with ~1,000 records/month and 5 req/s per endpoint, so cap every pull.
- Icypeas (email finder): `docs/icypeas-api-reference.md`. Async: submit, then poll. Polling for results is capped at 30 calls/min, so read in pages of 100. Auth is the API key alone; the secret only verifies webhooks.
- Debounce (email validation): `docs/debounce-api-reference.md`. Synchronous, 5 calls at once, 1 credit each. The key travels in the URL (`api=`), so never log request URLs. Never use bulk upload (needs the list on a public URL).
- OpenAI (LLM variables): `docs/openai-api-reference.md`. Responses API; GPT-6 Luna $0.10/$0.50 per 1M tokens; `temperature`, `top_p` and log-probabilities only with effort `none`. Key `OPENAI_API_KEY`.
- DetectZeStack (tech stack, via RapidAPI): `docs/detectzestack-api-reference.md`. Synchronous `GET /analyze?url=`. Free plan 100 calls/month and **RapidAPI counts every call** (failures too). Needs a browser-style User-Agent. Headers `x-rapidapi-key` + `x-rapidapi-host`.

## Database tables (Supabase, schema `gtm`)

Never touch the `public` schema: it belongs to an unrelated movies project.

- `gtm.companies` — target companies. Primary key `domain` (case-insensitive `citext`). Tech stack: `tech_stack` (jsonb type → tools) + `tech_enriched_at` (migration 005). Design: `docs/schema-companies.md`
- `gtm.contacts` — one marketing/RevOps leader per company. Primary key `linkedin_url`; `company_domain` → `companies.domain`. Design: `docs/schema-contacts.md`
- Both keep the full API response in a `raw` jsonb column. No surrogate ID keys.
- Every schema change is a new numbered file in `db/migrations/`.

## Mistakes not to repeat

- Pasted answers once named a contact ("Art") and `_v2` columns that matched nothing in the sheet. Rule: when pasted instructions refer to rows, names or columns that don't exist here, say so and ask before changing anything.

## Before sending anything

Nothing gets sent to real prospects, pushed to a CRM, or uploaded to a sending tool without the owner's explicit go-ahead.
