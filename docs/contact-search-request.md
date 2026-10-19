# Contact Search Request — Marketing / RevOps Leader per Account

**Status:** ⏳ Awaiting approval. Nothing has been pulled yet.
**Source:** `docs/BRIEF.md` §2c (Persona), `docs/CONTEXT.md` (Persona, icp_tier).
**Endpoint:** `POST https://api.blitz-api.ai/v2/search/waterfall-icp-keyword`, one call per company.
**Input:** `linkedin_url` of each of the 300 companies in `data/processed/companies_blitz_2026-10-19.csv`.

---

## Why Waterfall ICP

The brief's persona is a **6-tier title cascade: the first tier with a match wins, one person per company**. That is exactly what Waterfall ICP does. We send the tiers in priority order with `max_results: 1`; Blitz walks down the tiers and returns the single best person, plus an `icp` field saying which tier matched. That becomes our `icp_tier` (1–6).

## How Blitz matches titles (this shapes the lists below)

- Every word in a phrase must appear as a **whole word, in any order**: `"VP Marketing"` matches *VP of Marketing* and *Marketing VP*.
- **No abbreviation expansion or stemming**: `VP` ≠ `Vice President`, `Demand Gen` ≠ `Demand Generation`. So each variant is listed separately.
- Hyphens split words: `"Founder"` matches *Co-Founder*; `"CEO"` matches *Co-CEO*.
- `[brackets]` = exact whole-title match.

## The request body

```json
{
  "company_linkedin_url": "<from accounts CSV>",
  "max_results": 1,
  "cascade": [
    {
      "include_title": [
        "VP Marketing", "Vice President Marketing", "SVP Marketing", "Senior Vice President Marketing",
        "EVP Marketing", "CMO", "Chief Marketing Officer",
        "VP Growth", "Vice President Growth",
        "VP Demand Generation", "VP Demand Gen", "Vice President Demand Generation"
      ],
      "exclude_title": ["$EXCLUDES"],
      "location": ["WORLD"]
    },
    {
      "include_title": ["Head Marketing", "Head Growth", "Head Demand Generation", "Head Demand Gen"],
      "exclude_title": ["$EXCLUDES"],
      "location": ["WORLD"]
    },
    {
      "include_title": ["Director Marketing", "Director Growth", "Director Demand Generation", "Director Demand Gen"],
      "exclude_title": ["$EXCLUDES"],
      "location": ["WORLD"]
    },
    {
      "include_title": [
        "VP Revenue Operations", "Vice President Revenue Operations",
        "Head Revenue Operations", "Director Revenue Operations",
        "RevOps", "GTM Engineer", "Go To Market Engineer"
      ],
      "exclude_title": ["$EXCLUDES"],
      "location": ["WORLD"]
    },
    {
      "include_title": ["Founder", "CEO", "Chief Executive Officer", "[Owner]"],
      "exclude_title": ["$EXCLUDES", "Chief of Staff", "Advisor"],
      "location": ["WORLD"]
    },
    {
      "include_title": ["Marketing", "Growth", "Demand Generation", "Demand Gen", "Revenue Operations"],
      "exclude_title": ["$EXCLUDES"],
      "location": ["WORLD"],
      "include_headline_search": true
    }
  ]
}
```

`$EXCLUDES` (same on every tier, from brief §2c):
```json
["Assistant", "Intern", "Junior", "Coordinator", "Freelance",
 "Brand", "Communications", "Content", "PR", "Social Media"]
```

All tiers search **current jobs only** (Blitz default) and **any location** (`WORLD`), per the brief.

## Tier map

| Tier (`icp_tier`) | Brief persona | Notes |
|---|---|---|
| 1 | Senior marketing: VP/SVP/CMO + VP Growth/Demand Gen | `"VP Marketing"` also catches *VP Product Marketing*, which the brief's `{ROLE}` bank treats as marketing |
| 2 | Head of Marketing / Growth / Demand Gen / Marketing Ops | `"Head Marketing"` already covers *Head of Marketing Operations* |
| 3 | Director of Marketing / Growth / Demand Gen / Marketing Ops | Also catches *Senior Director, Marketing* |
| 4 | RevOps leaders + GTM Engineer | `"RevOps"` alone also catches *RevOps Manager* (the brief lists "RevOps" itself) |
| 5 | Founder / Co-founder / CEO / Owner | Extra excludes stop *Chief of Staff to the CEO* and *Advisor to the CEO* |
| 6 | Manager/IC + headline catch-all | Headline search on, so a *"Growth marketer, B2B SaaS"* headline counts too |

## Deviations from the literal brief (flagged for you)

1. **`[Owner]` in exact-match brackets.** Plain `"Owner"` would match *Product Owner*, which is common at software companies and not our persona. In brackets it matches only a title that is exactly "Owner".
2. **Extra founder-tier excludes** `Chief of Staff`, `Advisor` (see tier 5). Not in the brief, but they stop false CEO matches.

## Pull plan and record budget

- **Calls:** 300 (one per company), **cost = 1 record per person found; a company with no match costs nothing.**
- **Budget:** ≤300 records of the 688 left → **≥388 remaining** afterwards.
- **Sample first:** run the first 10 companies (≤10 records), review titles and tier spread, then run the other 290.
- **Concurrency:** unlike the company search, these calls are independent, so they run in parallel: 4 workers, capped at our 5 requests/second for this endpoint. 290 calls take ~1 minute.
- **Follows the CLAUDE.md fetch rules:** streams each contact to disk as it arrives, skips companies already done on re-run, failed calls go to `logs/blitz_contact_search_errors.log`.

## Where results go

- `data/raw/contacts_blitz_<date>.jsonl` + `.csv`: every person exactly as returned.
- `data/processed/contacts_blitz_<date>.csv`: review columns (to be agreed after the sample, like we did for companies) + `company_domain`, `icp_tier` + a `raw` JSON column.
- A no-match company is logged as such, so we can see which accounts came back empty.

## Optional tweaks (not applied unless you say so)

1. **Tighten tier 6 "Growth".** On its own it can catch *Growth Engineer* or *Growth Product Manager*. Replace with `"Growth Marketing"`, `"Growth Manager"`, `"Growth Lead"`.
2. **`profile_min_connections: 50`.** Skips near-empty or abandoned LinkedIn profiles that tend to bounce or ignore outreach.
3. **Add `"Chief Growth Officer"` to tier 1.** A common title at this stage, though not named in the brief.
