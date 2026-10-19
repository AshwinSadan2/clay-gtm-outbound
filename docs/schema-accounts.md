# Schema Design — `accounts` (companies)

**Status:** ✅ Signed off 2026-10-19 (exclusion flag kept; no promoted columns, no `name_clean`, name `gtm.accounts`). Not yet pushed to Supabase.
**Source data:** `data/processed/companies_blitz_2026-10-19.csv` (300 rows, 7 agreed columns incl. `raw`).

---

## 1. Profile of the CSV

| Column | Filled | Distinct | Length / range | Notes |
|---|---|---|---|---|
| `name` | 300/300 | 300 | 3–44 chars | 9 names carry suffixes: *"Recko \| A Stripe company"*, *"Borneo (Acquired by Atlassian)"*, *"Greenly \| Certified B Corp"* |
| `domain` | 300/300 | 300 | 6–22 chars | All lowercase, no `www.`, no paths, no duplicates → **safe primary key** |
| `linkedin_url` | 300/300 | 300 | 37–59 chars | All `https://www.linkedin.com/company/<slug>`, no trailing `/` → unique |
| `industry` | 300/300 | 1 | — | Always "Software Development" (our filter) |
| `employees_on_linkedin` | 300/300 | 186 | 6 – 3,934 (median 129) | Whole numbers |
| `about` | 300/300 | 300 | 34–1,985 chars | Free text, line breaks already collapsed |
| `raw` | 300/300 | 300 | 0.6–4.9 KB | Valid JSON, 14 keys, identical to the Blitz response |

**What sits in `raw` only** (not columns, but queryable later): `type` (290 private, 7 public, 3 other), `founded_year` (1993–2023, 26 blank), `specialties` (33 blank), `followers`, `website`, `linkedin_id`, `size`, `hq` (city, state, country; all US; 16 blank states).

**Supabase today:** the `public` schema already holds an unrelated movies project (`movies`, `genres`, `movie_genres`, `movies_with_genres`). Extensions `pgcrypto` and `uuid-ossp` are installed.

---

## 2. Proposed table

```sql
create schema if not exists gtm;

create table gtm.accounts (
    domain                text primary key
                          check (domain = lower(domain) and domain !~ '^www\.|/'),
    name                  text not null,
    linkedin_url          text not null unique,
    industry              text,
    employees_on_linkedin integer check (employees_on_linkedin >= 0),
    about                 text,
    raw                   jsonb not null,

    is_excluded           boolean not null default false,
    exclusion_reason      text,

    source                text not null default 'blitz_company_search',
    pulled_at             timestamptz not null,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

-- keep updated_at honest on every upsert
create or replace function gtm.set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

create trigger accounts_updated_at before update on gtm.accounts
for each row execute function gtm.set_updated_at();

alter table gtm.accounts enable row level security;
```

---

## 3. Design decisions

| Decision | Why |
|---|---|
| **Own schema `gtm`**, not `public` | Keeps campaign data apart from the movies project. Also, Supabase only exposes `public` through its web API, so prospect data stays reachable only through our direct database connection. |
| **Table name `accounts`** | Matches `CONTEXT.md` ("Account = a company… stored in the `accounts` table") and the planned link `contacts.account_domain → accounts.domain`. |
| **`domain` as primary key** | It's the key contacts link to, and it's what CRMs, Icypeas and email tools match on. Profiling shows it's clean and unique. The `check` stops `WWW.Foo.com` or `foo.com/` from creating a second copy of the same company. |
| **`linkedin_url` unique** | It's the input to Waterfall ICP, so contact rows get matched back to their account through it. Unique stops one LinkedIn page from appearing under two domains. |
| **`raw jsonb not null`** | Every field Blitz returned, unfiltered (as agreed). `jsonb` lets us query inside it later, e.g. `raw->'hq'->>'state'` or `raw->>'founded_year'`, without new columns. |
| **`is_excluded` + `exclusion_reason`** | We already know 8 accounts had no contact, mostly because they were acquired (Recko→Stripe, Borneo→Atlassian, Spot→Flexera…). This flags them rather than deleting them, so they never get emailed and we keep a record of why. The suppression step can reuse the same flag. |
| **`source` + `pulled_at`** | Says where and when each row came from, so if we add a second source or re-pull later, we can tell the batches apart. |
| **`created_at` / `updated_at` + trigger** | Loads are upserts (`on conflict (domain) do update`), so re-running is safe. `updated_at` shows what changed and when. |
| **`industry` nullable** | Constant today, but a future pull from a different source may not have it. |
| **Row-level security on, no policies** | Belt and braces: even if `gtm` is exposed to the web API later, nothing is readable without an explicit rule. Our scripts connect as the database owner, so this doesn't affect us. |

## 4. Housekeeping when we push

- `db/migrations/001_initial_schema.sql` was the early SQLite placeholder and was never used for real data. It gets replaced by Postgres migrations: `001_gtm_accounts.sql` now, `002_gtm_contacts.sql` after the contacts sign-off.
- `scripts/data.py` moves from SQLite to Supabase (pooler connection) with upserts on `domain`.

## 5. Decisions (2026-10-19)

1. **Exclusion flag:** ✅ keep `is_excluded` / `exclusion_reason`.
2. **Promoted `raw` fields:** none for now; query them inside `raw`.
3. **`name_clean`:** not added; revisit if copy uses the company name.
4. **Naming:** `gtm.accounts`.
