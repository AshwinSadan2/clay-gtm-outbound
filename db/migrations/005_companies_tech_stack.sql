-- 005: tech-stack enrichment on gtm.companies (DetectZeStack via RapidAPI). Design: docs/schema-companies.md §4.
-- tech_stack holds the provider's category map: {"CRM": ["HubSpot"], "Analytics": ["Google Analytics"], ...}.
-- The raw response and campaign-specific signals (distilled tool/type) stay in the CSVs, never here.

alter table gtm.companies
    add column tech_stack       jsonb,
    add column tech_enriched_at timestamptz;

-- tech_enriched_at = when we ran DetectZeStack, set for every attempted company (a failed scan leaves tech_stack
-- null). A stack never exists without that date, and is always a {type: [tools]} object ({} = nothing detected).
alter table gtm.companies add constraint companies_tech_stack_check
    check (tech_stack is null or (tech_enriched_at is not null and jsonb_typeof(tech_stack) = 'object'));

-- Containment lookups, e.g. tech_stack @> '{"CRM": ["HubSpot"]}'.
create index companies_tech_stack_idx on gtm.companies using gin (tech_stack jsonb_path_ops);
