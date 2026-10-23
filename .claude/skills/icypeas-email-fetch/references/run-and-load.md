# Running the email search and loading it

How `icypeas_email_search.py` behaves, how to size the gates, and how results map to `gtm.contacts`.
Icypeas API facts (endpoints, limits, statuses, errors): `icypeas-api-reference.md` in this folder.

---

## 1. Inputs

| Source | How | Notes |
|---|---|---|
| A CSV the user gives | Use as is (never edit it). Read its header, propose the column mapping, confirm | Name, last name and domain columns are needed. An id column unique per person is needed too. For a Supabase load it must hold the LinkedIn URL |
| Supabase | `data.py export-contacts --exclude-domains SUPPRESSION.csv --exclude-column domain` | Default: contacts never email-searched (`email_enriched_at` null). `--all` includes searched ones (re-search costs credits again). Writes `data/processed/contacts_supabase_<date>.csv` |

- **Suppression:** always offer the newest `data/processed/suppression_*.csv` as `--exclude-domains`. Enriching
  customers / open deals wastes credits. If none exists, say so and offer the `/suppression-gate` skill first.
- First name **or** last name may be blank, not both (Icypeas rejects it: `first_last_mandatory_discovery_error`).
- A domain matches better than a company name. If only a company name exists, `--domain-column` can point at it.

## 2. Flags

| Flag | Required | Meaning |
|---|---|---|
| `--contacts FILE` | yes | Input CSV |
| `--output FILE` | yes | Results CSV, appended each run. One per input list: `data/processed/contacts_email_enriched_<date>.csv` (add a list name if two lists run the same day) |
| `--first-name-column` · `--last-name-column` · `--domain-column` · `--id-column` | yes | Input column names |
| `--limit N` | no | Submit at most N **new** people this run (gate size) |
| `--resume` | after the first run | Continue: poll anything pending, then submit the next people. Required once a run has started |
| `--dry-run` | no | Print the requests; no calls, no credits |
| `--probe [--account-email E]` | no | Key check; with the account login email, also the credit balance. Free |
| `--submit-rps` (default 5, max 10) · `--reads-per-min` (default 27, max 30) | no | Speeds, capped at Icypeas limits |
| `--poll-every` (10 s) · `--max-wait` (600 s) | no | Polling rhythm; when `--max-wait` runs out, the run saves and exits; `--resume` carries on |
| `--env PATH` | no | `.env` stored elsewhere |

A forgotten required flag stops the run. There are no campaign defaults.

## 3. Files written

| File | What |
|---|---|
| `--output` | Input columns + `email`, `email_status`, `email_mx_provider`, `email_enriched_at`, `email_search_id`, `email_provider_status`, `email_certainty`, `emails_found`, `raw` |
| `data/raw/<output name>.jsonl` | One line per finished search, Icypeas's answer untouched |
| `data/raw/<output name>.state.json` | Every submitted search id + who is done: the resume point |
| `logs/icypeas_email_search.log` · `_errors.log` | Run log · failed calls (time, HTTP code, message, request) |

**Streaming + resume:** each search id is saved the moment Icypeas returns it, and each result is written and
flushed the moment it's final. A stopped run loses nothing. `--resume` never resubmits (never re-pays) a person.
The state file remembers its input file: pointing a started `--output` at another input is refused.

## 4. Gates and batch sizes

| Gate | Command adds | User sees |
|---|---|---|
| Dry run | `--limit 5 --dry-run` | The 5 requests |
| Sample | `--limit 5` | All 5 rows (`review_results.py --last 5 --show 5`) |
| Second gate | `--resume --limit 100` | Summary of the 100 + `--show 10` |
| Scale | `--resume` (≤ 50,000 left) or `--resume --limit 50000` per batch | Summary after each batch |

- Never jump from the sample straight to the full list.
- More than 50,000 left: batches of 50,000, with a summary and a "continue?" between batches.
- Before scaling, compare the remaining people with the credit balance from `--probe --account-email`. Each
  person can cost 1 credit. If credits are short, say how many people they cover and ask.
- **Long runs:** sending is 5/s (`--submit-rps 9` speeds it up), so 50,000 people ≈ 1.5–3 hours. Run big batches
  in the background and set `--max-wait 3600`. Each polling round reads 100 results per call at ≤30 calls/min,
  so 50,000 pending ≈ 18 min per round. If time runs out, `--resume`.

## 5. What to check at each gate

`review_results.py` prints these. Flag anything unusual to the user:
- **Found rate.** The Clay list ran 70–80% for VP / Head titles. Much lower suggests bad domains or names.
- **Emails not on the company domain:** should be 0. Any hit suggests a wrong domain in the input.
- **More than one email per person:** the script keeps the most certain one. Mention the count.
- **Errors this run** (end of the run log): open `logs/icypeas_email_search_errors.log` if not 0.
- **Odd names** (emoji, symbols, "MBA", "PhD" in the name) can still find an email but need cleaning before outreach.
- **Billing caveat:** Icypeas marks some misses `DEBITED_NOT_FOUND`. Whether a miss costs a credit is
  unconfirmed. Ask the user to compare the dashboard's credits used with the found count.

## 6. Loading to Supabase (after the user's go-ahead)

`data.py load-emails FILE --id-column person_linkedin_url [--limit 10]`

| CSV column | `gtm.contacts` column |
|---|---|
| `person_linkedin_url` (the `--id-column`) | `person_linkedin_url`: match key; update only, never insert |
| `email` | `email` (`citext`, unique where present) |
| `email_mx_provider` | `email_mx_provider` |
| `email_enriched_at` | `email_enriched_at` (when the search finished, found or not) |
| `email_search_id` | `email_search_id` |
| — | `email_status`: computed by the database: null = never searched · `found` · `not_found` |
| — | `email_validation` / `email_validation_at`: filled later by a separate validation tool |

Not loaded (CSV only): `email_certainty` (the provider's own confidence isn't trusted), `email_provider_status`,
`emails_found`, `raw`.

- First load `--limit 10` and let the user look in Supabase, then load the whole file.
- Re-loading is safe: unchanged rows are left alone (`unchanged` count).
- Rows whose LinkedIn URL isn't in `gtm.contacts` are **skipped**, never inserted. A CSV of outside people
  can be enriched, but it can't be loaded until those people are in `gtm.contacts` (companies first, then contacts).
- Schema: `docs/schema-contacts.md` §4, migration `004_contacts_email.sql`. No migration is needed for a run.
