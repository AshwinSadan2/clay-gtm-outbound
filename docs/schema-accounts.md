# Schema Design — `accounts` (companies)

**Status:** ✅ Signed off 2026-10-19 (user's revised column list). Not yet pushed to Supabase.
**Source data:** `data/processed/companies_blitz_2026-10-19.csv` (300 rows).

---

## 1. Final table

```sql
create schema if not exists gtm;

create table gtm.accounts (
    domain                 text        primary key,          -- natural key + FK target for contacts
    name                   text        not null,
    website                text,
    linkedin_url           text        unique,
    industry               text,
    employees_on_linkedin  integer,
    hq_country_code        text,
    about                  text,
    raw                    jsonb       not null,             -- full unfiltered API record (escape valve)
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now()
);

-- keep updated_at honest on every upsert
create or replace function gtm.set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

create trigger accounts_updated_at before update on gtm.accounts
for each row execute function gtm.set_updated_at();

alter table gtm.accounts enable row level security;
```

Columns are exactly the signed-off list. Around them:

| Addition | Why |
|---|---|
| **`gtm` schema** | Supabase's `public` schema already holds an unrelated movies project; `gtm` keeps campaign data apart and off Supabase's web API. |
| **`updated_at` trigger** | Without it, `updated_at` stays at insert time forever; loads are upserts on `domain`. |
| **Row-level security on, no policies** | Nothing is readable through the web API by default. Our scripts connect as the database owner and aren't affected. |

`primary key` already means unique + not null, so `domain` needs nothing else.

## 2. Profile of the source data (300 rows)

| Column | Filled | Notes |
|---|---|---|
| `domain` | 300 | All lowercase, no `www.`, no paths, unique |
| `name` | 300 | 3–44 chars; 9 carry suffixes (*"Recko \| A Stripe company"*) |
| `website` | 300 | Usually the homepage; a few include paths (*testrigor.com/request-trial*, *tractian.com/en*). Stored as returned |
| `linkedin_url` | 300 | All `https://www.linkedin.com/company/<slug>`, unique |
| `industry` | 300 | Always "Software Development" (our filter) |
| `employees_on_linkedin` | 300 | 6 – 3,934, median 129 |
| `hq_country_code` | 300 | Always "US" (our filter) |
| `about` | 300 | 34–1,985 chars |
| `raw` | 300 | Full Blitz company record, 14 keys |

Everything else Blitz returned (type, founded year, specialties, followers, full HQ, LinkedIn ID, size band) stays queryable in `raw`, e.g. `raw->>'founded_year'`.

## 3. Notes

- **No exclusion flag on accounts.** The 8 companies with no contact found (mostly acquired: Recko→Stripe, Borneo→Atlassian, Spot→Flexera…) can be identified as accounts with no row in `contacts`.
- **Housekeeping when we push:** the early SQLite placeholder `db/migrations/001_initial_schema.sql` is replaced by Postgres migrations (`001_gtm_accounts.sql`, then `002_gtm_contacts.sql`), and `scripts/data.py` moves to Supabase.
