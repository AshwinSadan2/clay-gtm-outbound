# Tech distiller — <Client> (<campaign>, <YYYY-MM-DD>)

<!-- Copy to docs/<client>-tech-distiller.md and fill in from the conversation. Claude writes this; the user
reviews it. Keep the "# Tech distiller — " title and the "## Allowlist" table format exactly: the config step
(distill_tech_stack.py config) reads them. Model: references/clay-tech-distiller.md. -->

What <Client> sells, in one or two sentences, and why a detected tool matters for its pitch. Drawn from the universe
in `docs/clay-relevant-tech-providers.md` (or the client's own equivalent).

## Decisions

| Point | Decision |
|---|---|
| Types allowed | <e.g. CRM · Ad pixel>. Nothing else |
| <type> | <what counts, what doesn't (e.g. "email sequencers only, no chat tools")> |
| Exclusions | <tools that look relevant but aren't (e.g. Google AdSense = they sell ads)> |
| Ranking | <Type A 1 · Type B 2 · ...>, confirmed by the user on <date> |
| Relation | corresponding = <client> plugs into / replaces it · adjacent = related signal of fit |

## Allowlist

Tool = the exact name the detection API returns (case-insensitive). Rank = the type's priority (1 = highest, the
same for every tool of a type). Relation = corresponding / adjacent. A tool belongs to one type only.

| Rank | Type | Tool | Relation |
|---|---|---|---|
| 1 | <Type A> | <Tool> | corresponding |
| 2 | <Type B> | <Tool> | adjacent |
