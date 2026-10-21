# Company search: flags, Blitz fields and matching rules

Endpoint: `POST https://api.blitz-api.ai/v2/search/companies` (cursor pagination, 1–50 per page).
Cost: **1 record per company returned**. Trial plan: ~1,000 records/month, 5 requests/second.
Check the balance any time with `scripts/probe_connections.sh` (free).

## Flag → Blitz field

| Flag (repeatable) | Blitz field | Accepted values | Required |
|---|---|---|---|
| `--industry` | `company.industry.include` | Exact LinkedIn industry string, see `blitz-industries.md` | yes |
| `--keyword` | `company.keywords.include` | Free text | no |
| `--employee-range` | `company.employee_range` | `1-10` `11-50` `51-200` `201-500` `501-1000` `1001-5000` `5001-10000` `10001+` | yes |
| `--country` | `company.hq.country_code` | ISO 2-letter code: `US`, `GB`, `DE`, `CA`… | yes |

Repeating a flag ORs the values: `--employee-range 11-50 --employee-range 51-200` = 11–200 people.
Different flags AND together. Max 50 values per flag.

Other flags: `--limit N` (companies this run), `--page-size` (1–50, default 50), `--resume`,
`--date YYYY-MM-DD` (file stamp), `--dry-run` (print request, no call), `--probe` (1-record count check).

## Matching rules that bite

- **Industry is exact and case-sensitive.** "SaaS", "Tech" or "Fintech" are not industries. Map them to
  list entries (SaaS → `Software Development`; fintech → `Financial Services` + a `fintech` keyword).
  A misspelled industry returns HTTP 422 and costs nothing.
- **Country is ISO 2-letter.** `USA` or `United States` silently return 0 results.
- **Keywords** search the description, specialties, NAICS/SIC and Crunchbase/G2 categories. A phrase
  matches if all its words appear in one of those fields. The list is OR'd, so each extra keyword
  *broadens* the result. Keep it tight (one or two terms). A typo returns 0 results, with no error.
- **Industry alone leaks.** `Software Development` alone pulls tech-media brands (TechCrunch, Entrepreneur)
  that self-tag under it. The `SaaS` keyword fixed this in the 2026-10-19 run. Expect similar leakage in
  other industries and use the sample to catch it.
- **Employee range is LinkedIn's self-reported band**, not live headcount. `employees_on_linkedin` in the
  results is live headcount and can sit outside the band.

## Not exposed as flags (yet)

Blitz also supports keyword exclude, HQ state/city/continent, company type, live headcount ranges,
revenue and funding filters. The scripts don't pass them today. If a brief truly needs one, say so to
the user instead of editing the script silently. Adding a flag is a script change.

## Reading `--probe` output

```
total matching: 106 | records remaining: 393
example: Unlimit | unlimit.com | Financial Services | 583 | GB | payments; fintech; ...
```
- `total matching` = how big the market is under these filters. Thousands means too broad: add a keyword
  or narrow the size. Under ~50 means too narrow: add industries, ranges or countries.
- The example company is the quickest leakage check: does it look like the client's buyer?

## Files written (per date stamp)

- `data/raw/companies_blitz_<date>.jsonl`: every company exactly as returned (used for resume/dedup)
- `data/raw/companies_blitz_<date>.csv`: readable copy, every field
- `data/raw/companies_blitz_<date>.cursor`: next page to resume from
- `data/raw/companies_blitz_<date>.filters.json`: filters used. `--resume` refuses different filters.
- `data/processed/companies_blitz_<date>.csv`: gtm.companies columns, the file to push
- Logs: `logs/blitz_company_search.log`, failed calls in `logs/blitz_company_search_errors.log`

A second, different pull on the same day needs its own `--date`, e.g. `--date 2026-10-21b`.
