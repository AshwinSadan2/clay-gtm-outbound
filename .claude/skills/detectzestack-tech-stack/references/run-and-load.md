# Running the tech-stack scan, distilling it and loading it

How the three scripts behave, the files they write, and how results map to `gtm.companies`.
API facts (endpoints, quota, errors): `detectzestack-api-reference.md` in this folder.

---

## 1. Scripts and flags

### `detectzestack_tech_search.py` (scan)

| Flag | Required | Default | Meaning |
|---|---|---|---|
| `--input` · `--output` | yes | — | Companies CSV · results CSV (appended each run) |
| `--url-column` · `--id-column` | yes | — | Website/domain to scan · unique per company (domain for Supabase) |
| `--limit N` | no | all | Scan at most N **new** companies this run (gate size) |
| `--resume` | after the first run | off | Continue; never re-scans a done or failed company |
| `--retry-failed` | no | off | With `--resume`: try failed companies again (1 call each) |
| `--dry-run` | no | off | Print the sites; no calls |
| `--keep N` | no | 0 | Stop when the monthly quota left reaches N |
| `--rps` | no | 1 (max 2) | Calls per second |
| `--timeout` | no | 60 | Seconds to wait for one scan |
| `--env PATH` | no | `./.env` | `.env` stored elsewhere |

Fixed (API facts, not run values): the `/analyze` path, a browser-style User-Agent (the API's firewall blocks
Python's default: `403 error code: 1010`), RapidAPI's quota header.

### `distill_tech_stack.py` (client signals)

| Step | Flags | Meaning |
|---|---|---|
| `config` | `--doc` · `--config` | Client doc (`docs/<client>-tech-distiller.md`) → config JSON (`data/processed/distiller_<client>_<date>.json`). Refuses: no `## Allowlist`, a type with two ranks, a tool under two types, a relation other than corresponding/adjacent |
| `distill` | `--config` · `--input` · `--output` · `--keep-columns` | Apply the config to any CSV with a `tech_stack` map (results CSV or Supabase export) |
| | `--types` | Subset of the config's types |
| | `--stack-column` (default `tech_stack`) | Column holding the `{type: [tools]}` map |
| | `--project-to N` | Expected companies with a signal in a list of N, with a likely range (±1 standard error) |

### `data.py` (Supabase)

| Command | Meaning |
|---|---|
| `export-companies --email-validation "Safe to Send,Risky"` | Companies whose contact's email has one of these results |
| `export-companies --tech not-scanned` / `--tech scanned` | Never scanned (to scan) / has a stack, exported with it (to distil from the DB) |
| `export-companies --output FILE` | Name the export (default `data/processed/companies_supabase_<date>.csv`). Filters combine |
| `load-tech FILE --id-column domain [--limit N]` | Push `tech_stack` + `tech_enriched_at` (update only) |
| `stats` | Counts, including companies tech-scanned |

## 2. Files written

| File | What |
|---|---|
| `data/processed/tech_stack_companies_<date>.csv` | Input columns + `tech_names`, `tech_stack` (type → tools JSON), `tech_count`, `tech_scan_depth`, `tech_status_code`, `tech_enriched_at`, `tech_cached`, `tech_raw` (full response). **The source for the push** |
| `data/raw/<output name>.jsonl` · `.state.json` | Untouched responses · done/failed companies + last quota seen (resume point) |
| `data/processed/distiller_<client>_<date>.json` | Generated config (never hand-edit; rebuild from the doc) |
| `data/processed/distilled_tech_stack_companies_<date>.csv` | One row per company: kept columns + `tech_tool` + `tech_type` (ranked; blank = no signal). Campaign use only |
| `logs/detectzestack_tech_search.log` · `_errors.log` | Run log · failed calls (time, code, message, site; never the key) |

## 3. Row states

| State | `tech_stack` | `tech_enriched_at` | `tech_status_code` |
|---|---|---|---|
| Scanned | type → tools map | set | site's HTTP status (403 = the site blocked the scanner: thin result) |
| Scanned, nothing detected | `{}` | set | 200 |
| Failed (site down, bad certificate, 502) | blank | set | the error code (e.g. 422) |
| Never tried | — (not in the file) | — | — |

## 4. What to check at each gate

- **Quota:** the run log's `quota left this month`. Every call counts (RapidAPI), failures and cache hits included.
- **Thin results:** `tech_scan_depth = partial` (DNS only) or `tech_status_code` 403: few tools, say so.
- **Failures:** count and reasons from `_errors.log`; one `--retry-failed` at most.
- **Hit rate:** benchmark (Clay, 2026-10-27, 95 B2B SaaS sites): 19% (LinkedIn Ads 12, HubSpot 7, sequencers 0).
  Sequencers and back-office CRMs rarely show on websites; marketing tools and ad pixels do.
- **Missed names:** a tool the user expects but the distiller misses usually has a different detected spelling;
  add a row to the client doc, re-run `config`.

## 5. Loading to Supabase (after the user's go-ahead)

| CSV column | `gtm.companies` column |
|---|---|
| `domain` (the `--id-column`) | `domain`: match key; update only, never insert |
| `tech_stack` | `tech_stack` (jsonb `{type: [tools]}`; blank → null) |
| `tech_enriched_at` | `tech_enriched_at` (set for every attempted company, failures included) |

Not loaded: the raw response, counts, scan depth, status code, cache flag, and **any distilled signal**.
Rule in the database: a stack never exists without the date and is always a JSON object. Re-loading is safe
(unchanged rows left alone). Schema: `docs/schema-companies.md` §4, migration `005_companies_tech_stack.sql`.
