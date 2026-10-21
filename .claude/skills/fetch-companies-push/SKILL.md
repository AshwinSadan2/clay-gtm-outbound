---
name: fetch-companies-push
description: Pull target companies from Blitz using filters taken from a campaign brief or asked of the user (industry, keywords, employee range, country), run dry-run, then sample, then scale, and push them to Supabase gtm.companies. Use when the user wants to build or refresh a company/account list. Ends by offering the fetch-contacts-push skill.
---

# Fetch companies → push to Supabase

Builds a target company list from Blitz and loads it into `gtm.companies`. The scripts hold no campaign
values: every filter is a flag. **Never edit the scripts for a campaign.** If a brief needs a filter
the flags don't cover, tell the user.

Everything runs from the project folder: outputs go to its `data/` and `logs/`, which are created if missing,
and secrets come from its `.env`. If the `.env` lives elsewhere, add `--env PATH` to every command.
Shorthand used below:
```bash
S=.claude/skills/fetch-companies-push/scripts
PY=.venv/bin/python
```

The user is not a developer. Explain each step in plain English, show results as short tables, and
make the technical calls yourself. Only filter choices, spend and pushes are theirs to decide.

## Step 0: Preflight (free)

1. `bash $S/probe_connections.sh` must show Blitz, Supabase, DIRECT and POOLER all `OK`. Note
   `records_remaining`: it caps everything below. On a FAIL, stop and explain. Never print `.env` values.
2. `$PY $S/data.py stats` shows what's already in the database.

## Step 1: Get the filters

Ask: **"Do you have a new brief for this campaign?"**

- **Yes**: read it (a path, a pasted brief, or an updated `docs/BRIEF.md`). Pull industry, keywords,
  company size, HQ country, exclusions and target count. In the standard brief these are §2b
  (see `assets/filter-intake.md`). Ask only about what the brief leaves open.
- **No**: ask the intake questions in `assets/filter-intake.md` (industry, keywords, employee range,
  country, how many companies). Accept plain-English answers.
- **Unsure / "help me figure it out"**: do an exploratory run. Propose 2–4 candidate filter sets and
  `--probe` each (1 record each, saves nothing). Show total matching + an example company per set and
  decide together. State the record cost before probing.

Convert the answers to flags using `references/company-filters.md` and `references/blitz-industries.md`.
Industry strings must match the list exactly. Countries are ISO 2-letter codes.

## Step 2: Dry run and sign-off (free)

```bash
python3 $S/blitz_company_search.py <filter flags> --limit <target> --dry-run
```
Show the user:
- a table of each brief/answer line → flag → value
- the printed request body
- the budget: target companies = target records, against `records_remaining` (leave room for
  contacts, about 1 record per company)

**Wait for an explicit yes before any paid call.** Save the approved request as
`docs/company-search-request-<date>.md`, following `docs/company-search-request.md`.

## Step 3: Sample (10 records)

```bash
python3 $S/blitz_company_search.py <filter flags> --limit 10 --page-size 10
```
Profile `data/processed/companies_blitz_<date>.csv` and show:
- the 10 names, domains, industries, `employees_on_linkedin`, `hq_country_code`, and the first line of `about`
- **leakage**: anything that isn't the client's buyer (media, agencies, consultancies, non-profits, wrong country)
- **gaps**: rows with no `domain` (domain is the database key, so those rows can't load) or no `linkedin_url`
  (contacts need it)

Ask: proceed, or adjust filters? If adjusting, go back to Step 2 and use a new `--date`
(e.g. `2026-10-21b`). Once the filters change, `--resume` refuses to continue the old set.

## Step 4: Scale

```bash
python3 $S/blitz_company_search.py <same filter flags> --limit <target − 10> --resume
```
`--limit` counts companies pulled **this run**, so subtract the sample. It streams to disk, so if it
stops (error, credit cap) re-run the same command with `--resume`. Report new companies, total
matching, records remaining, and errors (`logs/blitz_company_search_errors.log`).

Profile the full file: row count, duplicate domains, missing domains/LinkedIn URLs, the spread of
industries and sizes, and any leakage spotted.

## Step 5: Push to Supabase (ask first)

Read `references/supabase-push.md`. Show the profile and ask: **"Push these N companies to Supabase?"**
On yes:
```bash
$PY $S/data.py load-companies data/processed/companies_blitz_<date>.csv --limit 5   # sample push
$PY $S/data.py load-companies data/processed/companies_blitz_<date>.csv             # full push
$PY $S/data.py stats
```
Report inserted / updated / unchanged / skipped / errors and the before → after counts. Explain that
contacts can only be loaded for companies now in the table (companies first, then contacts).

## Step 6: Hand-off

Ask: **"Do you want to run the contact search for these companies?"**
On yes, invoke the **fetch-contacts-push** skill. It reads the companies straight from Supabase.
On no, summarise what was pulled, pushed and spent, and stop.

## Guardrails

- No paid call without sign-off on the exact request. Always run sample before scale.
- Keep the `--limit` total within `records_remaining`. Say the cost before every paid step.
- Never edit files in `data/raw/`. Never touch the `public` schema.
- Nothing goes to a CRM or sending tool from this skill.
- Worked example of a full run: `assets/example-clay-2026-10-19.md`.
