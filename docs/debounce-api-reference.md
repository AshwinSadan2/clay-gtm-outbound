# Debounce API reference (email validation)

Source: https://developers.debounce.com (index: `/llms.txt`), read 2026-10-27. Facts marked **live** were confirmed
with our own key. Used by `.claude/skills/debounce-email-validate/scripts/debounce_email_validate.py`.

---

## 1. At a glance

| Item | Value |
|---|---|
| What it does | Checks whether an email address can receive mail (no email is sent) |
| Style | **Synchronous**: one GET per email, answer in the response (no polling) |
| Hosts | `api.debounce.io` (single, balance, usage) · `bulk.debounce.io` (bulk lists) |
| Auth | API key as query parameter `api=` (13 characters). No header |
| Speed limit | **5 concurrent calls** per account (2 with `append=true`) |
| Cost | 1 credit per validation. `photo=true` +1, `append=true` +20 per hit: **never used** |
| Our plan | 100 credits (100 calls on 2026-10-27 used 98) |

## 2. Authentication

- Every call carries `api=YOUR_KEY` in the query string. Missing/wrong key → **401** `{"debounce":{"error":"Wrong API","code":"0"},"success":"0"}`.
- Because the key sits in the URL, **never log request URLs**. The script logs only the email it sent and
  scrubs the key from any error text.
- Keys starting `public_` are for browser widgets (CORS list, 20 validations per IP per day). Not used here.

## 3. Endpoints

| Method + URL | Purpose | Params | Cost |
|---|---|---|---|
| `GET https://api.debounce.io/v1/` | Validate one email | `api`, `email` · optional `gsuite`, `photo`, `append` | 1 credit |
| `GET https://api.debounce.io/v1/balance/` | Credits left | `api` | Free |
| `GET https://api.debounce.io/v1/usage/` | Calls per date range | `api`, `start`, `end` (`YY-MM-DD`, from `20-08-14`) | Free |
| `GET https://bulk.debounce.io/v1/upload/` | Start a bulk list | `api`, `url` (public HTTPS `.csv`/`.txt` on **your own server**) | 1 per email |
| `GET https://bulk.debounce.io/v1/status/` | Bulk progress + download link | `api`, `list_id` | Free |
| `https://disposable.debounce.io/?email=` | Disposable-domain check | `email` | Free |

**Why we don't use bulk:** Debounce must download the list from a public web link. That would put prospect
data (personal information) on the open internet. Single calls at 5 at a time are fast enough (100 emails ≈ 1 min).

Bulk rules, for reference: < 20 MB, ≤ 200,000 emails, one email per line, one active bulk job per account
(others queue). Status: `processing` / `completed` with `percentage` and `download_link` (CSV).

## 4. Response (single validation)

```json
{
  "debounce": {
    "email": "someone@company.com",
    "code": "5",
    "role": "false",
    "free_email": "false",
    "result": "Safe to Send",
    "reason": "Deliverable",
    "send_transactional": "1",
    "did_you_mean": ""
  },
  "success": "1",
  "balance": "95"
}
```

| Field | Meaning | Our column |
|---|---|---|
| `result` | Final verdict: `Safe to Send` · `Risky` · `Invalid` · `Unknown` | `email_validation` (**loaded to Supabase**) |
| `reason` | Why: `Deliverable`, `Accept All`, `Bounce`, `Unreachable`, … | `email_validation_reason` (CSV) |
| `code` | Numeric code for the reason (see §5) | `email_validation_code` (CSV) |
| `role` | Role address (`sales@`, `info@`) | `email_role` (CSV) |
| `free_email` | Gmail/Yahoo etc. | `email_free` (CSV) |
| `send_transactional` | `1` = fine for sign-up/transactional mail | `email_send_transactional` (CSV) |
| `did_you_mean` | Typo suggestion | `email_did_you_mean` (CSV). **Ignore**: see §8 |
| `balance` | Credits left after this call | — |

All values come back as **strings** (`"true"`, `"1"`), whatever the OpenAPI schema says (**live**).

## 5. Result and reason codes seen

| `result` | `reason` | `code` | What it means | Outreach call |
|---|---|---|---|---|
| Safe to Send | Deliverable | 5 | Mailbox exists | Send |
| Risky | Accept All | 4 | Domain accepts every address; this mailbox can't be confirmed | Send carefully (lower volume, watch bounces) |
| Unknown | Unreachable | — | Mail server didn't answer | Hold or re-check later |
| Invalid | Bounce | — | Mailbox doesn't exist | Never send |

Full code list: https://help.debounce.com/understanding-results/result-codes/ (other reasons include
Syntax, Spam Trap, Disposable, Role).

## 6. Rate limits

| Limit | Value | What happens |
|---|---|---|
| Concurrent single calls | 5 (2 with `append`) | 429 `Maximum concurrent calls reached` |
| Public key | 20 / IP / day | 429 `maximum number of calls per day reached` |
| Bulk jobs | 1 active per account | Extra uploads queue |

There is no per-second limit, only concurrency. The script defaults to 3 at once (`--concurrency`, max 5).

## 7. Errors

| HTTP | Meaning | Script behaviour |
|---|---|---|
| 200 + `success:"0"` | Request failed (message in `debounce.error`) | Log, move on |
| 401 | Wrong / missing key | Log, move on (probe catches it first) |
| 402 | Out of credits (`Credits Low`) | **Stop starting new calls**, save, exit; `--resume` after a top-up |
| 403 | Not allowed for this key | Log, move on |
| 429 | Too many at once | Retry with back-off (5 s, 10 s, 15 s) |
| 500 / 503 | Server error | Retry with back-off |
| Timeout | — | Log, **no retry** (the call may already be charged); `--resume` retries it |

## 8. Findings from our run (2026-10-27, 100 Icypeas-found emails)

| Result | Count |
|---|---|
| Safe to Send (Deliverable) | 63 |
| Risky (Accept All) | 33 |
| Unknown (Unreachable) | 2 |
| Invalid (Bounce) | 2 |

- **Both Invalid emails were Icypeas `ultra_sure`.** Validation catches what the finder's own confidence misses.
- **`did_you_mean` is noise for B2B:** it suggested `.ai` → `.ca`, `.io` → `.co` on 27 of 100 valid company
  emails. Never auto-correct with it.
- No role or free-mail addresses (expected: the finder builds person@company emails).
- 100 calls left **2 of 100 credits**, matching the 2 `Unknown` results: Unknown appears not to be charged
  (unconfirmed; check the dashboard).
