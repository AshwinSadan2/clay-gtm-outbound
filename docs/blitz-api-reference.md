# Blitz API Reference Doc

Internal reference for BlitzAPI (B2B data: company & people search, enrichment, verified emails, US phones, job postings).
Source: https://docs.blitz-api.ai (full index: `/llms.txt`, OpenAPI spec: `/api-reference/v2.openapi.json`). Compiled 2026-10-19.

**Our account (as of 2026-10-19):** Startup Trial plan · 988 records remaining · 5 requests/sec per endpoint · resets 2026-11-02.
Re-check any time with `bash .claude/skills/fetch-companies-push/scripts/probe_connections.sh`.

---

## 1. Base URL

```
https://api.blitz-api.ai
```

- All endpoints are versioned under `/v2/...`.
- Single production server; there is no sandbox. Every successful call that returns data uses real records.

---

## 2. Authentication

- API key in an HTTP header on every request: `x-api-key: <key>`.
- Our key lives in `.env` as `Blitz_APIKEY`. Never put it in client-side code (browser/mobile).
- Health check: `GET /v2/account/key-info` returns `valid`, `records_remaining`, `next_reset_at`, `max_requests_per_seconds`, `allowed_apis`, `active_plans`. Use it before every batch run.

```bash
curl https://api.blitz-api.ai/v2/account/key-info -H "x-api-key: $BLITZ_KEY"
```

| Auth failure | Meaning |
|---|---|
| `401` | Header missing or key invalid |
| `402` | Key valid, but the monthly record allowance is used up |
| `404` | Key does not exist |

---

## 3. Endpoints

Every endpoint is `POST` except `key-info` (`GET`).

### Search (people)
| Endpoint | Input → Output | Pagination |
|---|---|---|
| `/v2/search/people` | Company filters + person filters → people across many companies | Cursor |
| `/v2/search/employee-finder` | Company LinkedIn URL + role/level/location → employees at **one** company | Page number |
| `/v2/search/waterfall-icp-keyword` | Company LinkedIn URL + prioritized title cascade → best-fit decision makers, tagged by tier (cached, <600ms) | None |

### Search (companies & jobs)
| Endpoint | Input → Output | Pagination |
|---|---|---|
| `/v2/search/companies` | Industry, headcount, HQ, revenue, funding, keywords → companies | Cursor |
| `/v2/company/tam-by-jobs` | Job + company filters → distinct companies hiring, with matched-jobs count | Cursor (no `total_results`) |
| `/v2/company/tam-by-people` | People + company filters → distinct companies, with matched-people count | Cursor |
| `/v2/jobs/search` | Job title, seniority, location, date + firmographics → job postings | Cursor |
| `/v2/jobs/company` | Company LinkedIn URL → that company's live job postings | Cursor |

### Enrichment (people)
| Endpoint | Input → Output |
|---|---|
| `/v2/enrichment/person` | LinkedIn profile URL → full profile & career history |
| `/v2/enrichment/email` | LinkedIn profile URL → verified work email |
| `/v2/enrichment/phone` | LinkedIn profile URL → mobile/direct phone (**US only, not in free trial**) |
| `/v2/enrichment/email-to-person` | Work email → person profile |
| `/v2/enrichment/phone-to-person` | US phone → person profile |

### Enrichment (companies)
| Endpoint | Input → Output |
|---|---|
| `/v2/enrichment/company` | Company LinkedIn URL → full company profile |
| `/v2/enrichment/domain-to-linkedin` | Website domain → company LinkedIn URL |
| `/v2/enrichment/linkedin-to-domain` | Company LinkedIn URL → email domain |
| `/v2/enrichment/company-distribution-by-country` | Company LinkedIn URL → employees by country |
| `/v2/enrichment/company-distribution-by-department` | Company LinkedIn URL → employees by department |

### Utility
| Endpoint | Purpose |
|---|---|
| `/v2/account/key-info` (GET) | Key validity, plan, limits, records left |
| `/v2/utils/current-date` | Current time in a timezone (0 records) |

**Key gotcha:** Waterfall ICP, Employee Finder, Company Jobs, Company Enrichment, LinkedIn→Domain and both distribution endpoints take a **company LinkedIn URL, not a domain**. If you only have a domain, call `/v2/enrichment/domain-to-linkedin` first.

**Typical outbound chain:** `domain-to-linkedin` → `waterfall-icp-keyword` (or `employee-finder`) → `enrichment/email`.

---

## 4. Request shape

- JSON body, header `Content-Type: application/json`.
- Flat inputs for enrichment: `{"person_linkedin_url": "..."}`, `{"domain": "clay.com"}`.
- Search bodies are nested: `company` filters and `people` filters, plus `max_results` (page size, 1–50) and `cursor` / `page`.
- Include/exclude filters: `{"include": [...], "exclude": [...]}`. Ranges: `{"min": x, "max": y}`.
- Country = ISO 2-letter code (`US`, `GB`). `USA` silently returns 0 results. `"WORLD"` = no geo filter.
- Enumerated values (industry, job level, employee range, company type) are **case-sensitive** and must match the accepted lists exactly (https://docs.blitz-api.ai/guide/reference/normalization).
- Unknown or misspelled fields are rejected with `422`, not silently ignored. Free-text fields (name, keywords, job_title, city) are not validated: a typo just returns 0 results.
- Max 50 items in any filter list.

```json
POST /v2/search/people
{
  "company": {
    "industry": { "include": ["Software Development"] },
    "employee_range": ["51-200", "201-500"],
    "hq": { "country_code": { "include": ["US"] } }
  },
  "people": { "job_level": ["VP", "Director"] },
  "max_results": 25
}
```

```json
POST /v2/enrichment/email
{ "person_linkedin_url": "https://www.linkedin.com/in/someone" }
```

---

## 5. Response shape

Every successful response is JSON and carries a **`fair_usage`** block:

```json
"fair_usage": {
  "records_used": 3,
  "records_remaining": 9913547,
  "next_reset_at": "2026-09-29T10:25:23.155Z",
  "rate_limit": { "requests_per_second": 10, "remaining_this_second": 9 },
  "request_id": "019bae09-..."
}
```

**Search responses** (list):
```json
{
  "total_results": 14337505,
  "results": [ { "first_name": "...", "full_name": "...", "headline": "...", "linkedin_url": "...",
                 "location": {...}, "experiences": [...], "education": [...], "skills": [...] } ],
  "results_length": 3,
  "max_results": 3,
  "cursor": "eyJzIjpb...",
  "fair_usage": { ... }
}
```
Employee Finder uses `page` and `total_pages` instead of `cursor`.

**Enrichment responses** (single object, with a `found` flag):
```json
{
  "found": true,
  "email": "antoine@blitz-agency.com",
  "mx": [{ "priority": 1, "host": "aspmx.l.google.com" }],
  "all_emails": [ { "email": "...", "job_order_in_profile": 1, "company_linkedin_url": "...", "email_domain": "..." } ],
  "fair_usage": { ... }
}
```
- `found: false` = no match. **A miss uses no records.**
- Blitz never guesses email permutations. It returns only emails tied to that person and re-verified at least every 30 days.
- Store `fair_usage.request_id` in our logs for support tickets.

---

## 6. Rate limits

| Plan | Requests/sec **per endpoint** | Records / month |
|---|---|---|
| Free trial (**us**) | 5 | 1,000 |
| Start ($99) | 10 | 200,000 |
| Scale ($499) | 25 | 5,000,000 |
| Build Your Infra | Custom | Custom |

- Limits are **per endpoint**, so `/enrichment/email` and `/search/people` don't share a budget.
- Short bursts may be queued; sustained overage → `429`. After a server `429`, wait **≥60 seconds**.
- Read the live limit from `key-info.max_requests_per_seconds` rather than hard-coding it.
- Several workers hitting the **same** endpoint must split the limit between them (e.g. 2 workers on the trial → about 2 req/s each).
- Recommended client timeout: **10 s**. Don't auto-retry a timeout, because the server may already have counted the records.
- **Record budget:** 1 record = 1 company / person / email / phone / job returned. Search pages cost one record per result, so `max_results: 50` costs up to 50 records. On the trial (1,000 records/month), always cap pulls.

---

## 7. Error codes and messages

All errors return `{"success": false, "message": "..."}`.

| Code | Meaning | Retry? | Action |
|---|---|---|---|
| `400` | Body isn't valid JSON | No | Fix JSON / Content-Type |
| `401` | Missing/invalid `x-api-key` | No | Check `.env` key |
| `402` | Monthly records exhausted | No | Wait for reset or upgrade |
| `404` | API key doesn't exist | No | Check key |
| `422` | Unknown field or invalid value | No | Fix fields listed in `errors[]` (uses no records) |
| `429` | Rate limit exceeded | Yes | Back off ≥60 s; throttle client-side |
| `500` | Transient server error | Yes | Exponential backoff |
| `503` | Service unavailable | Yes | Exponential backoff |

422 example. Read `errors[].field` in code; treat `message` as human text that may change.
```json
{
  "success": false,
  "message": "Invalid request body. company.industry.include[0]: Invalid value \"Software\". Did you mean \"Computer Software\", \"Software Development\" ...?",
  "errors": [
    { "field": "company.industry.include[0]", "message": "Invalid value \"Software\". Did you mean ...?" }
  ]
}
```

---

## 8. Pagination

| Style | Endpoints | How |
|---|---|---|
| **Cursor** | `search/people`, `search/companies`, `company/tam-by-jobs`, `company/tam-by-people`, `jobs/search`, `jobs/company` | Send `cursor` from the previous response; stop when `cursor` is `null` |
| **Page number** | `search/employee-finder` | Send `page` (1, 2, …); response has `page` and `total_pages` |
| **None** | `waterfall-icp-keyword`, all `enrichment/*`, `utils/*`, `account/*` | Single response |

- `max_results` = **page size (1–50)**, not a total.
- Cursors are stable, so new records added mid-run won't create duplicates.
- Server-side caps: people/companies 50,000 results (1,000 pages); employee finder 10,000; jobs 5,000.
- `tam-by-jobs` has no `total_results`. Keep paging until `cursor` is null; a short page doesn't mean the end.
- **Always set our own total cap** before looping, because every result returned costs a record.

---

## 9. Async versus sync

- **The API is fully synchronous.** Every endpoint returns its result in the same HTTP response. There are no job IDs, polling or webhooks.
- Latency is roughly sub-second (Waterfall ICP <600 ms, cached); budget 10 s timeouts.
- "Async" only exists **client-side**: the official Python SDK (`blitz-api-py`) ships both `BlitzAPI` (sync) and `AsyncBlitzAPI` (async/await) with identical methods. The TypeScript SDK (`blitz-api-js`) is promise-based.
- Both SDKs include per-endpoint rate limiting (default 5 req/s), auto-retry on `429`/`5xx` (3 retries), and auto-pagination with a `max_items` cap.
- For bulk work, run many requests concurrently (async client or worker pool) while staying under the per-endpoint limit.
