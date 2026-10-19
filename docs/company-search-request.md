# Company Search Request — Clay Target Accounts

**Status:** ⏳ Awaiting approval. Nothing has been pulled yet.
**Source:** `docs/BRIEF.md` §2b (ICP — Company Criteria). Field names are checked against the Blitz OpenAPI spec (see `docs/blitz-api-reference.md`).
**Endpoint:** `POST https://api.blitz-api.ai/v2/search/companies`

---

## The request body

```json
{
  "company": {
    "industry": { "include": ["Software Development"] },
    "keywords": { "include": ["SaaS"] },
    "employee_range": ["51-200"],
    "hq": { "country_code": ["US"] }
  },
  "max_results": 50
}
```

Every later page sends the same body plus `"cursor": "<cursor from the previous response>"`.

## How each filter maps to the brief

| Brief criterion | Blitz field | Value | Notes |
|---|---|---|---|
| Industry: SaaS / software | `company.industry.include` | `["Software Development"]` | Exact, case-sensitive LinkedIn industry string (confirmed in Blitz's accepted list). |
| Exclude tech-media brands | `company.keywords.include` | `["SaaS"]` | Matches "SaaS" in description, specialties, NAICS/SIC or G2/Crunchbase categories. Biases out TechCrunch-style media that self-tag as Software Development. Kept to one term on purpose, because the list is OR'd and extra terms like "software" would re-broaden it. |
| 51–200 employees | `company.employee_range` | `["51-200"]` | Exact LinkedIn size band. |
| US headquarters | `company.hq.country_code` | `["US"]` | ISO 2-letter code (`USA` would return nothing). |
| Company type | — | not set | Brief: don't filter on type. |
| Funding stage | — | not set | Brief: parked. Available later via `last_funding_type` / `total_funding`. |
| Page size | `max_results` | `50` | Maximum allowed per page. |

## Pull plan and record budget

- **Target:** ~300 companies (per `CONTEXT.md` → "Target list").
- **Pages:** 6 pages × 50 = 300 companies, following the cursor. The script hard-stops at 300 even if more match.
- **Cost:** 1 record per company returned → **~300 records**.
- **Budget check (trial, 988 records left):** 300 for companies, then ~300 for one contact per company (Waterfall ICP), leaving **~388** as buffer. Emails come from Icypeas, not Blitz, so they don't touch this budget.
- **Sample before scale:** page 1 is pulled with `max_results: 10` first (10 records). We eyeball those 10 for media/agency/non-SaaS leakage, then run the rest.
- **Rate:** well under the trial's 5 requests/second; 6–7 calls total.

## Where results go

- Raw API pages → `data/raw/companies_blitz_<date>.jsonl` (untouched).
- Each company → upserted into the `accounts` table keyed on `domain`, with the full response kept in a `raw` jsonb column.

## Optional tweaks (not applied unless you say so)

1. **Explicit media exclusion:** add `"keywords": { "exclude": ["media", "publishing", "news"] }` if the sample shows media brands slipping through.
2. **Agency exclusion:** add `"exclude": ["agency", "consulting"]` to keywords if dev shops and agencies show up (they often tag as Software Development).
3. **Size by headcount instead of band:** `employee_count: {min: 51, max: 200}` uses live LinkedIn headcount rather than the self-reported band. It's stricter, but companies that don't keep their LinkedIn page up to date can drop out.
