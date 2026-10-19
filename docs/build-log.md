# Build Log

Running record of what was built, decided and run in this project, newest session first.

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
