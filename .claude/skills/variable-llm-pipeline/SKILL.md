---
name: variable-llm-pipeline
description: Fill a CSV column that needs judgment (e.g. a personalised {OPENER}) with OpenAI GPT-6 Luna through chained, versioned Markdown prompt files, one prompt per run. Gets the CSV (or exports it from Supabase), writes the prompts with the user, samples on a separate sheet (1 → 10 → 20…) until a version is agreed, then scales after a cost choice. Use for AI-written or AI-judged merge variables. Never for rule-based variables, which are Python scripts.
---

# Variable LLM pipeline (CSV → prompt stages → answer columns)

Writes one CSV column per stage with OpenAI. Every prompt lives in a versioned Markdown file. The script
(`scripts/openai_stage.py`) runs one prompt file per run and knows nothing about stages: **Claude designs the
pipeline**, and each later prompt reads the columns earlier runs wrote. Nothing is sent to prospects, and
nothing goes to Supabase.

Everything runs from the project folder, reading its `.env` (see `.env.template` in this skill) and writing
to its `data/` and `logs/`.

```bash
S=.claude/skills/variable-llm-pipeline/scripts/openai_stage.py
PY=.venv/bin/python
```

The shell is zsh: pass flags as an array (`F=(...)`, `"${F[@]}"`), never as one `$FLAGS` string.

The user is not a developer. Explain in plain English, show results as short tables, and make the technical
calls yourself. The variable's purpose, the prompts' wording, every gate and the spend are theirs.

**References:**
- `references/prompt-writing-guide.md`: how to write the prompt files. **Read it before writing any.**
- `references/run-and-check.md`: flags, output columns, the worked opener pipeline, how to profile a run.
- `references/supabase-export.md`: writing a one-off read-only export when there is no CSV.
- `references/openai-api-reference.md`: API facts (Responses API, models, prices, limits, errors).
- `assets/prompt-template.md`: the skeleton every new prompt file starts from.

**Worked example:** `docs/prompts/opener/`, the `{OPENER}` pipeline. Stage 1 insight v2 + stage 2 compose v3
are the current versions; v1 and v2 show what changed and why.

## Step 0: Is this an LLM job? (free)

Ask what the variable is and where it lands (paste the template line it fills).
- **Rule-based** (a lookup, a mapping, an if/else table, e.g. `{ROLE}` from the title or `{PS_LINE}` from the
  tech type): **stop.** It's a deterministic Python script with its rules as flags, never an LLM call. Say so,
  and offer to write that instead.
- **Needs judgment** (read free text, choose, write): continue.

## Step 1: Preflight (free)

1. **Check `.env`, masked first.** Run `sed -E 's/[A-Za-z0-9]/x/g' .env` **as its own command**, and read it
   before anything else.
   - Every line must be `KEY=value`. If one isn't, stop and ask.
   - Then confirm `OPENAI_API_KEY` is filled in (name and length only).
   - If it's missing, add the empty name to `.env` and `.env.template`, and the user pastes the key.
     **Never ask for it in chat.**
2. **Probe** (once the first prompt file exists): `$PY $S --probe "${F[@]}"` must show **key OK**, the model
   **available**, and a price.

## Step 2: The input CSV

Ask: **"Which CSV should this run on?"**

- **A CSV:** get the path. Read only its header and row count. Map the columns the prompts will need; the id
  column must be unique per row.
- **No CSV:** ask **"Is the data in Supabase?"** If yes, write a one-off read-only export following
  `references/supabase-export.md`:
  1. Show the SQL.
  2. Run it from the scratchpad into `data/processed/<what>_supabase_<today>.csv`.
  3. Report the row count and how full each needed column is.
- **Neither:** stop. The data has to be built first (the list-building and enrichment skills).

Never edit a file in `data/raw/`. Results are written into the working CSV in `data/processed/`. If the user
wants the source untouched, use `--output` to write a copy.

## Step 3: Design the pipeline (with the user)

Agree, in a short table:
1. **The output:** what the final column holds, where it lands, and the brief's rules for it (length, tone,
   banned punctuation).
2. **Stages:** default to two, extract → write (`references/prompt-writing-guide.md` §2). Add a stage only for
   a separate job (e.g. a judge).
3. **Inputs per stage:** which columns, and how full they are. **Variants** for thin data, with a word-count
   threshold the user picks.
4. **Checks:**
   - which flags each stage runs
   - word limits per variant
   - which checks are hard fails: e.g. `greeting`, for anything that would visibly break the email
5. **Exclusions:** rows to skip (`--skip-column`, e.g. competitors marked `exclude_reason`).

## Step 4: Write the prompt files (sign-off)

1. **Read before writing.** Read `references/prompt-writing-guide.md` in full, the template, and the opener
   files.
2. **Write** `docs/prompts/<variable>/stage1_<job>_v1.md`, `stage2_<job>_v1.md`… from
   `assets/prompt-template.md`. Settings go in the header:
   - Model `gpt-6-luna`
   - Effort `none`
   - Output field
   - Max output tokens
3. **Self-check** against the guide's §11 checklist. Show the user each file (or the System/User blocks), and
   ask: **"Are these prompts right?"**
4. If the user hands over prompt files, read them in full, flag gaps against the guide and the CSV columns,
   and fix only what they approve.

## Step 5: Sample sheet → dry run → 1 row → 10 rows

All prompt testing runs on a **separate sample sheet**, never on the live sheet. Make it a copy of the input:
`data/processed/<what>_sample_<today>.csv`, used as `--input` for every test run. Below, `F_n` = the flags for
stage n (`references/run-and-check.md` §1 and §3).

1. **Dry run.** `$PY $S "${F_1[@]}" --limit 1 --dry-run`. Read the filled prompt and check every `{{variable}}`
   filled. If there are two variants, dry-run one row of each (`--ids`).
2. **One row.** Run stage 1 with `--limit 1`, then each later stage. Show:
   - each stage's answer
   - tokens, cost and confidence
   - flags

   Ask: **"Look right? Next is 10 rows."**
3. **Ten rows.** Run every stage with `--resume --limit 9`, then profile the run (`run-and-check.md` §4).
   Show all 10 answers in a table, plus the smells from the guide's §10.

## Step 6: Iterate (sample before scaling)

Each round:
1. **New version.** Copy the file to `v<K+1>` and add a changelog line. Never edit a version that has run.
2. **Grow the sample.** A new version counts as not done for every row, so run it with `--limit` 10 rows
   larger than the last round: v1 on 10, v2 on 20, v3 on 30… The rows already seen give a like-for-like
   comparison; the 10 new rows catch problems the old rows hid. Only the stages that changed need to run;
   later stages just read the new column.
3. **Compare.** Show v<K> vs v<K+1> on the shared rows (the old answers are in the raw JSONL), then the new
   rows. Include average words, confidence and flags.

Repeat until the user and you agree the version is good.

## Step 7: Scale (sign-off on how)

1. **Extrapolate the cost** from the sample: average `cost_usd_total` per row × rows on the live sheet.
2. Ask: **"Run all N rows now for ≈ $X (≈ Y min), or use OpenAI's Batch API: about 50% cheaper (≈ $X/2),
   results within 24 hours?"**
   - **Now:** run each stage on the live sheet with the agreed versions, `--resume`, and `--max-cost` at
     about 2× the estimate.
     - For long runs, run in the background, and don't poll.
     - Concurrency defaults to 25.
   - **Batch:** not built into the script yet. Say so, and offer to add a batch mode first: submit a JSONL,
     save the batch id, collect the results, then merge them into the sheet. Read the Batch docs before
     building it.
3. **Final summary:**
   - rows done / total, failures (with the reason)
   - total cost
   - variant split, and confidence (average, lowest 10)
   - every flagged row in full, and which rows to fix by hand

The live sheet is the result. It feeds the copy or merge step, which needs the owner's go-ahead before anything
is sent.

## Rules

- **Gate order:** design → prompts → probe → dry run → 1 → 10 → iterate (10, 20, 30…) → scale choice → full
  run, with a sign-off at each arrow. Never jump from a sample to the full list without the scale question.
- **Tests on the sample sheet, the full run on the live sheet.** Never test a prompt version on the live sheet.
- **No prompt text in code.** Prompts live only in `docs/prompts/<variable>/*_vN.md`, and the script reads
  them. **Never edit the script for a campaign**: every value is a flag or a prompt-file line.
- **Never edit a prompt version that has run.** A new version re-runs every row: that's how results stay
  traceable (`<column>_prompt`, `<column>_settings`).
- **Rule-based variables are never LLM calls** (Step 0).
- **Secrets:** never print `.env` values, request headers or the key.
- **Personal data:** the CSV and `data/raw/*.jsonl` hold personal data. They stay in `data/` (gitignored), and
  no rows are pasted into prompts beyond the row being processed.
- **Stop on billing errors.** On `insufficient_quota` the run stops by itself: tell the user. Never retry it.
