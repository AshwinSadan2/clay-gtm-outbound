---
name: detectzestack-tech-stack
description: Detect each company's website tech stack with DetectZeStack (RapidAPI), distil it to one client's ranked signals (e.g. CRM, sequencer, ad pixel), and load the full stack into Supabase gtm.companies. Takes a companies CSV or a Supabase export, gates 1 → 10 → 100 → full run, builds the client's distiller doc, and pushes only after sign-off. Use when the user wants tech-stack, technographic or tool-signal enrichment for companies.
---

# DetectZeStack tech stack (companies → stack → client signals → gtm.companies)

Scans each company's website for the technologies it runs, keeps the **full stack** in Supabase, and distils it
to the **client's signals** in a campaign CSV. Distilled signals are per client and transient: never in Supabase.
Every value comes from the user or the list. **Never edit the scripts for a run.**

Run everything from the project folder (outputs go to its `data/` and `logs/`; keys from its `.env`, see this
skill's `.env.template`; `--env PATH` if elsewhere). The shell is zsh: pass flags as a bash array
(`bash -c '... "${F[@]}"'`), never as one `$FLAGS` string.
```bash
S=.claude/skills/detectzestack-tech-stack/scripts
PY=.venv/bin/python
```

The user is not a developer: plain English, short tables, technical calls yours. The input list, the client
facts, the signal ranking, every gate and the push are theirs.

**References:** `references/run-and-load.md` (flags, files, states, checks, DB mapping) ·
`references/detectzestack-api-reference.md` (API, 9 points) · `references/clay-relevant-tech-providers.md` (the
owner's universe of client-relevant, detectable tools: the model for any client) · `references/clay-tech-distiller.md`
(a finished client doc) · **Asset:** `assets/client-tech-distiller-template.md` (start of every new client doc).

## Step 0: Preflight (free)

1. `sed -E 's/[A-Za-z0-9]/x/g' .env` **as its own command**, read it first. Every line must be `KEY=value`; if
   not, stop and fix it with a script that prints nothing, or ask. Then confirm `RAPIDAPI_HOST` and `RAPIDAPI_KEY`
   are filled in (names and lengths only, never values).
2. If Supabase is involved: `bash $S/probe_connections.sh` must show **POOLER OK**.

There is no free key check: every DetectZeStack call counts against the monthly quota. The 1-row check is the probe.

## Step 1: Input

Ask: **"Which companies: a CSV you have, or a list from our Supabase database?"**
- **CSV:** read only its header and row count; propose `--url-column` (website or domain) and `--id-column`
  (unique per company: the domain if results go to Supabase); confirm.
- **Supabase:** turn the user's criteria into flags, e.g. companies with a mailable contact, never scanned:
  `$PY $S/data.py export-companies --email-validation "Safe to Send,Risky" --tech not-scanned --output data/processed/companies_<what>_<today>.csv`
  `--tech not-scanned` keeps already-scanned companies out (no paying twice). Show the count and dedupe check.

Output: `--output data/processed/tech_stack_companies_<today>.csv` (one file per list, appended each run).
`F` = `--input IN --output OUT --url-column COL --id-column COL`.

## Step 2: First-row check (1 call)

`... "${F[@]}" --limit 1 --dry-run` → `... "${F[@]}" --limit 1`. Show: technologies found, `tech_scan_depth`, the
**quota left** from the run log. Compare quota with the list size (free plan 100/month; Pro $9 = 1,000). If short,
say how many it covers and ask: scan that many, or upgrade first. Ask: **"Looks right? Next: 9 more (10 total)."**

## Step 3: 10 rows

`... "${F[@]}" --resume --limit 9`. Show a table: company, tech count, a few notable tools, failures.

## Step 4: Who is this for?

Read `references/clay-relevant-tech-providers.md` first. Ask: **"Are you building this for Clay or another client?"**
- **Clay:** use `docs/clay-tech-distiller.md` (CRM > Sequencer > Ad pixel); confirm the types and ranking still hold.
- **Another client:** look the client up (web): what they sell, who buys, what they integrate with or replace.
  If public information is thin, ask **targeted** questions built from the universe doc and the tech actually
  found in the 10 rows (e.g. "Does your product plug into HubSpot, or replace it?", "Would a LinkedIn Ads pixel
  mean a good fit?"). Never a vague "tell me about the client".

## Step 5: Build the client's distiller

1. Map the 10-row tech (and the universe doc) to the client: **corresponding** = tools the client plugs into or
   replaces; **adjacent** = related tools that signal fit without a direct hook.
2. Write `docs/<client>-tech-distiller.md` from `assets/client-tech-distiller-template.md` (decisions table +
   `## Allowlist` table `| Rank | Type | Tool | Relation |`). The user never writes it; they review it.
3. Ask the user to **rank the signal types** (1 = most important); rank decides the order in `tech_tool`.
4. On sign-off, convert: `$PY $S/distill_tech_stack.py config --doc docs/<client>-tech-distiller.md --config data/processed/distiller_<client>_<today>.json`

## Step 6: Hit rate on 10

`D` = `--config CONFIG --input OUT --output data/processed/distilled_tech_stack_companies_<today>.csv --keep-columns name,domain,website,linkedin_url`
(keep the columns the list has). `$PY $S/distill_tech_stack.py distill "${D[@]}"`: show hits per tool, the hit
rate, and the 10 rows' signals. If 0 hits, revisit the allowlist with the user before spending more.

## Step 7: 100 rows and projection

`... "${F[@]}" --resume --limit 90`, then `distill "${D[@]}" --project-to <list size>`. Show the hit rate at 100 and
the projection (e.g. 35/100 → ~350 of 1,000, with the likely range). Ask: **"Run the rest (N companies, N calls)?"**
Never go from 10 straight to the full list.

## Step 8: Full run

- ≤ 50,000 left: `... "${F[@]}" --resume`. More: batches of `--resume --limit 50000`, a summary and "continue?" between.
- Stops on quota (`stopped early: … quota`): tell the user; `--resume` after the monthly reset or an upgrade.
- Failures (site down, bad certificate, bot block) are logged and get a row with the date, no stack. Offer
  `--resume --retry-failed` once (it costs a call each).

Then distil the full CSV (Step 6 command with `--project-to` dropped). Final summary: companies scanned / failed,
hit rate, signals per type and tool, quota left, the two output files.

## Step 9: Push to Supabase (after sign-off)

Ask: **"Load the tech stacks into the database?"** Only `tech_stack` (type → tools map) and `tech_enriched_at`.
1. `$PY $S/data.py load-tech OUT --id-column domain --limit 10`, then ask the user to look in Supabase
   (`gtm` schema → `companies`, filter `tech_enriched_at` is not null; the columns are at the far right).
2. On their OK: `$PY $S/data.py load-tech OUT --id-column domain`, then `$PY $S/data.py stats`.

Later campaigns can distil straight from the database: `data.py export-companies --tech scanned --output FILE`,
then `distill` on that file. No re-scan, no cost.

## Rules

- Gate order: preflight → 1 → 10 → client + distiller → 100 → full → distil → push, with a sign-off at each arrow.
- Every call costs quota, failures included. Never re-scan a done company (`--resume`; `--tech not-scanned`).
- Distilled signals (`tech_tool` / `tech_type`) never go to Supabase. The full stack never leaves it out.
- The full results CSV keeps `tech_raw` (the raw response). Never edit it or anything in `data/raw/`.
- One distiller doc per client in `docs/`; the config JSON is generated from it (never hand-edited).
- Never print `.env` values. `data.py` and `probe_connections.sh` are identical copies across the skills.
