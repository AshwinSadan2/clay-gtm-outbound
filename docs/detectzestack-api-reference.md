# DetectZeStack API reference (tech-stack detection, via RapidAPI)

Sources, read 2026-10-27: the provider's OpenAPI spec (`https://detectzestack.com/openapi.yaml`), `llms.txt`,
the pricing page, and the RapidAPI listing (https://rapidapi.com/mlugoapx/api/detectzestack). Facts marked
**live** were confirmed with our own key. Used by `.claude/skills/detectzestack-tech-fetch/scripts/detectzestack_tech_search.py`.

What it does: give it a website, get back the technologies the site runs (CMS, frameworks, CDN, hosting,
analytics, marketing tools, payments, security), each with categories, a confidence score and, when known, a
version and CPE id. Four detection layers run on every scan: Wappalyzer fingerprints (3,800+), DNS CNAME
mapping (200+ providers), TLS certificate issuer, and custom HTTP header patterns.

---

## 1. Base URL

| Route | Base URL | Auth |
|---|---|---|
| **RapidAPI gateway (ours)** | `https://detectzestack.p.rapidapi.com` | RapidAPI key + host headers |
| Direct (Stripe billing) | `https://detectzestack.com` | `X-API-Key` header (a separate key we don't have) |
| Demo, no key | `https://detectzestack.com/demo?url=` | None; 20 / hour / IP |

The host value `detectzestack.p.rapidapi.com` is not secret; it is `RAPIDAPI_HOST` in `.env` (**live**).

## 2. Endpoints

Every endpoint is available on every plan unless marked otherwise. Cost is per call against the monthly quota.

| Method + path | Purpose | Key params | Cost |
|---|---|---|---|
| **`GET /analyze`** | **Full tech-stack scan of one site (what we use)** | `url` (req): `stripe.com` or `https://stripe.com` | 1 |
| `POST /analyze/batch` | Scan up to 10 sites at once (CSV output possible) | body `{"urls":[…]}`, `?format=json\|csv` | 1 per URL · **Ultra+** |
| `POST /compare` | Shared vs unique tech across 2–10 sites | body `{"urls":[…]}` | 1 per URL · **Ultra+** |
| `GET /check` | Does a site use one named technology? | `url`, `tech` (req) | 1 |
| `GET /lookup` | Reverse: domains using a technology | `tech` (req), `limit` (50), `offset` (0) | 1 |
| `GET /history` | Past stack snapshots for a domain | `domain` (req), `limit` (20, max 100), `offset`, `include_changes` | 1 |
| `GET /changes` | Feed of added/removed tech | `domain` (opt); depth by tier: Free 7 d · Pro 30 · Ultra 90 · Mega 365 | 1 |
| `GET /dns` | DNS records + provider enrichment | `domain` (req) | 1 |
| `GET /security` | Security headers, letter grade | `url` (req) | 1 |
| `GET /certificate/check` | TLS certificate details | `url` (req) | 1 |
| `GET /vulnerability` | CVEs for detected tech (CPE → NVD) | `url` (req), `severity` (opt) | 1 |
| `GET /site` | All of the above in one call | `url` (req) | **3** · Ultra+ |
| `GET /stats` | Our usage this month (tier, used, limit) | — | **1 (live: it counted)** |
| `GET /health` | Service health | — | Free, no auth |
| `/webhooks`, `/watches` (GET/POST/PATCH/DELETE) | Change alerts by webhook / email / Slack | see spec | Watches: Free 0 · Pro 5 · Ultra 25 · Mega 125 |

## 3. Authentication

Two headers on every call (RapidAPI route):

```
x-rapidapi-key:  <RAPIDAPI_KEY from .env>      (50 characters, one key for every RapidAPI API)
x-rapidapi-host: detectzestack.p.rapidapi.com  (RAPIDAPI_HOST from .env; picks the API)
```

- RapidAPI forwards the call to the provider with its own `X-RapidAPI-Proxy-Secret`; we never see or send it.
- Wrong / missing key → RapidAPI refuses before the provider sees it (401/403 with a RapidAPI message).
- **Bot block (live):** the provider's firewall (Cloudflare) answers `403 error code: 1010` to Python's default
  `User-Agent`. Always send a browser-style `User-Agent` header.

## 4. Request shape

All reads are `GET` with query parameters; batch/compare are `POST` with a JSON body.

```bash
curl -H "x-rapidapi-key: $RAPIDAPI_KEY" -H "x-rapidapi-host: detectzestack.p.rapidapi.com" \
     -H "User-Agent: Mozilla/5.0" \
     "https://detectzestack.p.rapidapi.com/analyze?url=stripe.com"
```

```json
POST /analyze/batch      {"urls": ["stripe.com", "shopify.com", "github.com"]}     (1–10 URLs)
```

- `url` accepts a bare domain or a full URL. We send the bare domain (`gtm.companies.domain`).
- No request IDs, no custom fields: we join results back by the domain we sent.

## 5. Response shape

`GET /analyze` → `200`:

```json
{
  "url": "https://stripe.com",
  "domain": "stripe.com",
  "technologies": [
    {
      "name": "React",
      "version": "18.2.0",
      "categories": ["JavaScript frameworks"],
      "confidence": 100,
      "description": "A JavaScript library for building user interfaces",
      "website": "https://reactjs.org",
      "icon": "React.svg",
      "cpe": "cpe:2.3:a:facebook:react:*:*:*:*:*:*:*:*",
      "source": "http"
    }
  ],
  "categories": {"JavaScript frameworks": ["React"], "CDN": ["Cloudflare"]},
  "meta": {"status_code": 200, "tech_count": 12, "scan_depth": "full"},
  "cached": false,
  "response_ms": 840,
  "_usage_warning": {"message": "…", "upgrade_url": "…"}
}
```

| Field | Meaning |
|---|---|
| `technologies[]` | One entry per technology. `version` / `cpe` only when known |
| `technologies[].source` | Which layer found it: `http` · `dns` · `certificate` · `wappalyzer` (DNS-only hits are weaker evidence) |
| `technologies[].confidence` | 0–100 |
| `categories` | Category → technology names (handy summary) |
| `meta.scan_depth` | `full` = page fetched; `partial` = only DNS worked (site blocked or down): a thinner result |
| `meta.status_code` | HTTP status the provider got from the site |
| `cached` | `true` = served from the provider's 24-hour cache |
| `_usage_warning` | Only present when near or over the monthly limit |

Batch → `{"results":[{"url","result":<AnalyzeResponse>,"error"}], "total_ms", "successful", "failed"}`.
Errors → `{"error": "…"}`; quota errors add `limit`, `used`, `tier`, `needed`, `upgrade`.

Response headers worth reading:

| Header | Set by | Meaning |
|---|---|---|
| `X-RateLimit-Requests-Limit` / `-Remaining` / `-Reset` | **RapidAPI** | Monthly quota, what's left, seconds to reset. **This is the counter that bills us** |
| `X-RateLimit-Limit` / `-Remaining` / `-Used` | Provider | Provider's own monthly count |
| `X-Cache` | Provider | `HIT` (24 h cache) / `MISS` (fresh scan) |

## 6. Pagination

- `/analyze` returns one site in full: **no pagination**.
- `/lookup` and `/history` page with `limit` + `offset` (offset = rows to skip). `/lookup` results are capped
  by tier: Basic 25 · Pro 100 · Ultra 500 · Mega 2,000. `/history` max 100 per page.
- `/watches` list returns `limit` info; `/changes` filters by domain and tier-gated time depth.

## 7. Sync vs async

**Synchronous.** Each `/analyze` call scans (or reads cache) and returns the result in the same response,
usually within seconds. No job ids, no polling. Webhooks/watches exist only for *ongoing change alerts*, not
for getting scan results.

## 8. Rate limits and quota

| Plan (RapidAPI) | Price | Requests / month | Notes |
|---|---|---|---|
| **Basic (ours)** | Free | **100** | Every endpoint except `/site`, batch, compare |
| Pro | $9 | 1,000 | 5 change watches |
| Ultra | $29 | 10,000 | Batch + compare, `/site`, "higher rate limits", 25 watches |
| Mega | $79 | 50,000 | 125 watches, priority queue |

- **Monthly quota is the real limit.** It resets each calendar month on the provider side; RapidAPI's
  `X-RateLimit-Requests-Reset` showed ~31 days (**live**: 2,678,306 s on 2026-10-27).
- **What counts:** the provider refunds cache hits (`X-Cache: HIT`) and failed scans (4xx/5xx). **RapidAPI
  counts every call through the gateway**, including a 404 and `/stats` (**live**: 2 test calls → 98 left).
  Plan on 1 quota unit per call, whatever the outcome.
- **Per-second limit:** not published. We send 1 call per second (`--rps`, max 2).
- Demo endpoint: 20 / hour / IP. Watch email registration: 5 / hour.
- Free-plan accounts also carry a RapidAPI-wide hard limit (`X-RateLimit-rapid-free-plans-hard-limit-*`, 500,000),
  far above our use.

## 9. Error codes and messages

| HTTP | Message (example) | Cause | Script behaviour |
|---|---|---|---|
| 400 | `{"error":"…"}` missing `url` | Bad request | Log, mark failed |
| 401 | `Unauthorized` / RapidAPI `Invalid API key` | Wrong key | Log, mark failed (fix `.env`) |
| 403 | `error code: 1010` | Firewall blocked the User-Agent | Fixed by the browser-style User-Agent |
| 403 | RapidAPI `You are not subscribed to this API` | No plan on RapidAPI | Subscribe (free plan) |
| 404 | `Endpoint '/' does not exist` | Wrong path (from RapidAPI) | — |
| 422 | `/check`: failed to fetch the target site | Site down / blocked | Log, mark failed |
| 429 | `{"error","limit","used","tier","upgrade"}` or RapidAPI `You have exceeded the MONTHLY quota` | Quota used up | **Stop the run**; `--resume` next month or after an upgrade |
| 429 | rate limit | Too fast | Retry with back-off (10 s, 20 s) |
| 502 | `Failed to analyze URL` | Site couldn't be scanned | Log, mark failed; `--resume --retry-failed` later |
| 503 | — | Provider degraded (`/vulnerability`, `/health`) | Retry with back-off |

All error bodies are JSON `{"error": "…"}` from the provider, or `{"message": "…"}` from RapidAPI.
