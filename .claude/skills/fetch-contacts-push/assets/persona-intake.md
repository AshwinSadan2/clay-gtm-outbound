# Persona intake

## Pulling the persona from a brief

In a brief laid out like `docs/BRIEF.md`, the persona is in **§2c Persona: People Criteria**:
"Target job titles" (often already a tiered cascade), "Location" and "Exclusions at the people level".
Turn each tier into one `--tier` and each exclusion into `--exclude-title`.

## Asking when there's no brief

| Ask the user | Becomes |
|---|---|
| Who do you want to reach at each company (job titles)? | the titles |
| If that person isn't there, who's next best? And after that? | more `--tier`s, in order → cascade mode |
| Any titles to avoid (assistants, interns, a department)? | `--exclude-title` |
| Should the person be in a particular country, or anywhere? | `--location` (default `WORLD`) |

**Choosing the mode:** if the user gives a fallback order, use cascade mode (`--tier`). If they give one
designation or one list with no order ("Heads of Partnerships"), use single-title mode (`--title`).
Don't push a cascade on a user who doesn't have one.

## Turning plain English into title phrases

"VP of Marketing" → list every variant Blitz won't infer:
`"VP Marketing" "Vice President Marketing" "SVP Marketing" "CMO" "Chief Marketing Officer"`

Drop filler words ("of", "the"): matching is by whole words in any order.
Show the user the final phrase list per tier before the dry run.
