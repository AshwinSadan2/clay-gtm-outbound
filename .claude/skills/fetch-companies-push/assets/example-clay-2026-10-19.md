# Worked example: the Clay run (2026-10-19)

Brief: Clay's outbound to US SaaS companies with 51–200 employees (`docs/BRIEF.md` §2b).
Approved request doc: `docs/company-search-request.md`.

```bash
S=.claude/skills/fetch-companies-push/scripts
F='--industry "Software Development" --keyword SaaS --employee-range 51-200 --country US'

eval python3 $S/blitz_company_search.py $F --limit 300 --dry-run              # request for sign-off
eval python3 $S/blitz_company_search.py $F --limit 10 --page-size 10          # sample: 10 records
eval python3 $S/blitz_company_search.py $F --limit 290 --resume               # scale to 300 total
.venv/bin/python $S/data.py load-companies data/processed/companies_blitz_2026-10-19.csv --limit 5   # sample push
.venv/bin/python $S/data.py load-companies data/processed/companies_blitz_2026-10-19.csv             # full push
.venv/bin/python $S/data.py stats
```

Outcome: 300 companies pulled (300 records) and loaded into `gtm.companies`.
Lesson: without `--keyword SaaS`, the sample showed tech-media brands (TechCrunch-style) leaking in.
