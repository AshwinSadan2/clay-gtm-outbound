# Writing prompt files for the LLM pipeline (GPT-6 Luna)

Read this before writing or changing any prompt file. It has three sources:
- OpenAI's docs (prompt engineering, GPT-6 / latest-model guide, structured outputs, reasoning), read 2026-10-28
- the file format `scripts/openai_stage.py` expects
- what we learned taking the `{OPENER}` from v1 to v3 (`docs/prompts/opener/`, the worked example)

Start every new file from `assets/prompt-template.md`.

## 1. First: should this be an LLM call at all?

Only variables that need **judgment** (reading free text, choosing, writing) go through the LLM. A variable
that is a lookup or a rule (a title mapped to a role, a tech type mapped to a P.S. line, a date format) is a
deterministic Python script with its rules as flags, never a prompt. If you can write the rule as an if/else
table, it is not an LLM job.

## 2. Split the job into stages

One call = one small, literal job. OpenAI describes Luna as built for "focused, high-volume tasks". GPT models
behave like "a junior coworker" who needs explicit instructions for a specific output, so a call that does
two jobs at once does both badly.

| Pattern | Stages | When |
|---|---|---|
| Extract → write | 1. find the insight in the source text · 2. write the line from the insight | Personalised copy (the `{OPENER}`) |
| Classify | 1 stage with a closed answer set | Tagging, scoring, routing |
| Extract → judge → write | 3 stages | When a bad insight must be filtered out before writing |

- **Each stage is its own prompt file and its own run.** A later stage reads an earlier stage's column as a
  `{{variable}}` (or maps it with `--var name=column`).
- **The writing stage never sees the raw source.** Stage 2 of the opener gets only the angle. This stops it
  from copying the bio.
- **Keep an intermediate stage's output labelled and plain** (e.g. `Observation: … Likely pain: …`). That
  gives the next stage clean, separable parts and gives a human something to review.

## 3. Variants: route by how much data the row has

- A file can hold several `## Variant X` sections. The script picks one per row with `--variant-when` (word
  count of a column) and `--variant-default`.
- Write a fallback variant for thin data (opener: contact About under 50 words → the company About instead).
- Routing must be deterministic. Write the same `--variant-when` flags for every stage of a pipeline, so the
  stages agree.
- Each variant names what it is working from and why ("This prospect has no usable personal About, so you read
  their COMPANY's About"), so the model does not pretend to know the person.

## 4. Anatomy of one prompt section

| Block | Goes to the API as | Holds | OpenAI guidance |
|---|---|---|---|
| `### System` | `instructions` (outranks the input) | Identity (one line: who you are, what this call produces) → rules → output format | "Identity, Instructions, Examples, Context." Rules and business logic go here: the "function definition". |
| `### User` | `input` | Fixed context (campaign facts) → the row's data, delimited → examples → the final ask in one line | Context "usually best positioned near the end". The row is the "arguments". |

- **Order inside User:** static text first (campaign context, fixed template), row data last. OpenAI: put
  content you reuse on every request at the beginning of the prompt, so the cache can reuse it.
- **Delimit the data.** Use `"""` (as in the opener files) or XML tags (`<about>…</about>`), so the model
  never confuses the bio with an instruction.
- **Show where the output lands.** The compose prompt pastes the full fixed Email 1 with `«YOUR OPENER»` and
  says everything else is fixed. The model writes to fit the next line instead of repeating it.
- **End with a one-line ask** that repeats the single job: "Write {{first_name}}'s opener. One sentence. The
  opener only."

## 5. Writing rules the model follows

- **Be explicit and literal.** GPT-6 follows instructions closely and is "more sensitive to context", so
  conflicting rules cause odd output. Read the whole section once, looking only for contradictions.
- **Hard rules as short bullets, each one testable.** "ONE sentence. Max 15 words." beats "keep it brief".
- **Say what to do, then what never to do, with the exact phrases.** Banned words work best when they are
  named: "no evaluative praise (impressive / interesting / exciting / great)", "never start with 'you focus
  on'". The model has habits ("recurring phrases"), so ban the ones you see in the 10-row review.
- **One thing, not a list.** Ask for ONE specific thing and ban lists outright ("no X, Y, Z and W"). v1 copied
  bios as feature lists until this rule was added.
- **Current over past.** "Prefer their current company and recent work; never a past employer or a dated
  result."
- **Neutral, not flattering.** "Name the thing, don't rate it."
- **Formatting rules from the brief,** word for word (e.g. no dashes, with the allowed exception for hyphens
  inside compound words spelled out).
- **Give the model an honest way out.** If a stage may find nothing useful, tell it what to say ("If the source
  has no clear link, write 'No clear link'"). Otherwise it invents a plausible one, as Stage 1 v2 did.

## 6. Examples (few-shot)

- 1 to 3 examples, **"copy the shape, not the words"**. A single example gets copied.
- OpenAI: "show a diverse range of possible inputs with the desired outputs". Mix a rich-data row and a
  thin-data row.
- Use invented names and companies (Sam at Acme), never a real prospect.

## 7. Output format

- Every call returns structured output: `{"<Output field>": "<string>"}`, enforced with a strict JSON schema
  by the script. Declare the field in the file (`**Output field:** \`angle\``) and say in the rules: "Output
  ONLY the <thing>."
- The script blocks everything outside that field. Spending prompt words on "no preamble, no quotes" is still
  worth it, because it keeps the field itself clean.
- A refusal or a cut-off answer is caught by the script and logged; the row is retried on `--resume`.

## 8. Model settings (the file's header lines)

| Setting | Luna default here | Why |
|---|---|---|
| `**Model:**` | `gpt-6-luna` | Cheapest GPT-6 ($0.10 in / $0.50 out per 1M tokens). About $0.0001 per call at our prompt size. Try `gpt-6.1-terra` ("natural writing", 10× the price) only if Luna's writing is the bottleneck. |
| `**Effort:**` | `none` | Short literal jobs gain nothing from thinking. `none` is also the only effort that allows log-probability **confidence**, `temperature` and `top_p`: with any other effort OpenAI refuses them (HTTP 400). Astra and Sol do not accept `none`. |
| `**Temperature:**` | unset (OpenAI default 1.0) | Lower (0.3 to 0.7) for steadier, more repetitive copy; keep 1.0 for variety across a big send. Change it in a new version, not mid-run. |
| `**Max output tokens:**` | 1000 | A cap on reasoning plus answer. If it is hit, the answer is empty but still billed. One-line outputs use about 30 tokens. |

## 9. Versioning

- The file name is the version: `stage<N>_<job>_v<K>.md`, in `docs/prompts/<variable>/`.
- **Never edit a version that has run.** Copy it to `v<K+1>` and add one changelog line under the title: what
  changed and which review prompted it. Header lines that are not sent to the model (settings, notes) may be
  corrected in place.
- A new version or a changed setting counts as "not done" for every row, so the next run re-runs them all.
  Compare versions on the **same 10 rows** (`--ids`).

## 10. Review checklist (10-row gate)

Read every output, not a sample. Look for:

| Smell | Example from the opener | Fix in the next version |
|---|---|---|
| Copies the source | "you use Tableau and Power BI alongside web research and project management tools" | One-thing rule; give the writing stage only the insight |
| Lists | "pricing, quoting, rebates, chargebacks…" | "Never a list" + the `list` check |
| Stale | Past employer, "in 2021" | Current-work rule + the `dated` check |
| Same opening every time | 5 of 9 started "you focus on" | Ban the phrase, give alternatives |
| Tells them what they know | "Acme helps teams run outbound" (Variant B) | Shorter cap (15 words), who they serve |
| Breaks the template | Opener starting "Hey Estefania," | `--fail-on greeting` (hard fail) |
| Invented link | Pain made up from a thin bio | Honest "No clear link" way out + the `review` check |

Confidence (0 to 1, from log-probabilities) is a triage signal, not a grade. In the opener run, the lowest
scores were the plainest lines. Read rows under about 0.85 first.

## 11. Before the first paid call

- [ ] Every `{{variable}}` is a CSV column, or mapped with `--var`
- [ ] Each variant has a System and a User block, and the fallback says what it works from
- [ ] Rules are testable bullets, the brief's formatting rules are copied word for word, and there are no
      contradictions
- [ ] Examples are invented, varied, and labelled "copy the shape"
- [ ] Output field declared, and "output ONLY …" stated
- [ ] Settings: model, effort none (unless the job truly needs thinking), max tokens
- [ ] Dry run read in full for one row of each variant
