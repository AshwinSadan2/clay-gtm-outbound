# Company filter intake

Use this when there's no new brief, or the brief leaves a filter open. Ask in plain English, one
group at a time, and offer examples. Record each answer next to the flag it becomes.

| Ask the user | Becomes | Example answer → flag |
|---|---|---|
| Which industry or industries are you targeting? | `--industry` (exact strings from `references/blitz-industries.md`) | "B2B software" → `--industry "Software Development"` |
| Any words the company should be known for (product type, category)? | `--keyword` | "SaaS" → `--keyword SaaS` |
| How big should the companies be (number of employees)? | `--employee-range` | "50 to 200" → `--employee-range 51-200` |
| Which countries should they be headquartered in? | `--country` | "US and Canada" → `--country US --country CA` |
| How many companies do you want in total? | `--limit` | "300" → `--limit 300` |

## Pulling filters from a brief

In a brief laid out like `docs/BRIEF.md`, the filters are in **§2b ICP: Company Criteria**:
"Industry to target", "Company size", "Geography" and "Exclusions". The target count is usually in
the pull plan or `docs/CONTEXT.md` ("Target list"). Quote the brief line next to each flag when you
show the user the request.

## When the user is unsure: exploratory run

Run `--probe` on 2–4 candidate filter sets (1 record each, nothing saved). Show the totals side by
side, then let the user pick:

| Option | Filters | Total matching | Example company |
|---|---|---|---|
| A | Software Development · 51-200 · US | 9,800 | … |
| B | A + keyword SaaS | 2,100 | … |

Say the cost before each probe round ("3 probes = 3 records").
