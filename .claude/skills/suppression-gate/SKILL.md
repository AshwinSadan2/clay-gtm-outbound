---
name: suppression-gate
description: Suppress companies or contacts that must not be prospected (customers, competitors, open deals, lost deals, recent or ongoing conversations, opt-outs), using the Attio CRM (read-only), before any enrichment spend. Asks the level (domain or email-matched contact), categories and time window, then runs profile, download, preview and sign-off, and writes suppressed/clean CSVs. Never changes the database. Use when the user wants to suppress, exclude or clean a target list against the CRM.
---

# Suppression gate (Attio → suppressed / clean CSVs)

Removes anyone we must not prospect from a target list, so enrichment money is only spent on companies we'd
actually talk to. Three staged scripts, each a gate the user signs off on. **Output is CSV only: never change
the database, and never write to Attio** (the key is read-only anyway).

Everything runs from the project folder. Outputs go to its `data/` and `logs/`, which are created if missing.
Keys come from its `.env` (see `.env.template` in this skill). If the `.env` lives elsewhere, add `--env PATH`.
```bash
S=.claude/skills/suppression-gate/scripts
PY=.venv/bin/python
```

The user is not a developer. Explain in plain English, show results as short tables, and make the technical
calls yourself. Level, categories, time window, target and sign-offs are theirs.

## Step 0: Preflight (free)

1. Check `.env` masked first: `sed -E 's/[A-Za-z0-9]/x/g' .env`. Then confirm the keys in this skill's
   `.env.template` are filled in, reporting names and lengths only. Never print values.
2. `bash $S/probe_connections.sh` must show **ATTIO OK**, and also **POOLER OK** if the target will be Supabase.
   On a FAIL, stop and explain.

## Step 1: Ask the settings

Use `assets/intake-questions.md`. Ask one group at a time:
1. **Level**: whole companies (`--level domain`, the default) or specific people (`--level contact`).
   For contact level, ask straight away whether the lead list has **emails**. Contact level matches on email
   only (never LinkedIn URL) and won't run without them. If there are no emails, offer domain level or stop.
2. **Categories**: show the plain-English list and let the user pick → `--categories ...` or `all`.
3. **Window**: only if `recently_contacted` or `in_conversation` is chosen. "90 days, 120, a year, or another
   number?" → `--days N` (default 90). Lost deals have no time limit unless asked (`--lost-days N`).

Category meanings, inheritance and edge cases: `references/categories.md`.

## Step 2: Profile the CRM (stage 1, free, writes nothing)

```bash
$PY $S/attio_profile.py --level <level> --categories <...> --days <N>
```
Show inline:
- the CRM size line
- each category with its count. Small categories list their entries (companies by name and domain,
  people by job title and company, never emails). Big ones show counts only. Tune with `--detail-threshold`.
- any note the script prints. For example, `in_conversation` matches nobody until mailboxes are synced
  (see `references/attio-crm.md`).

Ask: **"Attio has N to suppress under these rules. Download this list?"** If the user wants changes, return to Step 1.

## Step 3: Download (stage 2)

```bash
$PY $S/attio_download.py --level <level> --categories <...> --days <N>
```
Use the same flags that were signed off. This writes the raw Attio copy (`data/raw/attio_*_<date>.jsonl`) and
`data/processed/suppression_attio_<level>_<date>.csv`. Confirm the count matches the profile.

## Step 4: What to suppress against

Ask: **"A CSV you have, or our Supabase list?"**
- **CSV**: `--target-csv PATH`. Find the match column: `--domain-column` (domain level) or `--email-column`
  (contact level) if it isn't named `domain` / `email`. Look at the header row yourself first.
- **Supabase**: `--target-supabase`, which reads `gtm.companies` (domain) or `gtm.contacts` (contact).
  It's saved as `data/processed/<companies|contacts>_supabase_<date>.csv`.

## Step 5: Preview (stage 3, writes nothing except a Supabase download)

```bash
$PY $S/attio_suppress.py --level <level> <target flags>
```
Show inline:
- **the target profile**: rows, match column, unique, blank, duplicates. Flag blanks and duplicates.
- **would be suppressed**, by category: details when small, counts when big
- **clean** count, plus **unchecked** (no email, contact level) and **already have a contact** if shown

Ask: **"Of your T rows, S would be suppressed and C stay clean. Write the files?"**

## Step 6: Apply (after an explicit yes)

```bash
$PY $S/attio_suppress.py --level <level> <target flags> --apply
```
Report the files and row counts:
- `data/processed/<target>_suppressed_<date>.csv` (target columns + `suppression_reason`, `suppress_until`)
- `data/processed/<target>_clean_<date>.csv`: the list to carry forward
- `data/processed/<target>_unchecked_<date>.csv`: contact level only, rows with no email

Remind the user that the database wasn't changed. If 90-day rows have a `suppress_until` date, mention when the
first ones roll off: re-running this gate later frees them automatically.

## Step 7: Hand-off

Tell the user which clean file to use next and what it's for, e.g. contact search or email enrichment on the
clean companies. The contacts skill (`fetch-contacts-push`) doesn't read the clean file yet. If it's run next,
say so and suggest checking its company list against the suppressed file.

## Guardrails

- Every stage is a gate: no download without a signed-off profile, no `--apply` without a signed-off preview.
- **Contact level = email only, both sides.** Never match on LinkedIn URL, and never run it without emails.
- Never change Supabase or Attio. Never touch the `public` schema. Never print `.env` values or prospect emails.
- Don't edit the scripts for a campaign: every setting is a flag. If the CRM is reconfigured, update the field and
  stage names at the top of `scripts/attio_common.py` and tell the user.
- Worked example with real numbers: `assets/example-2026-10-21.md`.
