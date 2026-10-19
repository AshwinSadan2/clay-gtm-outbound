# Schema Design — `contacts` (people)

**Status:** ✅ Signed off and applied 2026-10-19 (`db/migrations/002_gtm_contacts.sql`). Loaded: 287 contacts.
**Source data:** `data/processed/contacts_blitz_2026-10-19.csv` (292 matched contacts).
**Depends on:** `gtm.companies` (`docs/schema-companies.md`).

---

## 1. Final table

```sql
create table gtm.contacts (
    person_linkedin_url    text        primary key,                 -- natural person key (unique in our data)
    company_domain         extensions.citext not null references gtm.companies(domain),  -- FK link to companies
    icp_tier               smallint    not null check (icp_tier between 1 and 6),
    first_name             text,
    last_name              text,
    job_title              text,
    headline               text,
    location_country_code  text,
    about_me               text,
    raw                    jsonb       not null,       -- full unfiltered record (person + match meta + link)
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now()
);

create index contacts_company_domain_idx on gtm.contacts (company_domain);
-- + updated_at trigger, row-level security on (see migration file)
```

## 2. Decisions (2026-10-19)

| Decision | Detail |
|---|---|
| **PK `person_linkedin_url`** | Natural key, no surrogate ID. All matched contacts have a unique one. Upsert key for re-runs. |
| **FK `company_domain` → `companies.domain`** | `citext`, like the parent. The database rejects a contact whose company isn't loaded. Indexed for joins and "contacts at company X". |
| **Load the 292 matched only** | The 8 no-match companies have no contact row. |
| **Drop the 5 nameless contacts** | Tyfone, Merge, HR Acuity, Nightfall AI, HiredScore. Skipped by the loader (`first_name` blank). |
| **Dropped columns** | `full_name`, `location_city`, `location_state_code`, `job_start_date`. |
| **`ranking`, `connections_count`** | Left in `raw`. |
| **No `first_name_clean` yet** | Added at the copy stage. |
| **One contact per company not enforced** | Adding a second contact later needs no schema change. |
| **No email columns yet** | The Icypeas session adds `email_*` columns as its own migration. |

## 3. Loaded state (2026-10-19)

| Check | Result |
|---|---|
| Companies | 300 |
| Contacts | 287 (292 matched − 5 nameless) |
| Companies with a contact | 287 |
| Companies without a contact | 13 (8 no-match + 5 nameless) |
| Contacts by `icp_tier` | 1: 117 · 2: 41 · 3: 25 · 4: 14 · 5: 77 · 6: 13 |
| Orphan contacts | 0 |
| Re-run of both loads | 0 inserted, 0 updated: fully idempotent |
