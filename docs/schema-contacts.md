# Schema Design — `contacts` (people)

**Status:** ⏳ Awaiting sign-off (revised for natural keys). Schema file written: `db/migrations/002_gtm_contacts.sql`. **Not yet applied to Supabase.**
**Source data:** `data/processed/contacts_blitz_2026-10-19.csv` (292 found contacts).
**Depends on:** `gtm.companies` (`docs/schema-companies.md`).

---

## 1. Proposed table

```sql
create table gtm.contacts (
    linkedin_url          text        primary key,           -- natural key + upsert key
    company_domain        extensions.citext not null
                          references gtm.companies(domain) on update cascade on delete restrict,
    first_name            text        not null,
    last_name             text,
    full_name             text,
    job_title             text        not null,
    headline              text,
    icp_tier              smallint    not null check (icp_tier between 1 and 6),
    location_city         text,
    location_state_code   text,
    location_country_code text,
    connections_count     integer,
    about_me              text,
    raw                   jsonb       not null,              -- full unfiltered API response
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index contacts_company_domain_idx on gtm.contacts (company_domain);
-- + updated_at trigger, row-level security on (see migration file)
```

## 2. Decisions

| Decision | Detail |
|---|---|
| **No surrogate `id`** | Removed, per the natural-keys decision. |
| **Primary key = `linkedin_url`, not `domain`** | ⚠️ *Pushback.* If `domain` were the contacts primary key, the database would allow only **one contact per company**, which the earlier decision explicitly left open. `linkedin_url` is a real, natural key: every contact has one, all 292 are unique, and it's the upsert key for re-runs. |
| **`company_domain` → `companies.domain`** | The relationship between the two tables. Same `citext` type as the parent, so `Clay.com` and `clay.com` link to the same company. A contact can't exist without its company; a company with contacts can't be deleted. |
| **Index on `company_domain`** | The primary key doesn't speed up "all contacts at company X" or joins to `companies`; this index does. |
| **5 nameless contacts excluded** | Tyfone, Merge, HR Acuity, Nightfall AI, HiredScore. `first_name not null` enforces it. |
| **No `first_name_clean` yet** | Added at the copy stage. |
| **`job_start_date` dropped** | 79 of 277 are 1 Jan placeholders. Still in `raw`. |
| **One contact per company not enforced** | Adding a second contact later needs no schema change. |
| **No email columns yet** | The Icypeas session adds `email_*` columns as its own migration. |
| **Matches companies** | `raw jsonb`, `gtm` schema, auto `updated_at`, row-level security on. |

## 3. Profile of the source data (292 found contacts)

| Column | Filled | Notes |
|---|---|---|
| `linkedin_url` | 292 | All `https://www.linkedin.com/in/<slug>`, lowercase, unique |
| `company_domain` | 292 | Every one matches a row in `companies` |
| `first_name` / `last_name` / `full_name` | 287 | 5 blank (excluded, above). Some not email-ready: *"C. T."*, *"FADI"*, *"Roberto E."* |
| `job_title` | 292 | Current job at the target company (292/292); 152 distinct |
| `headline` | 292 | 13–79 chars |
| `icp_tier` | 292 | 120 / 41 / 25 / 15 / 78 / 13 |
| `location_city` / `state_code` / `country_code` | 275 / 193 / 276 | US 194 · IN 29 · CA 11 · GB 7 · blank 16 |
| `connections_count` | 279 | 0 – 29,929, median 1,952 |
| `about_me` | 230 | 62 blank (the opener falls back to the company About) |
| `raw` | 292 | Full Blitz response, 1.3–7.4 KB |

**Expected load:** 287 contacts across 287 companies. 13 companies end up with no contact: 8 no-match + 5 nameless.
