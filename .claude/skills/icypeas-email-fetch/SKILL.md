---
name: icypeas-email-fetch
description: Find work emails for a contact list with Icypeas (submit, then poll) and load them into Supabase gtm.contacts. Takes a CSV from the user or exports never-searched contacts from Supabase (minus suppressed companies), probes key and credits, then gates 5 → 100 → full run (batches of 50,000 when large), and pushes only after sign-off. Use when the user wants emails found, enriched or fetched for contacts.
---

# Icypeas email fetch (contacts → emails → gtm.contacts)

Finds a work email for each person on a list, then writes the results to `gtm.contacts`. Icypeas is
**asynchronous**: the script submits searches, saves each search id, and **polls** until every search is final.
Every value comes from the user or the list. **Never edit the scripts for a run.**

Everything runs from the project folder. Outputs go to its `data/` and `logs/`, which are created if missing.
Keys come from its `.env` (see `.env.template` in this skill). If the `.env` lives elsewhere, add `--env PATH`.
```bash
S=.claude/skills/icypeas-email-fetch/scripts
PY=.venv/bin/python
```

The user is not a developer. Explain in plain English, show results as short tables, and make the technical
calls yourself. The input list, column mapping, gate sign-offs and the push are theirs.

**References:** `references/run-and-load.md` (flags, files, gates, checks, database mapping) ·
`references/icypeas-api-reference.md` (API: endpoints, limits, statuses, errors).

## Step 0: Preflight (free)

1. Check `.env` masked first, **as its own command**, and read it before anything else:
   `sed -E 's/[A-Za-z0-9]/x/g' .env`. Every line must be `KEY=value`. If one isn't (e.g. `Label - value`),
   stop: don't run any other `.env` check, and fix the line with a script that prints nothing, or ask the user.
   Then confirm the keys in this skill's `.env.template` are filled in (names and lengths only, never values).
2. If Supabase is involved (export or load): `bash $S/probe_connections.sh` must show **POOLER OK**.

## Step 1: Ask for the input

Ask: **"Which list should I find emails for: a CSV you have, or contacts from our Supabase database?"**

- **A CSV:** get the path. Read only its header and row count. Propose the mapping and confirm it:
  first name → `--first-name-column`, last name → `--last-name-column`, company domain → `--domain-column`,
  a column unique per person → `--id-column` (the LinkedIn URL if the results will go to Supabase).
  If any is missing, or the id column has repeats, say so and stop.
- **Supabase:** offer the newest `data/processed/suppression_*.csv` to leave out suppressed companies.
  If none exists, offer `/suppression-gate` first. Then run:
  `$PY $S/data.py export-contacts --exclude-domains FILE --exclude-column domain`
  This gives contacts never email-searched. `--all` also includes searched ones, and re-searching costs credits again.
  Columns: `first_name`, `last_name`, `company_domain`, `person_linkedin_url`.

Pick the output: `--output data/processed/contacts_email_enriched_<today>.csv`. If that file already belongs
to another list, add the list's name. To continue an earlier run, reuse its `--output` and add `--resume`.

Below, `FLAGS` = `--contacts IN --output OUT` plus the four column flags.

## Step 2: Probe (free)

Ask once for the Icypeas account's login email (used only to read the credit balance), then:
`$PY $S/icypeas_email_search.py --probe --account-email EMAIL`

Must show **Icypeas key: PASS** and a credits line. On FAIL, stop and explain (`logs/icypeas_email_search_errors.log`).
Compare credits with the number of people: each person can cost 1 credit. If credits are short, say how many
people they cover and ask.

## Step 3: Dry run → sample of 5

1. `$PY $S/icypeas_email_search.py FLAGS --limit 5 --dry-run`: show the 5 requests (name, domain).
   Ask: **"Send these 5? It costs at most 5 credits."**
2. `$PY $S/icypeas_email_search.py FLAGS --limit 5`
3. `$PY $S/review_results.py --results OUT --domain-column COL --last 5 --show 5` and show it as a table:
   name, company, email, found / not found. Ask: **"Look right? Next is 100."**

## Step 4: Gate of 100

`$PY $S/icypeas_email_search.py FLAGS --resume --limit 100`, then
`review_results.py ... --last 100 --show 10` (add `--group-column icp_tier` if the list has it).
Show the found rate, emails off the company domain, multi-email count, mail providers, errors and credits used.
Point out anything odd (`references/run-and-load.md` §5). Ask: **"Run the rest (N people, up to N credits)?"**

**Never go from the sample straight to the full list.** The 100 gate always comes first.

## Step 5: Scale

- **≤ 50,000 left:** `$PY $S/icypeas_email_search.py FLAGS --resume`
- **More than 50,000 left:** batches of `--resume --limit 50000`. After each batch, show the summary
  (`review_results.py --last 50000`) and ask before the next one.
- Long batches: run in the background with `--max-wait 3600`. Sizing notes are in `references/run-and-load.md` §4.
- If the run ends with "searches not finished", re-run with `--resume`. It polls the pending ones and never resubmits.

Final summary: people done / total, found %, credits used, errors, the output file.

## Step 6: Push to Supabase (after sign-off)

Only for people already in `gtm.contacts` (the id column = LinkedIn URL). Load never inserts new people.
Ask: **"Load these emails into the database?"**
1. `$PY $S/data.py load-emails OUT --id-column person_linkedin_url --limit 10`, then ask the user to look in
   Supabase (`gtm.contacts`, filter `email_enriched_at` is not null).
2. On their OK: `$PY $S/data.py load-emails OUT --id-column person_linkedin_url`
3. `$PY $S/data.py stats`: show `contacts by email_status` (found · not_found · not searched).

`email_status` is computed by the database. Never write it. Validation columns stay empty: a separate tool fills them.

## Rules

- Follow the gate order (probe → dry run → 5 → 100 → scale → push), with a sign-off at each arrow.
- One `--output` per list, appended every run. Never write a second results file for the same list.
- Never edit a user's input CSV or anything in `data/raw/`.
- Never print `.env` values or the account email in logs or tables.
- `data.py` and `probe_connections.sh` are identical copies across the skills. Change one, change all.
- Errors: the run carries on and logs them. Report the count from the end of the run.
