# Tech-stack skill: agreed flow (DRAFT, 2026-10-27)

Captured from the owner's outline so it isn't lost. **Not built yet**: revisit once the scripts are
parameterized, then turn this into `SKILL.md` (under 200 lines) + references. Items marked *(assumption)* were
proposed by Claude and not yet confirmed by the owner.

---

## Flow

```
1. Input
   ├─ User gives a CSV of companies
   └─ No CSV → build a Supabase export from the user's criteria (e.g. export-companies --email-validation)
          │
          ▼
2. First-row check: scan 1 company (1 call). Must pass before anything else.
          │
          ▼
3. 10-row scale: +9 companies → 10 scanned.
          │
          ▼
4. Client: read the distiller doc (references/clay-relevant-tech-providers.md), then ask
   "Are you building this for Clay or another client?"
   ├─ Clay → use the Clay distiller doc as is
   └─ Other client → look the client up (web) and understand what they sell
         └─ not enough public info → ask the user targeted questions, built from the distiller doc
            and the tech actually found in the 10 rows
          │
          ▼
5. Map the found tech to the client:
   • Corresponding tech: tools the client plugs into / replaces (direct hooks)
   • Adjacent tech: not a direct match, but a related signal of fit
          │
          ▼
6. Build the client's distiller doc (types → tools, corresponding vs adjacent).
   Ask the user to RANK the signal types: not all signals carry the same priority.
          │
          ▼
7. Run the distiller on the 10 rows → hit rate (companies with ≥1 signal / 10).
          │
          ▼
8. Run 90 more → 100 rows. Distil again → hit rate at 100.
   Extrapolate to the full list and show it, e.g. 35/100 → ~350 of 1,000 (give a range, ±a few).
          │
          ▼
9. Complete the run, however long the CSV is.
          │
          ▼
10. Distil the full CSV → the campaign's distilled CSV.
```

## Already decided (this session)

| Topic | Decision |
|---|---|
| Supabase | Full stack only: `gtm.companies.tech_stack` (jsonb type → tools map) + `tech_enriched_at` (set for every attempted company, failures included). Migration 005 |
| Distilled signal | **Never in Supabase.** Transient, per client: rebuilt as a CSV whenever needed (`distill_tech_stack.py`) |
| Full results CSV | `data/processed/tech_stack_companies_<date>.csv`, appended each run, raw JSON kept in `tech_raw`. It is the source for the Supabase push |
| Distilled CSV | `data/processed/distilled_tech_stack_companies_<date>.csv`: one row per company, `tech_tool` + `tech_type` |
| Clay types (2026-10-27) | CRM · Sequencer (email outreach tools only; no general marketing automation, no chat) · Ad pixel. HubSpot CMS Hub not counted as CRM |
| Provider | DetectZeStack via RapidAPI (`docs/detectzestack-api-reference.md`). Free plan: 100 calls/month, every call counts |

## Open points *(assumptions to confirm when building)*

| # | Point | Proposed |
|---|---|---|
| 1 | Sign-off between steps | Wait for the user's OK at every arrow, like the other skills *(assumption)* |
| 2 | Where a client's distiller doc lives | `docs/<client>-tech-distiller.md`; the Clay doc stays in `references/` as the worked example *(assumption)* |
| 3 | Corresponding vs adjacent in the output | Both kept and labelled in the distilled CSV *(assumption)* |
| 4 | How the ranking is used | Distilled CSV gets the top-ranked signal per company + all matches *(assumption)* |
| 5 | Supabase push | Load 10 rows → user checks → load the rest, after the run *(assumption)* |
| 6 | Large lists | Batches (e.g. 50,000) with a "continue?" between, quota-checked against the plan *(assumption)* |
| 7 | Quota | Before step 9, compare rows left with the plan's remaining calls; ask to upgrade if short *(assumption)* |
