---
name: fetch-contacts-push
description: Find one contact per company already in Supabase gtm.companies via Blitz, using a title cascade (Waterfall ICP) or a single designation (People Search) taken from a brief or asked of the user. Runs dry-run, then sample, then scale, and pushes contacts to gtm.contacts. Use when the user wants people/decision-makers for loaded companies, or after fetch-companies-push.
---

# Fetch contacts → push to Supabase

Finds the best-matching person at each company in `gtm.companies` and loads them into `gtm.contacts`.
Titles, excludes and location are all flags. **Never edit the scripts for a campaign.**

Everything runs from the project folder. Shorthand used below:
```bash
S=.claude/skills/fetch-contacts-push/scripts
PY=.venv/bin/python
```

The user is not a developer. Explain each step in plain English, show results as short tables, and
make the technical calls yourself. Only persona choices, spend and pushes are theirs to decide.

## Step 0: Preflight (free)

1. `bash $S/probe_connections.sh` must show all `OK`. Note `records_remaining`. Never print `.env` values.
2. `$PY $S/data.py stats` shows companies, contacts, and **companies without a contact**.
   If `gtm.companies` is empty, stop: companies must be loaded first. Offer the **fetch-companies-push** skill.

## Step 1: Which companies

Contacts can only be pushed for companies already in `gtm.companies` (foreign key), so the input
always comes from Supabase:
```bash
$PY $S/data.py export-companies          # companies with no contact yet (default)
$PY $S/data.py export-companies --all    # every company, e.g. to add a second persona
```
This writes `data/processed/companies_supabase_<today>.csv`. Tell the user how many companies it holds.
That is the maximum spend (1 record per person found).

## Step 2: Get the persona

If you arrived from fetch-companies-push with a brief already in hand, use its persona section.
Otherwise ask: **"Do you have a brief with the target persona?"**

- **Yes**: read the persona (§2c in the standard brief, see `assets/persona-intake.md`): titles,
  tiers, people-level exclusions and location.
- **No**: ask the questions in `assets/persona-intake.md`. Who to reach, who's next best,
  titles to avoid, location.

Then **choose the mode** (details in `references/contact-modes.md`):
- The user gives a fallback order → **cascade**: one `--tier` per level, highest priority first (1–10).
- One designation, no order → **single title**: `--title`. Don't invent a cascade.

Write out every title variant (`VP` ≠ `Vice President`, `Demand Gen` ≠ `Demand Generation`), using the
matching rules in `references/contact-modes.md`. Default `--location WORLD`.

## Step 3: Dry run and sign-off (free)

```bash
python3 $S/blitz_contact_search.py --companies <export csv> <mode + title flags> --location WORLD --dry-run
```
Show the user:
- the tiers (or the single list) as a table, plus the excludes
- the endpoint the script chose and the printed request
- the budget: up to N records for N companies, against `records_remaining`

**Wait for an explicit yes before any paid call.** Save the approved request as
`docs/contact-search-request-<date>.md`, following `docs/contact-search-request.md`.

## Step 4: Sample (first 10 companies)

```bash
python3 $S/blitz_contact_search.py --companies <export csv> <flags> --limit 10
```
Profile `data/raw/contacts_blitz_<date>.csv` (every company, `status` found / no_match) and show:
- per company: name, `job_title`, `icp_tier`, `location_country_code`
- found vs no-match, and the tier spread
- **false hits**: titles that matched but aren't the persona (e.g. *Growth Engineer*, *Product Owner*)
- people with no `first_name` (they'll be skipped at push)

Ask: proceed, or adjust titles? If adjusting, return to Step 3 with a new `--date`
(e.g. `2026-10-21b`), so the new results don't mix with the old ones.

## Step 5: Scale

Re-run the **same command without `--limit`**, and with the sample's `--date` if the day has changed.
Companies already done are skipped, and failed ones are retried on re-run. Report found / no-match /
errors, the tier spread, and records remaining. Errors are in `logs/blitz_contact_search_errors.log`.

## Step 6: Push to Supabase (ask first)

Read `references/supabase-push.md`. Remind the user that each contact is stored against its company,
and the companies are already in the table because the list came from Supabase. Ask:
**"Push these N contacts to Supabase?"** On yes:
```bash
$PY $S/data.py load-contacts data/processed/contacts_blitz_<date>.csv --limit 5   # sample push
$PY $S/data.py load-contacts data/processed/contacts_blitz_<date>.csv             # full push
$PY $S/data.py stats
```
Report inserted / updated / unchanged / skipped (no first name, company not loaded) / errors, and the
before → after counts. If the loader warns that some companies aren't loaded, load those companies
first, then re-run the contacts push.

## Step 7: Wrap-up

Summarise: companies searched, contacts found and pushed, tier spread, no-match companies, and records
spent / remaining. Nothing goes to a CRM or sending tool from this skill.

## Guardrails

- No paid call without sign-off on the exact request. Always run sample before scale.
- One person per company. If the user wants more, say it needs a script change. Don't edit silently.
- Never edit files in `data/raw/`. Never touch the `public` schema.
- Worked examples (cascade and single title): `assets/example-clay-2026-10-19.md`.
