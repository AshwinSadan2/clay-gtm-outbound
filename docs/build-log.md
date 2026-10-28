# Build Log

Running record of what was built, decided and run in this project, newest session first.

---

## Session 4 — 2026-10-27 · Debounce validation, DetectZeStack tech stack, migration 005, two skills

Full log: `docs/build-log-2026-10-27.md`.

---

## Session 3 — 2026-10-23 · Icypeas email enrichment, migration 004, `icypeas-email-fetch` skill

**Goal:** find work emails for the clean contact list with Icypeas, store them permanently in Supabase, and package the flow as a skill.
**Outcome:** ✅ 155 of 270 clean contacts searched: **115 emails found (74%)**, 40 not found, 0 errors, all loaded to `gtm.contacts`. Migration 004 applied. New skill `/icypeas-email-fetch`. 115 contacts left for the skill's first real run.

### What was built

| Area | Files |
|---|---|
| Keys | `ICYPEAS_API_KEY`, `ICYPEAS_API_SECRET` in `.env` / `.env.template` |
| API reference | `docs/icypeas-api-reference.md` (9 points; polling limits; confirmed live against a real response) · copy in the skill's `references/` |
| Clean contact list | `data/processed/contacts_clean_2026-10-23.csv`: 287 contacts − 17 at suppressed companies = **270** |
| Email search | `icypeas_email_search.py`: submit (5/s) → save each search id → poll 100 results per read (≤30 reads/min) → stream each result. Resumable (`--resume`, never resubmits). `--probe` (key; `--account-email` adds credits), `--dry-run`, `--limit`. Every input, column and output is a flag |
| Results file | `data/processed/contacts_email_enriched_2026-10-23.csv` (one file, appended per run) · raw: `data/raw/contacts_email_enriched_2026-10-23.{jsonl,state.json}` |
| Database | `db/migrations/004_contacts_email.sql`: `email` (citext, unique), `email_mx_provider`, `email_enriched_at`, `email_validation`, `email_validation_at`, `email_search_id`, **generated** `email_status` |
| Loader (`data.py`, 3 identical copies) | `load-emails FILE --id-column COL` (update only, never insert) · `export-contacts [--all] [--exclude-domains FILE --exclude-column COL]` · `stats` shows email status |
| Skill | `.claude/skills/icypeas-email-fetch/`: `SKILL.md` (106 lines), `scripts/` (search, `review_results.py`, `data.py`, `probe_connections.sh`), `references/` (API reference, `run-and-load.md`), empty `assets/`, own `.env.template` |

### Timeline

| Time | Step | Result |
|---|---|---|
| ~07:15 | Project read-in; Icypeas keys added to `.env` / template | |
| ~07:25 | Clean contacts exported from Supabase | 270 (suppressed domains excluded) |
| ~07:35 | Icypeas docs read → API reference | async · key-only auth · polling 30/min |
| 07:44 | Script tested against a fake Icypeas | sample · refuse without `--resume` · cut-off polling · resume: all ✅ |
| 07:48 | Probe + **sample of 5** | 4 found, all `ultra_sure`, 6 s |
| 07:50 | **Next 50** | 35 found (70%), 0 off-domain |
| 07:53 | **Next 100** (into the single enriched CSV) | 76 found; tiers 1: 80% · 2: 73% |
| ~08:00–08:15 | Profile → schema rounds with user → sign-off | |
| 08:18 | **Migration 004 applied** (tracked in `gtm.schema_migrations`) | |
| 08:19 | Load 10 → user review → load rest (08:24) | 155 loaded · re-run 0 changes |
| 08:26 | Scripts parameterised; results CSV converted to new columns | loader re-run: 155 unchanged ✅ |
| 08:31 | Skill built; export-contacts tested | 115 exported = exactly the unsearched clean contacts |

### Key decisions

| Decision | Why |
|---|---|
| Single email search + polling, not bulk + webhooks | No public server; polling in pages of 100 fits the 30 reads/min limit |
| Auth = API key only; secret unused | Key-only auth since Icypeas v1.4.0; secret only verifies webhooks |
| One results CSV per list, appended each run (`contacts_email_enriched_<date>.csv`) | User: no second CSV |
| Gates 5 → 50 → 100 this session; skill: 5 → 100 → rest, batches of 50,000 when large | User's sample-before-scale rule |
| Email columns on `gtm.contacts`, not a new table | One email per person |
| `email_status` = `found` / `not_found` only, **generated** from `email_enriched_at` + `email` | Icypeas's DEBITED states are billing, not outcomes. Never-searched people (e.g. suppressed) must have no status |
| Dropped `email_certainty`, `email_source`, `email_raw` | User doesn't trust provider confidence; one provider; raw adds nothing (kept on disk in `data/raw/`) |
| Added `email_validation` / `email_validation_at` (empty) | A separate validation tool comes later |
| Migration tracked in `gtm.schema_migrations`, not `supabase_migrations.schema_migrations` | The Supabase table holds only the movies project's history |
| Required flags have no defaults (input, output, the four columns) | A forgotten flag stops the run instead of reusing this campaign's values |

### Final state

| | |
|---|---|
| `gtm.contacts` email status | found **115** · not_found **40** · not searched 132 (115 still to run + 17 suppressed) |
| Icypeas | ~115 credits used (1 per email found; see the `DEBITED_NOT_FOUND` caveat below) |
| Blitz | 388 records left (unchanged), resets 2026-11-02 |
| Data files (git-ignored) | `contacts_clean_2026-10-23.csv` · `contacts_email_enriched_2026-10-23.csv` · `contacts_supabase_2026-10-23.csv` (the 115 left) · `data/raw/contacts_email_enriched_2026-10-23.*` |

### Issues hit and how they were handled

- **Icypeas keys printed in the chat.** The user had pasted them as `Label - value`. I ran the masked view and a length check in one command, so the check printed both values. The keys were kept for this exercise (user's call). Fixed by: the masked view now runs on its own command first (project memory + `SKILL.md` Step 0); the two lines were rewritten as `KEY=value` by a script that prints nothing. **Rotate both keys before any real use.**
- **"Clean companies CSV" didn't exist.** Only the suppression list did. The clean contact list was built as all contacts minus suppressed domains.
- **`DEBITED_NOT_FOUND`:** 34 misses carry a "debited" status, but Icypeas docs say misses are free. Unconfirmed; check the dashboard's credits used against 115.
- **Validation errors return HTTP 200** (`success: false`). The script checks `success`, not just the code.
- **Garbled names from LinkedIn** (e.g. symbols after a surname) still find emails but need cleaning before outreach.
- **Polling at scale:** 50,000 pending ≈ 18 min per polling round. Fine for now; the bulk route is the upgrade if lists get large.

### Next session

1. Run `/icypeas-email-fetch` on the **115 remaining** contacts (Supabase source), through every gate. First live test of the credit probe (needs the Icypeas login email).
2. Confirm whether `DEBITED_NOT_FOUND` costs credits (dashboard vs found count).
3. Pick an email validation tool → fill `email_validation` / `email_validation_at` (a new migration only if values need a check constraint).
4. `first_name_clean` / name cleaning before copy.
5. Rotate the Icypeas key and secret.

---

## Session 2 — 2026-10-21 · Parameterised pipeline, three skills, Attio suppression gate

**Goal:** make the session-1 engine reusable for any campaign without code changes, package it as skills, and build CRM suppression from Attio.
**Outcome:** ✅ Three local skills: `/fetch-companies-push`, `/fetch-contacts-push`, `/suppression-gate`. All scripts checked live (compile · network · provider). No database rows changed. Blitz: 394 → **388** records (6 spent on live tests).

### What was built

| Area | Files |
|---|---|
| Company pull, parameterised | `blitz_company_search.py`: `--industry`, `--keyword`, `--employee-range`, `--country` (all repeatable, required) · `--dry-run` · `--probe` (1-record match count, saves nothing) · resume refuses changed filters (`.filters.json`) |
| Contact pull, parameterised | `blitz_contact_search.py`: `--companies FILE` · `--tier` ×1–10 (Waterfall ICP) **or** `--title` (People Search, `icp_tier` 1) · `--exclude-title`, `--tier-exclude N`, `--headline-tier N`, `--location` · `--dry-run` |
| Loader | `data.py`: `load --companies --contacts` (always companies first) · `export-companies [--all]` (companies with no contact → CSV for the contact search) · warning when contacts skip for a missing company |
| Database | `db/migrations/003_contacts_icp_tier_up_to_10.sql`: `icp_tier` check widened 1–6 → 1–10 (applied) |
| Skills | `.claude/skills/fetch-companies-push/` and `fetch-contacts-push/`: `SKILL.md` (109 / 113 lines) + `scripts/` + `references/` (filter rules, title-matching rules, push rules, **535 Blitz industry strings**) + `assets/` (intake questions, Clay worked examples) |
| Portability | Scripts treat the run folder as the project, accept `--env PATH`, and create `data/` / `logs/` if missing. `scripts/` folder retired: code lives in the skills; `data.py` and `probe_connections.sh` are identical copies per skill |
| Attio | `ATTIO_API_KEY` in `.env` / `.env.template` (read-only scopes) · `probe_connections.sh` now checks Attio too |
| Suppression scripts | `attio_profile.py` → `attio_download.py` → `attio_suppress.py` (preview by default, `--apply` writes) + shared `attio_common.py` |
| Suppression skill | `.claude/skills/suppression-gate/`: `SKILL.md` (109 lines) · own `.env.template` (keys it needs, no values) · `references/` (categories + levels + matching; Attio fields and known gaps) · `assets/` (intake questions + sign-off wording; worked example with today's numbers) · `scripts/` |

### Timeline

| Time | Step | Result |
|---|---|---|
| ~07:10 | Profiled the 3 scripts; listed the hard-coded values | user: flags, not config files; change the engine as little as possible |
| 07:18 | Company filters + contact cascade → flags | flag-built requests checked **identical** to the approved 2026-10-19 ones |
| 07:22 | Contact modes: cascade (1–10 tiers) or single title; migration 003 applied | Employee Finder rejected: it can't filter by job title |
| 07:24 | Loader: ordered `load`, missing-company warning | re-load of 300 + 287 = all unchanged |
| 07:32 | Validation round 1: compile · network · live calls | all ✅ (3 Blitz records; test outputs in a throwaway folder) |
| 07:46 | Split into two skills | re-validated live from the new location (2 records) |
| 07:54 | `--env` flag + auto-created folders | tested from an empty folder (1 record) |
| 07:55 | Attio key added; probe | active, workspace *Bootprint-CEM*, read-only scopes |
| ~08:00 | Full CRM profile + overlap with our 300 | 30 CRM domains hit a rule; **18 of our 300** |
| 08:06 | First suppression CSV + raw Attio copy + opt-out file | `suppression_attio_2026-10-21.csv` (30 rows) |
| 08:22 | Suppression script: categories, levels, modes as flags | offline-tested against the saved raw pull |
| 08:26 | Split into 3 staged scripts; `in_conversation`; email-only contact level | offline + synthetic tests ✅ |
| 08:29 | Validation round 2 (suppression): compile · network (+ Attio) · live | all ✅: 18 suppressed / 282 clean; contact level vs Supabase correctly refused (no emails yet) |
| ~08:35 | Session commits pushed to GitHub | |
| ~08:40 | Wrapped as local skill **`suppression-gate`** (renamed from `suppress-crm`) with its own `.env.template` | `SKILL.md` 109 lines; live stage-1 run from the new path = 30 domains |

### Key decisions

| Decision | Why |
|---|---|
| Campaign values are CLI flags, never config files | An agent always runs the pipeline and turns the brief/user answers into flags; the proven engine stays untouched |
| Filter flags have no defaults | A forgotten flag must stop the run, not silently reuse the Clay filters |
| Single designation → People Search, not Employee Finder | Employee Finder filters only by level / department, not job title |
| Contacts skill reads companies from Supabase (`export-companies`) | Every contact found then has its company loaded, so the FK can't break |
| Skills ask before pushing to Supabase | User sign-off on every write |
| Suppression at **company-domain level**, before contact/email spend | Spend money only on companies we'd actually talk to |
| Categories: customer · competitor · do-not-recontact (all no time limit) · closed-lost (**all Lost, no limit**: Attio has no close date, every record dated 2026-08-10 import) · lead · in progress (while open) · recently contacted · in conversation (`--days`, default 90) · opted out (contact level only) | User's rules |
| Contact level matches on **email only, both sides**; never runs without emails; no-email rows → `_unchecked` | User's rule: never join on LinkedIn URL |
| `in_conversation` holds the whole company at domain level | If an SDR is talking to someone there, no company-level outbound |
| Contact level: people inherit their company's customer / competitor / recently-contacted status | 31 people, all at customers, 30 of them on the Won deal |
| Suppression output is CSV only | Database never changed by suppression |
| Skill named **`suppression-gate`**, a local project skill with its own `.env.template` | User's choice; it gates the list before enrichment spend, at company or contact level |
| Skill flow: preflight → ask level, categories, window → profile → sign-off → download → ask target (CSV or Supabase) → preview → sign-off → `--apply` | Every stage is a user gate; profile shows details when small and counts when big |

### Final state

| | |
|---|---|
| `gtm.companies` / `gtm.contacts` | 300 / 287, unchanged |
| Blitz records | **388 left**, resets 2026-11-02 |
| Attio | 72 companies · 75 people · 25 deals · lists: Customers 10, Active Pipeline 8, Newsletter Unsubscribes 3 |
| Suppression vs our 300 (domain, all categories, 90 d) | **18 suppressed** (7 customer · 1 competitor · 1 do-not-recontact · 3 closed-lost · 4 in progress · 2 recently contacted) · 282 clean · 17 of the 18 already have a contact |
| Data files (git-ignored) | `data/raw/attio_*_2026-10-21.jsonl` · `data/processed/suppression_attio_2026-10-21.csv`, `optout_attio_2026-10-21.csv`, `companies_supabase_2026-10-21.csv` |

### Issues hit and how they were handled

- **Hard-coded `--companies-date 2026-10-19`** in the contact script → replaced by `--companies FILE`.
- **`icp_tier` capped at 6** in the database → migration 003 (1–10) before any longer cascade could load.
- **Inline comment in `.env.template`** would have become the key's value if copied → moved onto its own line.
- **Stray space before the Attio key** in `.env` → removed without displaying the value.
- **Attio dates are import dates**: every record and deal stage is dated 2026-08-10, so closed-lost can't be windowed. Decision: suppress all Lost.
- **Attio interaction fields empty** (no mailbox/calendar sync); notes, tasks, threads and meetings are out of the key's scope → `in_conversation` is built but matches nobody yet.
- **Deal owner names** need the Attio *User Management: read* scope → only the owner ID is kept for now.
- **Blitz reference path** given by the user was on another machine → used Blitz's live OpenAPI spec instead.

### Next session

1. **Run `/suppression-gate` end to end** as a skill (so far only its scripts have run live), then hook it into `fetch-companies-push` after the push.
2. **Feed the clean list onward**: the contact skill should skip suppressed domains (today it reads `export-companies`).
3. **Email enrichment** (Icypeas) → `email_*` columns via migration **004** (003 is used). This also unlocks contact-level suppression.
4. Optional Attio scopes: *User Management: read* (deal owner names); mailbox/calendar sync (`in_conversation`).

---

## Session 1 — 2026-10-19 · List building (Blitz → Supabase)

**Goal:** stand up the project and build the Clay target list: US SaaS companies (51–200) and the best marketing / RevOps leader at each, stored in Supabase.
**Outcome:** ✅ 300 companies and 287 contacts in Supabase (`gtm` schema). Blitz trial: 394 records left of 1,000.

### What was built

| Area | Files |
|---|---|
| Project scaffold | `docs/`, `data/{raw,processed,exports}/`, `scripts/`, `db/migrations/`, `logs/`, `.env`, `.env.template`, `.gitignore`, `CLAUDE.md` |
| Rules | `CLAUDE.md`: folder map, secrets handling, **API fetch rules** (stream never buffer · resumable · separate error log, don't panic) |
| Blitz reference | `docs/blitz-api-reference.md`: base URL, auth, endpoints, request/response shapes, rate limits, errors, pagination, sync vs async |
| Connection check | `scripts/probe_connections.sh`: Blitz key + Supabase URL / direct DB / pooler DB, pass/fail only |
| Company pull | `scripts/blitz_company_search.py`: cursor-paginated, resumable via saved cursor, streams JSONL + CSVs |
| Contact pull | `scripts/blitz_contact_search.py`: Waterfall ICP, 4 parallel workers under a shared 4.5 req/s limiter, resumable per company |
| Database | `db/migrations/001_gtm_companies.sql`, `002_gtm_contacts.sql`; `scripts/data.py` (migrate / load / stats over the transaction pooler) |
| Design docs | `docs/company-search-request.md`, `docs/contact-search-request.md`, `docs/schema-companies.md`, `docs/schema-contacts.md` |

### Timeline

| Time | Step | Result |
|---|---|---|
| 07:15 | Scaffold project, `CLAUDE.md` | |
| 07:32 | Probe connections | Blitz ✅ (Startup Trial, 988 records, 5 req/s) · Supabase URL ✅ · direct ✅ · pooler ✅ (Postgres 17) |
| 07:33 | Blitz API reference written | from docs.blitz-api.ai + OpenAPI spec |
| 07:35 | Company search request proposed → **approved** | Software Development · `SaaS` keyword · 51–200 · HQ US |
| 07:37 | **Sample: 10 companies** | 10 records · 1,910 companies match in total |
| 07:40 | API fetch rules added to `CLAUDE.md`; script brought in line | streaming CSVs, separate error log (tested with a bad key: 401 logged, no crash) |
| 07:49 | Column audit → review CSV columns agreed; `raw` JSON column added | |
| 07:55 | **Scale: companies 11–300** | 290 records in 6 cursor pages, 3 s, 0 errors |
| 07:56 | Contact search (Waterfall ICP, 6 tiers) proposed → **approved** | |
| 07:58 | **Sample: 10 contacts** | 10/10 found · tiers 1×5, 2×4, 5×1 |
| 08:01 | Scale started, interrupted by user at 226/300 | Streaming held: 216 saved, 0 lost, 0 paid-for-and-lost |
| 08:03 | **Resumed in background: last 74** | 74/74 found, 17 s, 0 errors |
| 08:13 | Companies profiled → schema proposed | |
| 08:19 | User's revised companies schema adopted | |
| 08:23 | Natural-key redesign: `companies` (domain `citext` PK), contacts PK `linkedin_url` | |
| 08:25 | User's final contacts schema → **migrations applied** to Supabase | `gtm.companies`, `gtm.contacts` |
| 08:25 | **Load** | companies 300 inserted · contacts 287 inserted, 5 skipped (no name) · 0 errors |
| 08:26 | Verify | re-run = 0 changes (idempotent) · 0 orphans · citext lookup ✅ · RLS on · movies tables untouched |
| 08:29 | Loader gets `--limit` + FK-safe contact loading; `CONTEXT.md` updated | 5 + 5 reviewed from Supabase (full load kept) |

### Key decisions

| Decision | Why |
|---|---|
| Company filters exactly per brief: Software Development + `SaaS` keyword, LinkedIn band 51–200, HQ US | Sample showed no media / agency leakage. Self-reported band kept even though some companies have more than 200 on LinkedIn (user's call) |
| Waterfall ICP, `max_results: 1`, 6-tier cascade | Mirrors the brief's persona exactly; the API's `icp` field = our `icp_tier` |
| `[Owner]` exact match; founder tier excludes *Chief of Staff*, *Advisor* | Stop *Product Owner* and *Chief of Staff to the CEO* false matches |
| Keep a `raw` JSON column everywhere | Every field Blitz returned is kept unfiltered; trimmed columns can always be recovered |
| Supabase schema `gtm`, not `public` | `public` holds an unrelated movies project; also keeps prospect data off the web API |
| Natural keys, no surrogate IDs | `companies.domain` (`citext`, case-insensitive) · `contacts.person_linkedin_url`; FK `contacts.company_domain → companies.domain` |
| Contacts PK = LinkedIn URL, not domain | Domain as PK would cap contacts at one per company, which was deliberately left open |
| Drop the 5 nameless contacts | Can't fill `{FIRST_NAME}` (Tyfone, Merge, HR Acuity, Nightfall AI, HiredScore) |
| Load only the 292 matched contacts | 8 companies had no match (mostly acquired: Recko→Stripe, Borneo→Atlassian, Spot→Flexera…) |
| Loads via the transaction pooler (6543), DDL via direct (5432) | Per `CONTEXT.md`; pooler can't hold prepared statements, so they're disabled |
| Deferred: `first_name_clean`, email columns, exclusion flag | Clean names at copy stage; `email_*` columns arrive with the Icypeas migration |

### Final state

| | |
|---|---|
| `gtm.companies` | 300 rows |
| `gtm.contacts` | 287 rows · tiers 1: 117 · 2: 41 · 3: 25 · 4: 14 · 5: 77 · 6: 13 |
| Companies without a contact | 13 (8 no-match + 5 nameless) |
| Blitz records | 988 at session start → **394 left** (594 used: 300 companies + 292 contacts + 2 not itemised by Blitz). Resets 2026-11-02 |
| Data files (git-ignored) | `data/raw/{companies,contacts}_blitz_2026-10-19.{jsonl,csv}` · `data/processed/{companies,contacts}_blitz_2026-10-19.csv` |

### Issues hit and how they were handled

- **Size band ≠ real headcount:** 4 of the first 10 companies had 288–888 people on LinkedIn while self-tagged 51–200. Flagged; user kept the band filter.
- **Hidden line break** in one company description split a CSV row. Descriptions now collapse all whitespace; CSVs rebuilt from the untouched JSONL.
- **Interrupted contact run:** the user stopped the scale run at 226/300. Streaming + resume meant nothing was lost or paid twice; the re-run picked up the remaining 74.
- **Placeholder job start dates:** 79 of 277 are 1 Jan, so the column was dropped (still in `raw`).
- **5 contacts with hidden names** → excluded by decision.

### Next session

1. **Suppression** (Session 2): pull already-contacted / customer / open-deal records from Attio and remove matches.
2. **Email enrichment** (Session 3): Icypeas (async submit → poll) into new `email_*` columns via migration `003`.
3. `first_name_clean` at the copy stage (*"FADI"* → *"Fadi"*, *"C. T."* → fallback).
