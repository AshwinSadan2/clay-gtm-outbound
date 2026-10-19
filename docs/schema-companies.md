# Schema Design — `companies`

**Status:** ✅ Signed off 2026-10-19. Schema file written: `db/migrations/001_gtm_companies.sql`. **Not yet applied to Supabase.**
**Source data:** `data/processed/companies_blitz_2026-10-19.csv` (300 rows).

---

## 1. Final table

```sql
create extension if not exists citext with schema extensions;   -- case-insensitive text
create schema if not exists gtm;

create table gtm.companies (
    domain                 extensions.citext primary key,    -- natural key + FK target for contacts
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
-- + updated_at trigger, row-level security on (see migration file)
```

## 2. Decisions (2026-10-19)

| Decision | Detail |
|---|---|
| **Table name `companies`** | Contacts link back with `company_domain`. |
| **`domain` is the primary key, no surrogate ID** | A natural key: what CRMs, email finders and Icypeas match on. Also the foreign-key target for `contacts.company_domain`. |
| **`domain` is `citext`** | Case-insensitive: `Clay.com` and `clay.com` are the same company, so the key can't split one company into two rows. Requires the `citext` extension, which the migration switches on (it isn't enabled in this Supabase project yet). |
| **`raw jsonb`** | Every field Blitz returned, unfiltered. Type, founded year, specialties, full HQ, followers and LinkedIn ID stay queryable, e.g. `raw->>'founded_year'`. |
| **`gtm` schema** | Supabase's `public` schema holds an unrelated movies project; `gtm` keeps campaign data apart and off Supabase's web API. |
| **Auto `updated_at` + row-level security** | Loads are upserts on `domain`; nothing is readable via the web API by default. |
| **No exclusion flag** | The 8 companies without a contact (mostly acquired) show up as companies with no row in `contacts`. |

## 3. Profile of the source data (300 rows)

| Column | Filled | Notes |
|---|---|---|
| `domain` | 300 | All lowercase, no `www.`, no paths, unique |
| `name` | 300 | 3–44 chars; 9 carry suffixes (*"Recko \| A Stripe company"*) |
| `website` | 300 | Usually the homepage; a few include paths (*testrigor.com/request-trial*). Stored as returned |
| `linkedin_url` | 300 | All `https://www.linkedin.com/company/<slug>`, unique |
| `industry` | 300 | Always "Software Development" (our filter) |
| `employees_on_linkedin` | 300 | 6 – 3,934, median 129 |
| `hq_country_code` | 300 | Always "US" (our filter) |
| `about` | 300 | 34–1,985 chars |
| `raw` | 300 | Full Blitz company record, 14 keys |
