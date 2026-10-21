# Project Vocabulary

<!--
This file tells Claude what words mean in THIS project. Without it, Claude
guesses domain language session-to-session and the guesses drift.

Two sections: "Project terms" (campaign-specific, grounded in BRIEF.md) and
"Stack terms" (technical vocabulary Claude will meet in our code).

Extend the Project terms section as new campaign-specific words come up.
Copy-specific vocabulary (angles, pain blocks, merge tags) is NOT here yet —
it arrives with the copy session.
-->

## Project terms

Terms specific to this campaign. Grounded in `BRIEF.md`.

- **Client** — Clay (clay.com), the GTM data platform whose outbound we're building. The whole shared brief runs as if we were Clay's growth team.
- **Target market** — marketing leaders at US SaaS companies with 51–200 employees. The people who feel the pains Clay removes.
- **Persona** — the best-available **marketing or RevOps leader** at each account, via a 6-tier title cascade: senior marketing (VP/SVP/CMO, tier 1) → Head of Marketing/Growth (tier 2) → Director of Marketing/Demand Gen (tier 3) → RevOps leadership (tier 4) → founder fallback (tier 5) → manager/IC + headline catch-all (tier 6). First tier with a match wins; `icp_tier` records which.
- **icp_tier** — integer on each contact recording which cascade tier matched. The database allows 1–10 (the cascade is set per campaign by flags); a single-title search (no cascade) stores 1. In the Clay cascade: 1 = senior marketing/VP/CMO, 2 = Head, 3 = Director, 4 = RevOps, 5 = founder, 6 = manager/IC. Lets us filter to the most senior marketers (tiers 1–3) when it matters.
- **Best-available marketing leader** — what the persona resolves to in practice: the exact title "VP of Marketing" is uneven across 51–200-person companies, so we take the most senior marketing leader the cascade finds rather than requiring one literal title.
- **Title cascade** — the tiered title search that defines the persona in practice (see Persona above and BRIEF.md). Excludes `assistant, intern, junior, coordinator, freelance`.
- **RevOps (adjacent buyer)** — Clay's other core buying center (VP/Head/Director of Revenue Operations · RevOps · GTM Engineer). In the cascade as tier 4, below the marketing tiers and above the founder fallback — the more direct Clay buyer at this company size. See BRIEF.md.
- **Software Development** — the exact LinkedIn industry string for our target companies. Blitz expects this literal value, not loose synonyms like "SaaS" or "Tech".
- **SaaS keyword filter** — the `keywords.include: ["SaaS"]` added to Blitz company search on top of the industry tag. "Software Development" alone surfaces tech-MEDIA brands (TechCrunch, Entrepreneur) that self-tag under it; the SaaS keyword biases toward real B2B software vendors. Keep the include list tight — it's OR-within-array, so loose terms like "software" re-broaden it. See BRIEF.md.
- **Company size band** — the 51–200 employee filter. Companies outside it are out of market for this campaign.
- **Geography** — United States (company HQ). Contact location is `WORLD` — the company is US-based but its marketing leader may sit anywhere.
- **Funding filter** — deliberately *not* applied (parked, out of scope). *Note: Blitz company search **does** support funding filters (`last_funding_type`, `total_funding`, `lead_investors`) — the earlier claim that it didn't was wrong. Left out by choice, not capability.*
- **In market** — a company that satisfies every brief filter at once: Software Development / SaaS, 51–200 employees, US-based, with a marketing leader to reach.
- **Target list** — the 300 SaaS companies and 287 marketing-leader contacts Session 1 produced (Blitz, 2026-10-19) and stores in Supabase (`gtm` schema). 13 companies have no contact: 8 no-match (mostly acquired) + 5 whose contact has no name on LinkedIn.
- **Account–contact link** — the foreign-key relationship storing each marketing leader (contact) against their company via `contacts.company_domain` → `companies.domain`.
- **Suppression list** — the set of records we must NOT email: anyone already in the CRM as contacted, opted-out, a current customer, or an open opportunity. Session 2 pulls this from Attio and removes matches from the send list. Suppression is *not* deduplication — see Stack terms.

## Stack terms

Technical vocabulary used throughout the project.

- **Account / company** — a company in our target market. Stored in the `gtm.companies` table (primary key `domain`, case-insensitive).
- **Contact** — a person at a company. Stored in the `gtm.contacts` table (primary key `linkedin_url`). Linked to its company via `company_domain` (→ `companies.domain`).
- **Skill** — a reusable Claude Code tool defined by a `SKILL.md` plus optional scripts. Invoked with `/skill-name`.
- **Plan mode** — Shift+Tab in Claude Code. Claude proposes a plan instead of executing.
- **Upsert** — SQL pattern `ON CONFLICT (key) DO UPDATE`. Inserts that update on conflict instead of erroring. Makes scripts re-runnable.
- **Idempotent** — runnable any number of times with the same final result. Our scripts are idempotent because they upsert.
- **Pooler** — Supabase's **transaction pooler** on port 6543 (`SUPABASE_DB_URL_POOLER`). All data loads go through it; it can't hold prepared statements, so the loader turns them off. Migrations (DDL) use the direct connection on port 5432 (`SUPABASE_DB_URL_DIRECT`).
- **`gtm` schema** — where all campaign tables live in Supabase. `public` belongs to an unrelated movies project and is never touched.
- **Natural keys** — no surrogate ID columns. `companies.domain` (case-insensitive `citext`) and `contacts.person_linkedin_url` are the primary keys.
- **Loader** — `data.py` (in each skill's `scripts/`): `migrate`, `load`, `load-companies`, `load-contacts`, `export-companies`, `stats`. Idempotent upserts, one commit per row, bad rows to `logs/data_errors.log`. Contacts load only if their company is already loaded (keeps the foreign key intact) and they have a first name.
- **Sample load** — sample-before-scale for the database: `--limit 5` loads the first 5 companies, then the 5 contacts belonging to them, for review before the full load.
- **Raw jsonb** — the `raw` column on `companies` and `contacts` holding the full API response. Our escape valve when APIs add new fields we want later.
- **Sample-before-scale** — discipline of running every paid-API script on `--limit=10` first and eyeballing the output before running on the full list.
- **Streaming / resumable** — write each record to the CSV as it arrives (never buffer the whole run in memory) and keep a cursor so a crash resumes from the last saved row instead of re-charging the whole pull.
- **Cursor pagination** — Blitz's pagination pattern: each response includes a cursor token; pass it back for the next page; stop when it returns null.
- **Orchestrate vs execute** — Claude **orchestrates** (plans, decides, asks). Scripts **execute** (do the per-row work). The whole course is built on this split.
- **Suppression vs deduplication** — **dedup** removes repeats *within* our own list (the same person twice). **Suppression** removes people who are on our list but must not be emailed for a *business* reason (already contacted, customer, opted out, open deal). Session 2 is suppression, not dedup.
- **List building** — Session 1: source accounts + contacts from Blitz into Supabase. Skill: the list-build skill.
- **Email enrichment** — Session 3: find an email for each contact via Icypeas and store it on the contact's `email_*` columns.
- **Async submit→poll** — Icypeas's two-step pattern: the search POST returns a job `_id` (not the email); you poll `/bulk-single-searchs/read` until the job leaves the in-flight set. Every Icypeas script is built this way.
- **Credits** — the metered unit each paid API charges per record. Blitz trial = 1,000 credits (~1/record). We sample first and watch the balance so a run never silently drains the trial.
