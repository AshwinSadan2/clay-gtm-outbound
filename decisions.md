# Decisions

Settled questions. Check here before reopening one. Older decisions (Sessions 1–4) are in `docs/build-log*.md`.

## 2026-10-30: Rule-based merge variables ({ROLE}, {PS_LINE}) are deterministic Python scripts, never LLM calls
- Why: predictable, free, auditable; the owner said they must never go through an LLM.
- What we didn't pick: an LLM classifier for titles; it costs money and can give different answers for the same title.

## 2026-10-30: {ROLE} rules are passed as `--rule label=keywords` flags, with `cmo`/`chief marketing` in the marketing rule
- Why: a new campaign never edits the script; without CMO, "CMO + AI GTM" became "revenue leaders" through the word GTM.
- What we didn't pick: rules hard-coded in the script or in a config file.

## 2026-10-30: {OPENER} uses GPT-6 Luna (`gpt-6-luna`) at effort `none`
- Why: cheapest GPT-6 ($0.10/$0.50 per 1M tokens); `none` is the only effort that gives confidence (log-probabilities) and temperature.
- What we didn't pick: GPT-4o mini (the owner's original prompts; older model); Terra/Sol/Astra (10–100× the price for a one-line opener); higher effort (no confidence score).

## 2026-10-30: Two-pass opener: insight first, then compose; the writer never sees the raw bio
- Why: the owner's design; separating "what to say" from "how to say it" makes each step checkable.
- What we didn't pick: one prompt that reads the bio and writes the line.

## 2026-10-30: Prompts and their settings live only in versioned Markdown files; a version that has run is never edited
- Why: every answer traces to a prompt version and settings (`_prompt`, `_settings` columns).
- What we didn't pick: prompt text inside the Python script; editing a prompt in place.

## 2026-10-30: Contact About under 50 words → Variant B (company About)
- Why: thin bios produced weak lines; 29 of 96 contacts go to B.
- What we didn't pick: 40 words (the owner's lower bound); skipping thin-bio contacts.

## 2026-10-30: Opener prompt rules: current work, one thing (never a list), B ≤ 15 words, never start "you focus on"
- Why: the owner's review of rows 1–20 (stale jobs, lists, long B lines, repeated openings).
- What we didn't pick: fixing these after the fact with a cleanup step.

## 2026-10-30: The script runs ONE prompt per run; pipelines are chained through CSV columns
- Why: the owner: future pipelines may have 4–5 stages, and the script must not care which stage it is.
- What we didn't pick: the first two-stage-only `openai_opener.py` (replaced).

## 2026-10-30: Concurrency default 25
- Why: the owner's choice; Luna allows 5,000 requests/min, so 25 is safe and fast (96 rows in about a minute).
- What we didn't pick: lower defaults (slower, no benefit at this size).

## 2026-10-30: Checks flag, never fix; a doubled greeting is a hard fail (`--fail-on greeting`)
- Why: a second "Hey Name," visibly breaks the email; other issues need a human eye.
- What we didn't pick: auto-rewriting flagged lines; hard-failing every check (would burn retries on style issues).

## 2026-10-30: Prompt testing on a separate sample sheet growing 10 → 20 → 30; full runs only on the live sheet
- Why: the owner's choice: like-for-like comparison plus 10 fresh rows each round.
- What we didn't pick: testing on the live sheet; re-testing on the same fixed 10 rows.

## 2026-10-30: Scaling asks "run now vs OpenAI Batch (≈50% cheaper, ≤24h)"; Batch mode is built later
- Why: the owner: offer it later; at 96 rows the saving is about a cent.
- What we didn't pick: building Batch mode now.

## 2026-10-30: Skill named `variable-llm-pipeline`; prompts in `docs/prompts/<variable>/`
- Why: the owner picked the name; prompts are campaign docs, so they live in `docs/`.
- What we didn't pick: prompts inside the skill folder; the owner's original `docs/Prompts/` (capital P).
