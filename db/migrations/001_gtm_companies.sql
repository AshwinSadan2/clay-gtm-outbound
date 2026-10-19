-- 001: gtm schema + companies. Design: docs/schema-companies.md (signed off 2026-10-19).

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

-- keep updated_at honest on every upsert
create or replace function gtm.set_updated_at() returns trigger as $$
begin new.updated_at = now(); return new; end $$ language plpgsql;

create trigger companies_updated_at before update on gtm.companies
for each row execute function gtm.set_updated_at();

alter table gtm.companies enable row level security;
