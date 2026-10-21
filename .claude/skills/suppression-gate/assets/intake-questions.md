# Intake questions (ask in plain English, one group at a time)

## 1. Level
"Should we suppress **whole companies** (anyone at a customer, competitor, open deal… is off the list), or
only **specific people** the CRM knows about (others at those companies stay)?"
- whole companies → `--level domain` (default, recommended before contact/email spend)
- specific people → `--level contact`. Check first: **does the lead list have emails?** If not, stop.
  Contact level matches on email only.

## 2. Categories
"Which of these should be suppressed?" (offer all, and let them untick):

| Plain English | Flag value |
|---|---|
| Current customers | `customer` |
| Competitors | `competitor` |
| Lost deals marked "Do not recontact" | `do_not_recontact` |
| Other lost deals | `closed_lost` |
| Open deals at Lead stage | `pipeline_lead` |
| Open deals In Progress / negotiation | `pipeline_in_progress` |
| Companies we contacted recently | `recently_contacted` |
| People an SDR is talking to (email/calendar) | `in_conversation` |
| People who opted out of email (contact level only) | `opted_out` |

## 3. Time window (only if recently_contacted or in_conversation is chosen)
"How far back counts as 'recent': 90 days, 120 days, a year, or another number?" → `--days N` (default 90).
Lost deals have no time limit unless the user asks for one (`--lost-days N`).

## 4. Target (after the suppression list is downloaded)
"What should I suppress against: a CSV you have, or our Supabase list?"
- CSV → `--target-csv PATH`. Ask which column holds the domain (`--domain-column`) or, at contact level,
  the email (`--email-column`) if it isn't named `domain` / `email`.
- Supabase → `--target-supabase` (gtm.companies at domain level; gtm.contacts at contact level).

## Sign-off messages (copy the shape)

After profile: "Attio has **N domains** to suppress under these rules: [category table]. Download this list?"
After preview: "Of your **T rows**, **S would be suppressed** and **C stay clean** [category table]. Write the files?"
