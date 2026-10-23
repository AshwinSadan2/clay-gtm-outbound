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
| **No email columns yet** | Superseded 2026-10-23: see §4 (migration 004). |

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

---

## 4. Email columns (migration 004, signed off 2026-10-23)

**Status:** ✅ Signed off 2026-10-23 · `db/migrations/004_contacts_email.sql` · not yet applied.
**Source data:** `data/processed/contacts_email_enriched_2026-10-23.csv` (Icypeas, appended per run).

| Column | Type | Filled by | Meaning |
|---|---|---|---|
| `email` | `citext` | loader | Best email found; null = none found or never searched |
| `email_status` | `text`, **generated** | database | null = never searched · `found` · `not_found` |
| `email_mx_provider` | `text` | loader | google, microsoft, mimecast… |
| `email_enriched_at` | `timestamptz` | loader | When the search finished (Icypeas `system.modifiedAt`); set for found **and** not-found |
| `email_validation` | `text` | later | Separate validation tool's result; allowed values set when the tool is chosen |
| `email_validation_at` | `timestamptz` | later | When validated |
| `email_search_id` | `text` | loader | Icypeas search id: the only link back to the original result |

**Rules enforced by the database**
- `email_status` is computed from `email_enriched_at` + `email`, so it can't be set by hand or disagree.
- An email can't exist without `email_enriched_at`.
- `email_validation` and `email_validation_at` are both set or both empty.
- `email` is unique where present.

**Decisions**
| Decision | Why |
|---|---|
| `email_status` = found / not_found only, ours, not Icypeas's | Icypeas's DEBITED / DEBITED_NOT_FOUND are billing states, not outcomes |
| Never-searched contacts (e.g. the 17 at suppressed companies) have **no** status | Saying `not_found` would claim a search that never happened |
| No `email_certainty` | The provider's own confidence isn't trusted; a separate validation tool fills `email_validation` |
| No `email_source` | One provider today; add when a second arrives |
| No `email_raw` | The user's call: the columns hold everything of value. Full responses stay on disk in `data/raw/emails_icypeas_<date>.jsonl` (exception to the "keep raw" rule) |
