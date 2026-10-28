# Running the email validation and loading it

How `debounce_email_validate.py` behaves, how to size the gates, and how results map to `gtm.contacts`.
Debounce API facts (endpoints, limits, result codes, errors): `debounce-api-reference.md` in this folder.

---

## 1. Inputs

| Source | Flags | Notes |
|---|---|---|
| Email-enrichment results | `--input data/processed/contacts_email_enriched_<date>.csv --email-column email --id-column person_linkedin_url` | Rows with no email are skipped (not charged) |
| A CSV the user gives | Their email and unique id columns | For a Supabase load the id must be the LinkedIn URL |

## 2. Flags

| Flag | Required | Meaning |
|---|---|---|
| `--input FILE` | yes | CSV holding the emails |
| `--output FILE` | yes | Results CSV, appended each run: `data/processed/contacts_email_validated_<date>.csv` |
| `--email-column` · `--id-column` | yes | Input column names |
| `--limit N` | no | Validate at most N **new** emails this run (gate size) |
| `--resume` | after the first run | Continue; never re-validates (never re-pays) a done email. Required once a run has started |
| `--dry-run` | no | Print the emails; no calls, no credits |
| `--probe` | no | Key check + credit balance. Free |
| `--concurrency` | no | Calls at once, default 3, max 5 (Debounce limit) |
| `--env PATH` | no | `.env` stored elsewhere |

## 3. Files written

| File | What |
|---|---|
| `--output` | Input columns + `email_validation`, `email_validation_at`, `email_validation_reason`, `email_validation_code`, `email_role`, `email_free`, `email_send_transactional`, `email_did_you_mean`, `validation_raw` |
| `data/raw/<output name>.jsonl` | One line per answer, Debounce's response untouched |
| `data/raw/<output name>.state.json` | People done: the resume point (and the input file it belongs to) |
| `logs/debounce_email_validate.log` · `_errors.log` | Run log · failed calls (time, HTTP code, message, the email; never the key) |

**Credit guard:** before calling, the script reads the balance and validates only as many emails as it covers.
On HTTP 402 it stops starting calls, saves, and exits; `--resume` after a top-up.

## 4. Gates

| Gate | Command adds | User sees |
|---|---|---|
| Dry run | `--limit 5 --dry-run` | The 5 emails |
| Sample | `--limit 5` | All 5 rows: result + reason |
| Second gate | `--resume --limit 95` | Profile of the 100 |
| Scale | `--resume` (batches of `--limit 50000` when huge) | Summary after each batch |

Speed: about 100 emails a minute at 3 at once.

## 5. What to check at each gate

- **Results × reasons.** Benchmark (2026-10-27, 100 Icypeas emails): 63 Safe · 33 Risky (Accept All) · 2 Unknown · 2 Invalid.
- **Invalid and Unknown:** list every one (email, finder certainty). Invalid = never send.
- **Risky / Accept All share.** A high share is normal for catch-all company domains; it's a sending decision, not an error.
- **`did_you_mean`:** mention the count, but never apply it (wrong for `.ai` / `.io` domains).
- **Role / free emails:** should be 0 for person@company emails.
- **Credits:** compare the balance before and after with the emails checked. Unknown results appeared uncharged.

## 6. Loading to Supabase (after the user's go-ahead)

`data.py load-validation FILE --id-column person_linkedin_url [--limit 10]`

| CSV column | `gtm.contacts` column |
|---|---|
| `person_linkedin_url` (the `--id-column`) | `person_linkedin_url`: match key; update only, never insert |
| `email` | must equal the stored `email`, or the row is skipped ("email differs") |
| `email_validation` | `email_validation` (Debounce `result`) |
| `email_validation_at` | `email_validation_at` |

Not loaded (CSV only): reason, code, role, free, send_transactional, did_you_mean, `validation_raw`.
Re-loading is safe: unchanged rows are left alone. Schema: `docs/schema-contacts.md` §4, migration `004_contacts_email.sql`.
