-- 002: contacts (people), linked to companies by domain. No surrogate key.
-- Design: docs/schema-contacts.md (awaiting sign-off).
-- NOT YET APPLIED: run only after both schemas are signed off.

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

-- the primary key doesn't cover lookups by company, so index the FK
create index contacts_company_domain_idx on gtm.contacts (company_domain);

create trigger contacts_updated_at before update on gtm.contacts
for each row execute function gtm.set_updated_at();

alter table gtm.contacts enable row level security;
