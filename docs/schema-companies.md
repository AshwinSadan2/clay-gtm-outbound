# Schema Design — `companies`

**Status:** ✅ Signed off and applied 2026-10-19 (`db/migrations/001_gtm_companies.sql`). Loaded: 300 companies.
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

## 4. Tech-stack columns (migration 005, 2026-10-27)

Source: DetectZeStack `/analyze` via RapidAPI (`docs/detectzestack-api-reference.md`), loaded by
`data.py load-tech FILE --id-column domain` (update only, matched on `domain`).

| Column | Type | Filled by | Meaning |
|---|---|---|---|
| `tech_stack` | `jsonb` | loader (CSV `tech_stack`) | Type → tools map: `{"CRM": ["HubSpot"], "Analytics": ["Google Analytics"], ...}`. `{}` = scanned, nothing detected |
| `tech_enriched_at` | `timestamptz` | loader | When we ran DetectZeStack (UTC), set for every attempted company, failures included |

Rules:
- States: both null = never tried · date only = tried, scan failed · `{}` + date = nothing detected · map + date = scanned.
- A stack never exists without the date, and is always a JSON object.
- GIN index (`jsonb_path_ops`): `tech_stack @> '{"CRM": ["HubSpot"]}'` is fast. Any-type search:
  `jsonb_path_exists(tech_stack, '$.*[*] ? (@ == "HubSpot")')`.

Decisions:
| Decision | Why |
|---|---|
| One map column instead of separate technology and category lists | It holds every tool and its type (all 1,072 detections checked); a tool can sit under two types |
| No raw response | Stays in `data/processed/tech_stack_companies_<date>.csv` (`tech_raw`) and `data/raw/*.jsonl` |
| No distilled campaign signal (`tech_tool` / `tech_type`) | Campaign-specific and transient: lives in `distilled_tech_stack_companies_<date>.csv`, re-derived per client |
| No count, scan depth, status code, cache flag | Derivable or troubleshooting-only; kept in the CSV |
