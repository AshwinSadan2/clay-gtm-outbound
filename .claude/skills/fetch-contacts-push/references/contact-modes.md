# Contact search: two modes, flags and matching rules

One call per company, run in parallel (default 4 workers, 4.5 requests/second; trial limit is 5/s).
Cost: **1 record per person found. A company with no match costs nothing.** `max_results` is 1, so
each company yields at most one person.

## Pick the mode from the user's answer

| User gives | Mode | Flag | Blitz endpoint | `icp_tier` |
|---|---|---|---|---|
| A priority order of titles ("VP first, else Head, else Director…") | Cascade | `--tier` once per tier, highest first (1–10 tiers) | `POST /v2/search/waterfall-icp-keyword` | 1–10 = the tier that matched |
| One designation / one list of titles, no order | Single title | `--title` once | `POST /v2/search/people` (filtered to the company) | always 1 |

`--tier` and `--title` can't be combined. Blitz's Employee Finder is **not** used: it filters by
seniority and department only, not by job title.

## Flags

| Flag | Meaning | Both modes? |
|---|---|---|
| `--companies FILE` | Companies CSV with `name`, `domain`, `linkedin_url` (normally the Supabase export) | yes, required |
| `--tier T1 T2 …` | One cascade tier: its titles, each quoted. Repeat per tier. Max 50 titles per tier. | cascade |
| `--title T1 T2 …` | The one title list | single |
| `--exclude-title T1 T2 …` | Titles that disqualify a person, on every tier | yes |
| `--tier-exclude N T1 …` | Extra excludes for tier N only (use 1 in single-title mode) | yes |
| `--headline-tier N` | Also match the LinkedIn headline on tier N (use 1 in single-title mode) | yes |
| `--location CODE …` | Where the **person** sits: `WORLD` (anywhere) or ISO codes `US`, `GB`… | yes, required |
| `--limit N` | Max companies this run (default: all remaining) | yes |
| `--date STAMP` | File stamp to write or continue (default today) | yes |
| `--dry-run` | Print endpoint + request, no call | yes |
| `--workers`, `--rps` | Concurrency (leave the defaults on the trial) | yes |

## How titles match (both endpoints)

- Every word of a phrase must appear in the title, as whole words, in any order: `"VP Marketing"` matches
  *VP of Marketing* and *Marketing VP*.
- No abbreviation expansion or stemming: `VP` ≠ `Vice President`, `Demand Gen` ≠ `Demand Generation`.
  **List each variant separately.**
- Hyphens split words: `"Founder"` matches *Co-Founder*.
- `[Brackets]` = exact whole-title match: `"[Owner]"` matches only "Owner", not *Product Owner*.
- One-word titles are broad: `"Growth"` also catches *Growth Engineer*. Prefer two-word phrases.
- Excludes use the same rules. Add excludes for common false hits (e.g. `"Chief of Staff"` on a CEO tier).

## Location

Default to `WORLD`: the company's HQ is already filtered, and the person may sit anywhere.
A contact-side country filter sharply increases no-matches.

## Files written (per date stamp)

- `data/raw/contacts_blitz_<date>.jsonl`: one line per company, with our ids + the untouched response.
  A company counts as done once it's here, so re-runs skip it.
- `data/raw/contacts_blitz_<date>.csv`: readable copy, with `status` = found / no_match per company
- `data/processed/contacts_blitz_<date>.csv`: gtm.contacts columns, found people only. This is the file to push.
- Logs: `logs/blitz_contact_search.log`, failed calls in `logs/blitz_contact_search_errors.log`.
  Failed companies aren't marked done, so re-running the same command retries them.
