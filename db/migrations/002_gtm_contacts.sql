-- 002: contacts (people), linked to companies by domain. No surrogate key.
-- Design: docs/schema-contacts.md (signed off 2026-10-19).

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

-- the primary key doesn't cover lookups by company, so index the FK
create index contacts_company_domain_idx on gtm.contacts (company_domain);

create trigger contacts_updated_at before update on gtm.contacts
for each row execute function gtm.set_updated_at();

alter table gtm.contacts enable row level security;
