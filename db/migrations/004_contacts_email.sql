-- 004: work email per contact. Found by email enrichment (Icypeas today);
-- checked later by a separate validation tool. Design: docs/schema-contacts.md (signed off 2026-10-23).

alter table gtm.contacts
    add column email                extensions.citext,     -- null = none found (or not searched)
    add column email_mx_provider    text,                  -- google, microsoft...
    add column email_enriched_at    timestamptz,           -- when we searched; null = never searched
    add column email_validation     text,                  -- validation tool result (later)
    add column email_validation_at  timestamptz,           -- when validated (later)
    add column email_search_id      text,                  -- Icypeas search id
    -- filled by the database from the two columns above; can never disagree with them
    add column email_status         text generated always as (
        case when email_enriched_at is null then null
             when email is null           then 'not_found'
             else 'found' end) stored;

-- an email can only exist if we searched for it
alter table gtm.contacts add constraint contacts_email_enriched_check
    check (email is null or email_enriched_at is not null);

-- a validation result and its time always come together
alter table gtm.contacts add constraint contacts_email_validation_check
    check ((email_validation is null) = (email_validation_at is null));

create unique index contacts_email_key on gtm.contacts (email) where email is not null;
