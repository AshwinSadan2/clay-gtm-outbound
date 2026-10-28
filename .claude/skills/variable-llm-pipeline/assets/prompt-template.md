# Stage <N> — <Job> (<what this call produces>) · v1

**v1 (<YYYY-MM-DD>):** first version. <One line per later version: what changed and which review prompted it.>

**Job of this call:** <one or two sentences: what goes in, what comes out, and what this call must NOT do>.

**Model:** GPT-6 Luna (`gpt-6-luna`).

**Output field:** `<field>`

**Effort:** none

**Max output tokens:** 1000

**Variants:** <A = the rich-data path, from {{<column>}} · B = the fallback when <column> is under N words, from {{<other column>}}>.
Routed by the run flags `--variant-when "A:<column>>=N" --variant-default B`.

**`{{variables}}`** are substituted by the script from the input CSV's columns of the same name
(<this campaign's input file>). <List any --var mappings, e.g. {{angle}} ← column insight.>

---

## Variant A — MAIN (<what it works from>)

### System

You are <identity: one line, who you are and what this call produces>.

Rules:
- <The one job, stated positively.>
- <Hard rule, testable: length, sentence count.>
- <What never to do, with exact phrases to avoid.>
- <Formatting rules from the brief, word for word.>
- <Honest way out if the input has nothing useful.>
- Output ONLY the <thing>. <No greeting / no preamble / no quotes>.

### User

<FIXED CONTEXT, same every run: campaign facts, the template the output lands in.>

THIS <PROSPECT / ROW>:
- <Label>: {{<column>}}
- <Source text>:
"""
{{<column>}}
"""

WORKED EXAMPLE (copy the shape, not the words):
  <Invented input → the desired output.>

<One-line ask that repeats the single job.>

---

## Variant B — FALLBACK (<what it works from>)

### System

<Same structure. Say plainly what is missing and what it uses instead, so it does not pretend to know more.>

### User

<Same structure, using the fallback columns.>
