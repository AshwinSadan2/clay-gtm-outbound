# Handoff

## Where we are
All 96 mailable contacts have `{ROLE}` and a v3 `{OPENER}` in `data/processed/mailable_contacts_2026-10-28.csv` (local only), but the openers are in the old column layout and 10 are flagged. The generic LLM script and the `/variable-llm-pipeline` skill are built, tested and pushed. Nothing has been sent to anyone.

## Last session did
- 2026-10-28/30: built the working sheet, `role_variable.py` ({ROLE}), the two-pass {OPENER} prompts (insight v2 + compose v3 on GPT-6 Luna, $0.0186 for 96 rows), `openai_stage.py`, the `/variable-llm-pipeline` skill, and `docs/build-log-2026-10-28.md`.

## Next session does
1. Mark LeadIQ and UserGems (competitors) with `exclude_reason`; Regie.ai stays.
2. With the owner's OK: re-run insight v2 + compose v3 on the live sheet with `openai_stage.py`, `--skip-column exclude_reason`, `--fail-on greeting` (≈ $0.02), drop the old-layout opener columns, review the flagged rows.
3. `{PS_LINE}`: add Marketing Automation to Clay's distiller (`docs/clay-tech-distiller.md`), re-distil (free), build deterministic `ps_line_variable.py`.
4. Give `.claude/skills/mail-merge-variables/` a `SKILL.md` (covering {ROLE} and {PS_LINE}).
5. Later: Batch mode for `openai_stage.py`.

## Waiting on
- Owner: what was wrong with "Art's opener" and which `_v2` columns were meant (neither matches the sheet).
- Owner: go-ahead for the live-sheet re-run (step 2).
- Owner: Debounce credit top-up for the last 15 emails; rotate the Icypeas keys.
- Also carried over: centerbase.com retry, 115 never-searched contacts, name cleaning.

*Last updated: 2026-10-30*
