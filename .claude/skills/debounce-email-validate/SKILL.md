---
name: debounce-email-validate
description: Validate found emails with Debounce (one synchronous call per email, up to 5 at once) and load the verdict into Supabase gtm.contacts.email_validation. Takes an email-enrichment CSV or a CSV the user gives, checks key and credits, then gates 5 → 100 → rest, and pushes only after sign-off. Use when the user wants emails verified, validated or checked for deliverability.
---

# Debounce email validation (emails → verdict → gtm.contacts)

Checks whether each email can receive mail and writes Debounce's `result` (`Safe to Send` · `Risky` · `Invalid` ·
`Unknown`) to `gtm.contacts.email_validation`. Debounce answers each call directly: no polling.
Every value comes from the user or the list. **Never edit the scripts for a run.**

Everything runs from the project folder. Outputs go to its `data/` and `logs/`, which are created if missing.
Keys come from its `.env` (see `.env.template` in this skill). If the `.env` lives elsewhere, add `--env PATH`.
```bash
S=.claude/skills/debounce-email-validate/scripts
PY=.venv/bin/python
```
The shell is zsh: pass flags as a bash array (`bash -c '... "${F[@]}"'`), never as one `$FLAGS` string.

The user is not a developer. Explain in plain English, show results as short tables, and make the technical
calls yourself. The input list, column mapping, gate sign-offs and the push are theirs.

**References:** `references/run-and-load.md` (flags, files, gates, checks, database mapping) ·
`references/debounce-api-reference.md` (API: endpoints, limits, result codes, errors).

## Step 0: Preflight (free)

1. Check `.env` masked first, **as its own command**, and read it before anything else:
   `sed -E 's/[A-Za-z0-9]/x/g' .env`. Every line must be `KEY=value`. If one isn't, stop: fix it with a script
   that prints nothing, or ask the user. Then confirm `DEBOUNCE_API_KEY` is filled in (name and length only).
2. If Supabase is involved (load): `bash $S/probe_connections.sh` must show **POOLER OK**.

## Step 1: Ask for the input

Ask: **"Which emails should I validate: the latest email-enrichment results, or a CSV you have?"**

- **Enrichment results:** the newest `data/processed/contacts_email_enriched_*.csv`
  (`--email-column email --id-column person_linkedin_url`). Rows with no email are skipped automatically.
- **A CSV:** get the path, read only its header and row count, propose the email and id columns, confirm.
  The id column must be unique per person (the LinkedIn URL if results go to Supabase).

Output: `--output data/processed/contacts_email_validated_<today>.csv`. To continue an earlier run, reuse its
`--output` and add `--resume`. Below, `F` = `--input IN --output OUT --email-column COL --id-column COL`.

## Step 2: Probe (free)

`$PY $S/debounce_email_validate.py --probe` must show **Debounce key: PASS** and the credits.
Compare credits with the emails to check (1 credit each). If short, say how many they cover and ask: check that
many now, or top up first. The script never starts more checks than the balance covers.

## Step 3: Dry run → sample of 5

1. `... "${F[@]}" --limit 5 --dry-run`: show the 5 emails. Ask: **"Check these 5? It costs 5 credits."**
2. `... "${F[@]}" --limit 5`, then show a table: name, company, email, result, reason.
   Ask: **"Look right? Next is up to 100."**

## Step 4: Gate of 100

`... "${F[@]}" --resume --limit 95` (100 in total with the sample). Profile the file
(`references/run-and-load.md` §5): results × reasons, Invalid/Unknown emails listed, per tier if the list has it.
Ask: **"Check the rest (N emails, N credits)?"** Never go from the sample straight to the full list.

## Step 5: Scale

`... "${F[@]}" --resume`. For very large lists, batches of `--limit 50000` with a summary and "continue?" between.
If the run stops on "credits ran out", tell the user; after a top-up, `--resume` carries on.

Final summary: emails done / total, results breakdown, credits left, errors, the output file.

## Step 6: Push to Supabase (after sign-off)

Ask: **"Load these results into the database?"**
1. `$PY $S/data.py load-validation OUT --id-column person_linkedin_url --limit 10`, then ask the user to look in
   Supabase (`gtm.contacts`, filter `email_validation` is not null).
2. On their OK: `$PY $S/data.py load-validation OUT --id-column person_linkedin_url`
3. `$PY $S/data.py stats`: show `emails by email_validation`.

Only `email_validation` and `email_validation_at` are loaded; a row lands only if the contact's stored email
is the one validated (otherwise "email differs", skipped). Reason, code and flags stay in the CSV.

## Rules

- Gate order: probe → dry run → 5 → 100 → scale → push, with a sign-off at each arrow.
- Never pass `append` or `photo` (extra credits). Never use bulk upload: it needs the list on a public URL.
- Never auto-correct emails with `did_you_mean`: for company domains it is mostly wrong (`.ai` → `.ca`).
- One `--output` per list, appended every run. Never edit the input CSV or anything in `data/raw/`.
- Never print `.env` values. The key travels in the URL, so never log or show request URLs.
- `data.py` and `probe_connections.sh` are identical copies across the skills. Change one, change all.
