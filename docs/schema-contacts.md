# Schema Design — `contacts` (people)

**Status:** ⏳ Awaiting sign-off. Nothing has been created in Supabase yet.
**Source data:** `data/processed/contacts_blitz_2026-10-19.csv` (300 rows: 292 found + 8 no-match).
**Depends on:** `gtm.accounts` (signed off, see `docs/schema-accounts.md`).

---

## 1. Profile of the CSV (292 found contacts)

| Column | Filled | Distinct | Length / range | Notes |
|---|---|---|---|---|
| `company_domain` | 292 | 292 | — | Matches `accounts.domain` for every row → **clean foreign key** |
| `icp_tier` | 292 | 6 | 1–6 | 120 / 41 / 25 / 15 / 78 / 13 |
| `person_linkedin_url` | 292 | 292 | 32–65 chars | All `https://www.linkedin.com/in/<slug>`, lowercase → **unique** |
| `full_name` / `first_name` / `last_name` | **287** | — | first name 2–11 chars | ⚠️ **5 contacts have no name** (hidden by LinkedIn privacy): Tyfone, Merge, HR Acuity, Nightfall AI, HiredScore |
| `job_title` | 292 | 152 | 3–65 chars | Always the **current** job at the target company (checked: 292/292) |
| `headline` | 292 | 292 | 13–79 chars | |
| `location_city` | 275 | 138 | | |
| `location_state_code` | 193 | 49 | 1–3 chars | Blank for most non-US contacts |
| `location_country_code` | 276 | 28 | 2 chars | US 194 · IN 29 · CA 11 · GB 7 · blank 16 |
| `connections_count` | 279 | — | 0 – 29,929 (median 1,952) | 17 under 50 |
| `job_start_date` | 277 | 100 | | ⚠️ 79 fall exactly on 1 Jan (year-only data), so not reliable |
| `about_me` | 230 | 230 | 26–2,591 chars | 62 blank; the opener then falls back to the company About (per brief) |
| `raw` | 292 | 292 | 1.3–7.4 KB | Full Blitz response for that company's call |

**Constant or redundant in this CSV:** `status` (always "found" for real contacts), `ranking` (always 1, as we ask for one per company), `company_name` / `company_linkedin_url` (already on `accounts`).
**Mail-merge note:** some first names aren't email-ready: `"C. T."`, `"FADI"`, `"Roberto E."`, `"Dee Anna"`.

---

## 2. Proposed table

```sql
create table gtm.contacts (
    id                    bigint generated always as identity primary key,
    account_domain        text not null
                          references gtm.accounts(domain) on update cascade on delete restrict,
    linkedin_url          text not null unique
                          check (linkedin_url ~ '^https://www\.linkedin\.com/in/[^/]+$'),

    first_name            text,
    last_name             text,
    full_name             text,
    job_title             text not null,
    headline              text,
    icp_tier              smallint not null check (icp_tier between 1 and 6),

    location_city         text,
    location_state_code   text,
    location_country_code char(2),
    connections_count     integer check (connections_count >= 0),
    about_me              text,
    raw                   jsonb not null,

    is_excluded           boolean not null default false,
    exclusion_reason      text,

    source                text not null default 'blitz_waterfall_icp',
    pulled_at             timestamptz not null,
    created_at            timestamptz not null default now(),
    updated_at            timestamptz not null default now()
);

create index contacts_account_domain_idx on gtm.contacts (account_domain);
create index contacts_icp_tier_idx       on gtm.contacts (icp_tier);

create trigger contacts_updated_at before update on gtm.contacts
for each row execute function gtm.set_updated_at();   -- created with accounts

alter table gtm.contacts enable row level security;
```

---

## 3. Design decisions

| Decision | Why |
|---|---|
| **`account_domain` → `accounts.domain`** | The account–contact link from `CONTEXT.md`. The database refuses a contact whose company isn't in `accounts`, and refuses deleting an account that still has contacts. |
| **`linkedin_url` unique = the upsert key** | Every contact has one, and it's stable. Re-running a load updates the person instead of duplicating them. |
| **`id` number as primary key** | A short, permanent ID for later tables (outreach events, replies) to point at, even if a LinkedIn URL changes. |
| **Names nullable** | 5 real contacts have no name. Making names required would silently drop them. They get flagged instead (see §4). |
| **`icp_tier` 1–6 enforced** | The persona cascade from the brief; tiers 1–3 = senior marketers, for when we want to filter. |
| **`job_title` required** | Every contact has one, and the `{ROLE}` line in Email 1 is chosen from it. |
| **No unique rule on `account_domain`** | It's one contact per company *for now*. Not locking that in means adding a second contact later needs no schema change. |
| **No email columns yet** | Emails come from Icypeas in a later session. That session adds its `email_*` columns as a new migration, so this table only holds data we actually have. |
| **8 no-match companies → not in contacts** | There's no person to store. Instead their `accounts` row gets `is_excluded = true`, `exclusion_reason = 'no contact found'` (plus *acquired by X* where we know it). |
| **Dropped from columns (kept in `raw`)** | `status`, `ranking`, `company_name`, `company_linkedin_url` (redundant), `job_start_date` (unreliable), plus nickname, picture, skills, education and work history. |
| **Same housekeeping as accounts** | `raw jsonb`, `is_excluded` + reason, `source`, `pulled_at`, timestamps with auto `updated_at`, row-level security on. |

## 4. Open questions for you

1. **The 5 nameless contacts:** flag them `is_excluded = true, exclusion_reason = 'no name'` (they can't get `{FIRST_NAME}`), or keep them active and fill names later via Person Enrichment (1 record each)?
2. **`first_name_clean`:** add a column for an email-ready first name (*"C. T."* → blank/fallback, *"FADI"* → *"Fadi"*, *"Dee Anna"* kept)? I'd add it at the copy stage rather than now.
3. **`job_start_date`:** drop it (recommended, since 1 in 4 is a placeholder), or keep it as a column anyway?
4. **One contact per company:** enforce it in the database, or leave it open as proposed?
