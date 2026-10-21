# Pushing to Supabase

All commands run from the project folder with the project virtualenv:
`.venv/bin/python .claude/skills/fetch-companies-push/scripts/data.py <command>`.
If `.venv` is missing: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`.

| Command | What it does |
|---|---|
| `load-companies FILE [--limit N]` | Upsert a companies CSV into `gtm.companies` (key: `domain`) |
| `load-contacts FILE [--limit N]` | Upsert a contacts CSV into `gtm.contacts` (key: `person_linkedin_url`) |
| `load --companies FILE --contacts FILE` | Both, always companies first |
| `export-companies [--all]` | Write `data/processed/companies_supabase_<today>.csv` (companies with no contact; `--all` = every company) |
| `stats` | Row counts, companies without a contact, contacts by tier |
| `migrate` | Apply new files in `db/migrations/` |

## Rules

- **Companies before contacts, always.** Each contact links to its company (foreign key
  `contacts.company_domain` → `companies.domain`). A contact whose company isn't loaded is skipped,
  and the loader warns. Tell the user this order before any load.
- **Upserts are safe to re-run.** Unchanged rows are reported as `unchanged` and not rewritten.
- **`--limit N`** loads only the first N rows. Use it for a sample push (e.g. 5) before the full push.
- Bad rows go to `logs/data_errors.log` and the load carries on. Report the error count.
- Contacts with no first name are skipped (they can't get `{FIRST_NAME}`).
- Only the `gtm` schema is touched. `public` belongs to an unrelated movies project.
- **Ask the user before pushing.** Show the counts first and push only after a yes.

## Reading the result

```
companies: 300 inserted, 0 updated, 0 unchanged, 0 skipped, 0 errors
```
After every push, run `stats` and report the before → after counts.
