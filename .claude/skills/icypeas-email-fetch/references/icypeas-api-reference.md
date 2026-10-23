# Icypeas API Reference Doc

Internal reference for the Icypeas API (email discovery, email verification, domain scan, profile/company scraping, lead database, reverse email lookup).
Source: https://api-doc.icypeas.com (docs v1.15.0). Compiled 2026-10-23.

**Our use:** find work emails for the clean contact list (`data/processed/contacts_clean_2026-10-23.csv`, 270 people: first name, last name, company domain).
**Confirmed live 2026-10-23:** key-only auth works; list reads return `items`; finished-item shape below (5-person sample: 4 found, all `ultra_sure`). **Still unconfirmed:** credit balance, 401/429 bodies.

---

## 1. Base URL

```
https://app.icypeas.com/api
```

- Every endpoint below is a path under `/api`. The subscription route lives under `/api/a/actions/...`.
- There's a single production server and no sandbox. Every search that finds something spends real credits.

---

## 2. Authentication

- Send the **API key alone** in the `Authorization` header on every request, plus `Content-Type: application/json`. The docs stress that the header must contain "your API key (and ONLY your API key)".
- Key-only auth has been supported since v1.4.0 (Nov 2023). Before that, requests were HMAC-signed with the secret. That older scheme is no longer documented.
- **The API secret is not needed to make calls.** Today its only documented use is checking that a **webhook** payload really came from Icypeas: each webhook carries an HMAC-SHA1 `signature` and the `timestamp` it was computed from.
- Our keys live in `.env` as `ICYPEAS_API_KEY` and `ICYPEAS_API_SECRET`.
- To get a key: Icypeas app → API section in the sidebar → enable API access → copy the key and secret.

```bash
curl -X POST https://app.icypeas.com/api/email-search \
  -H "Authorization: $ICYPEAS_API_KEY" -H "Content-Type: application/json" \
  -d '{"firstname":"John","lastname":"Doe","domainOrCompany":"icypeas.com"}'
```

- **Health check / credit balance:** `POST /api/a/actions/subscription-information` with body `{"email": "<account email>"}`. It returns subscription and credit details (and `currency`, since v1.9.1). Use it before every batch. The docs don't say whether it costs credits, but every route not on the credit-cost list is free.

| Auth failure | Meaning |
|---|---|
| `401` | "We could not authenticate you": header missing, or key wrong or disabled |

---

## 3. Endpoints

Every endpoint is `POST` with a JSON body.

### Email discovery (what we need)
| Endpoint | Input → Output | Cost | Limit |
|---|---|---|---|
| `/email-search` | first name + last name + domain/company → email(s) for one person | 1 credit **per email found** | 10/s |
| `/bulk-search` (`task: "email-search"`) | up to **5,000** rows of `[first, last, domainOrCompany]` → one bulk file | 1 credit per email found | 1/s |

### Verification and domains
| Endpoint | Input → Output | Cost | Limit |
|---|---|---|---|
| `/email-verification` | one email → deliverable or not | 0.1 credit **per email tested** | 10/s |
| `/domain-search` | domain or company → emails at that domain | 1 credit if emails are found | 10/s |
| `/bulk-search` (`task: "email-verification"` / `"domain-search"`) | rows of 1 item (email / domain) | as single | 1/s |

### Fetch results and progress (polling)
| Endpoint | Purpose | Limit |
|---|---|---|
| `/bulk-single-searchs/read` | Get search items: one by `id`, all singles (`mode: "single"`), or all rows of one bulk (`mode: "bulk"`, `file`) | **30 calls / min** |
| `/search-files/read` | Bulk file progress (`status: "in_progress"` / `"done"`) | **15 calls / min** |

### Other (not needed for this campaign)
| Endpoint | Cost | Limit |
|---|---|---|
| `/scrape/profile` · `/scrape/company` | 1.5 / 0.5 credit per hit | 20/s |
| `/scrape` (bulk, ≤50 rows) | as single | 20/s |
| `/url-search/profile` · `/url-search/company` · `/url-search` (bulk, ≤50 rows) | 1 credit per URL found | 20/s |
| `/find-people` · `/find-companies` (lead database) | 0.02 credit per result | 30/s |
| `/find-people/count` · `/find-companies/count` | free | 10/s |
| `/reverse-email-lookup` · `/reverse-email-lookups` (bulk, ≤50 rows) | 10 credits per profile found | 20/s · 15/s |
| `/a/actions/subscription-information` | free (not on the cost list) | not listed |

---

## 4. Request shape

### Single email search
```json
{
  "firstname": "John",
  "lastname": "Doe",
  "domainOrCompany": "icypeas.com",
  "custom": { "externalId": "https://www.linkedin.com/in/johndoe", "webhookUrl": "https://..." }
}
```
- `firstname` / `lastname`: either can be empty, but not both (otherwise `first_last_mandatory_discovery_error`).
- `domainOrCompany`: required. **A domain matches better than a company name**, and we have `company_domain` for every contact.
- `custom.externalId`: our own ID, echoed back in results as `userData.externalId`. **We'll use `person_linkedin_url`** so every result joins back to `gtm.contacts`. Icypeas doesn't check that it's unique.
- `custom.webhookUrl`: optional; we have no public server, so we poll instead.

### Bulk search
```json
{
  "name": "clay-contacts-2026-10-23",
  "task": "email-search",
  "data": [["John", "Doe", "icypeas.com"], ["", "Avocado", "yelp.fr"]],
  "custom": {
    "externalIds": ["<linkedin url 1>", "<linkedin url 2>"],
    "webhookUrlItem": "https://...",
    "webhookUrlBulkDone": "https://...",
    "includeResultsInWebhook": false
  }
}
```
- At most **5,000 rows** per call. `externalIds` must be the **same length** as `data`.

### Read results (polling)
```json
{ "id": "kMnquYkBTs8kZM9ND26h" }                                  // one single search
{ "mode": "single", "type": "email-search", "limit": 100 }        // all single searches
{ "mode": "bulk", "file": "<fileId>", "limit": 100 }              // every row of one bulk
```
- Send **either** `id` **or** `mode` (otherwise `mode_or_id_should_be_used_error`). `type` can't be combined with `mode: "bulk"`.
- `limit`: default 10, max **100**.

### Bulk progress
```json
{ "file": "<fileId>" }        // or { "status": "in_progress", "limit": 50 }
```

---

## 5. Response shape

### Submit (single): returns an ID, not a result
```json
{ "success": true, "item": { "_id": "kMnquYkBTs8kZM9ND26h", "status": "NONE" } }
```

### Submit (bulk)
```json
{ "success": true, "file": "kMnquYkBTs8kZM9ND26h", "status": "in_progress" }
```

### A finished search item
Returned by `/bulk-single-searchs/read` (inside `items`) and by the per-item webhook. Confirmed live 2026-10-23; the real item also has `results.li`, `results.saasServices` and `userData.provider`. Found items came back as both `FOUND` and `DEBITED`, so treat the two the same.
```json
{
  "_id": "<search id>",
  "status": "DEBITED",
  "name": "__icypeas__individual",
  "user": "<user id>",
  "file": "<file id, bulk only>",
  "order": 0,
  "results": {
    "firstname": "John", "lastname": "Doe", "fullname": "John Doe", "gender": "...",
    "emails": [
      { "email": "john@icypeas.com", "certainty": "ultra_sure", "mxProvider": "google", "mxRecords": ["..."] }
    ],
    "phones": []
  },
  "userData": { "externalId": "<our linkedin url>", "webhookUrl": "" },
  "system": { "createdAt": "<ISO date>", "modifiedAt": "<ISO date>" }
}
```
- List reads also return `total` and a `sorts` cursor (see §8).
- `results.emails` can hold more than one email. Take the one with the highest certainty.

### Search status (`status`)
| Status | Meaning | Final? | Charged? |
|---|---|---|---|
| `NONE` | Queued, not started | No | – |
| `SCHEDULED` | In the next batch | No | – |
| `IN_PROGRESS` | Searching / verifying | No | – |
| `FOUND` / `DEBITED` | Result found, credits taken | **Yes** | Yes |
| `NOT_FOUND` / `DEBITED_NOT_FOUND` | Processed, nothing found | **Yes** | Search: no (only found emails cost) |
| `BAD_INPUT` | Missing information | **Yes** | No |
| `INSUFFICIENT_FUNDS` | Ran out of credits | **Yes** | No |
| `ABORTED` | Cancelled by us | **Yes** | No |

### Email certainty (`certainty`)
| Value | Meaning | Send to it? |
|---|---|---|
| `ultra_sure` / `very_sure` | ~99% confidence, expected bounce <1% | Yes |
| `probable` | ~95% confidence, expected bounce <5% | Yes, with care (watch bounce rate; consider verifying) |
| `not_found` | No email found (search) / unknown (verification) | No |
| `undeliverable` | Address doesn't exist (verification) | No |

---

## 6. Rate limits

Limits apply to every route. The docs don't say whether they're per key or per account, so assume **per account**.

| Route | Limit |
|---|---|
| `/email-search` (single) | **10 calls / sec** |
| `/email-verification`, `/domain-search` (single) | 10 calls / sec |
| `/bulk-search` | **1 call / sec** (≤5,000 rows per call) |
| **`/bulk-single-searchs/read` (polling for results)** | **30 calls / min** (= 1 call every 2 s) |
| **`/search-files/read` (polling bulk progress)** | **15 calls / min** (= 1 call every 4 s) |
| Scrape / URL search | 20 / sec (bulk: ≤50 rows per call) |
| Find people / companies | 30 / sec (count: 10 / sec) |
| Reverse email lookup | 20 / sec (bulk: 15 / sec, ≤50 rows) |

- Going over a limit returns **`429`** on every route (added in v1.6.1). The docs don't mention any rate-limit headers, so throttle on our side.
- **Polling is the bottleneck, not submitting.** You can submit 10 searches a second but only read results 30 times a minute. So **never poll per search**. Read in pages of 100 (`mode: "single"` or `mode: "bulk"` + `file`) to collect up to 100 results per call.
- For our 270 contacts: one bulk call (or 270 singles over ~27 s), then read 3 pages of 100 roughly every 5–10 s until every item is final. That stays well inside 30/min.
- Icypeas says the limits are "always subject to change". Re-check this page before big runs.

---

## 7. Error codes and messages

| Code | Meaning | Retry? | Action |
|---|---|---|---|
| `200` + `success: true` | Accepted | – | Read `item._id` / `file` |
| `200` + `success: false` | **Validation error** (still HTTP 200!) | No | Fix the fields in `validationErrors[]` |
| `401` | Couldn't authenticate | No | Check `ICYPEAS_API_KEY` in `.env` |
| `429` | Rate limit exceeded | Yes | Back off, then throttle (see §6) |
| `500` / `503` | Server error (not documented, but treat as usual) | Yes | Exponential backoff |

**Always check `success`, not just the HTTP code**, because validation failures come back as 200.

Validation error body:
```json
{
  "success": false,
  "validationErrors": [
    { "expected": "string", "actual": null, "type": "required", "field": "user", "message": "validation_required" }
  ]
}
```

Messages we're most likely to hit:
| Message | Cause |
|---|---|
| `validation_required` / `validation_string_empty` | Required field missing or empty |
| `first_last_mandatory_discovery_error` | Both first and last name empty |
| `external_ids_array_should_match_data_array_error` | `externalIds` length ≠ `data` length |
| `mode_or_id_should_be_used_error` | Read call sent neither `id` nor `mode` |
| `search_not_found_error` | Unknown search `id` |
| `invalid_file_error` / `file_property_error` | Bad bulk `file` ID |
| `validation_number_max` | e.g. `limit` > 100 |

Full list: `validation_array`, `_array_empty`, `_array_min`, `_array_max`, `_array_length`, `_array_enum`, `_boolean`, `_email`, `_number`, `_number_min`, `_number_max`, `_string`, `_string_enum`.
Also, a search with too few credits doesn't error. Its status becomes `INSUFFICIENT_FUNDS`.

---

## 8. Pagination

Cursor-style, using the `sorts` array. It applies to `/bulk-single-searchs/read` (max 100 per page) and `/search-files/read` (max 50 per page).

1. First request: send just `limit` (plus your filters). The response includes `total` and a `sorts` array.
2. Next page: send `limit`, `next: true` and the **exact `sorts` from the last response** (`next: false` goes back a page).
3. Each response returns a new `sorts`. Always replace the old one.
4. **The end is an empty page.** There's no "has more" flag. You can also stop once the number of items read equals `total`.

Order: singles come **newest first**; a bulk read with `file` comes in **the same order as the `data` you sent** (`order` field); bulk reads without `file` come by creation date.
**Save the latest `sorts` after every page** so a run can resume (CLAUDE.md fetch rule 2).

---

## 9. Async versus sync

- **Fully asynchronous.** A search call only queues the work and returns an `_id` (or bulk `file`) with status `NONE`. The email arrives later.
- There are two ways to get results:
  1. **Polling (what we'll use; we have no public server):** read results on a timer until every item reaches a final status (§5). For bulks, `/search-files/read` shows when the file is `done`.
  2. **Webhooks:** `webhookUrl` (single), `webhookUrlItem` (each bulk row) and `webhookUrlBulkDone` (bulk finished: stats only, unless `includeResultsInWebhook`). The receiver must answer HTTP 200. Verify the HMAC-SHA1 `signature` with `ICYPEAS_API_SECRET`.
- The docs suggest waiting "a few seconds" before the first read. No processing time is given; measure it on the 10-record sample.
- How this fits our fetch rules: **stream** each final result to disk as it's read; **resume** from saved search IDs and the latest `sorts`, so a re-run never resubmits (and never re-pays for) a person already submitted; **log** failures to `logs/icypeas_errors.log`.
