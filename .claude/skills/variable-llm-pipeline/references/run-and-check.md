# Running a stage and checking its results

`scripts/openai_stage.py` runs ONE prompt file over every row of a CSV: one call per row, one answer column.
It does not know about stages. A pipeline is several runs; each later prompt reads earlier columns.

```bash
S=.claude/skills/variable-llm-pipeline/scripts/openai_stage.py
PY=.venv/bin/python
```

The shell is zsh: pass flags as a bash-style array `F=(...)` and `"${F[@]}"`, never as one `$FLAGS` string.

## 1. Flags

| Group | Flag | Meaning |
|---|---|---|
| In / out | `--input` | CSV, one row per call |
| | `--prompt` | the stage's prompt file |
| | `--output` | write here instead of updating `--input` in place |
| | `--output-column` | answer column (default: the file's Output field) |
| | `--var NAME=COLUMN` | fill `{{NAME}}` from a differently named column |
| | `--id-column` | unique per row (default `person_linkedin_url`) |
| | `--raw` | raw JSONL path (default `data/raw/llm_<input>__<column>.jsonl`) |
| Rows | `--limit N` | rows this run |
| | `--ids FILE` | only these ids, one per line (same 10 rows across versions) |
| | `--skip-column COL` | skip rows where COL is filled (e.g. `exclude_reason`) |
| | `--require COL` | skip rows where COL is empty (a later stage: `--require insight`) |
| | `--resume` | skip rows done with this exact prompt version and settings |
| Variants | `--variant-when "A:about_me>=50"` | first match wins; word count of a column |
| | `--variant-default B` | when nothing matches |
| Model | `--model --effort --temperature --top-p --max-output-tokens` | override the file's settings (recorded in `_settings`) |
| | `--price IN,CACHED,OUT` | USD per 1M tokens, for a model the script has no price for |
| Checks | `--checks dash,words,list,dated,question,greeting,review` | which checks to run (default: all) |
| | `--max-words A=20 --max-words B=15` | the `words` limit, per variant or one number |
| | `--review-phrases` | an answer containing one gets `review: no clear link` |
| | `--fail-on greeting` | hard fail: new call (up to `--fail-retries`, default 2), else the cell is left empty and the row is retried on `--resume` |
| Control | `--concurrency 25` | calls in parallel (default 25; Luna allows 5,000/min) |
| | `--max-cost 0.50` | stop starting rows once this run spent this; running rows still finish, so a run can go over by up to one batch |
| | `--timeout 120 --max-tries 5` | per call; 429/500/503 retried, and `insufficient_quota` stops the run |
| | `--dry-run` | print the filled prompt, no calls |
| | `--probe` | key, model, price, variants (free) |

**Which checks fit which stage:**
- **Intermediate stage** (insight): `--checks review`. Its text is never sent, so dashes and lists don't matter.
- **Final stage** (the copy): `--checks dash,words,list,dated,question,greeting` and `--fail-on greeting`.

## 2. What a run writes

| Where | What |
|---|---|
| `<column>` | the answer |
| `<column>_variant` | prompt section used |
| `<column>_input_tokens`, `_output_tokens`, `_cost_usd` | usage and cost, all calls for the row (hard-fail retries included) |
| `<column>_confidence` | exp(mean log-probability) of the answer's own tokens, 0 to 1 (effort none only) |
| `<column>_flags` | checks that fired: flag, never fix |
| `<column>_settings`, `_prompt`, `_at` | model settings, prompt version, time |
| `cost_usd_total` | sum of every `*_cost_usd` in the row (all stages so far) |
| `data/raw/llm_<input>__<column>.jsonl` | one line per row as it arrives: full API responses. This is the resume point |
| `logs/openai_stage.log`, `logs/openai_stage_errors.log` | run log; failed calls, refusals, blocked rows |

The CSV is rewritten every 5 s (`--csv-every`) and at the end. The JSONL is written per row, so a crash loses
nothing: re-run with `--resume`.

## 3. The opener pipeline (worked example, 2026-10-28)

```bash
IN=data/processed/mailable_contacts_2026-10-28.csv
R=(--variant-when "A:about_me>=50" --variant-default B)   # + --skip-column exclude_reason once that column exists
I=(--input $IN --prompt docs/prompts/opener/stage1_insight_v2.md --output-column insight "${R[@]}" --checks review)
C=(--input $IN --prompt docs/prompts/opener/stage2_compose_v3.md --var angle=insight --require insight "${R[@]}"
   --max-words A=20 --max-words B=15 --checks dash,words,list,dated,question,greeting --fail-on greeting)
$PY $S "${I[@]}" ...    then    $PY $S "${C[@]}" ...
```

- **Cost:** 96 rows × 2 stages ≈ $0.019 on Luna.
- **Time:** about 1 minute at concurrency 25.
- **Re-running only the compose stage** on a new version re-uses the saved insights: run C again.

## 4. Profiling a run (show the user)

Read the CSV with a short script and report:
- rows done / total, failed (from the log), cost this run and `cost_usd_total` summed
- variant split
- average and lowest confidence, plus the 10 lowest rows
- flags by type, with the flagged rows listed in full
- for copy stages: word count average and max, and the most common first two words (repeated openings)

To compare versions, read both runs' JSONL, or keep the old version's column by running the new one with a
different `--output-column` (e.g. `opener_v4`), then show them side by side for the same rows.
