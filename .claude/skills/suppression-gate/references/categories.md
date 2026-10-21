# Suppression categories, levels and matching

## Levels (`--level`, ask every run)

| Level | What gets suppressed | Matches on | Use when |
|---|---|---|---|
| `domain` | The whole company: every row with its domain | company domain (`www.`, `http(s)://` and paths stripped) | Default. Before any contact/email spend on a company list. |
| `contact` | Only people Attio holds who hit a category. Others at the same company stay. | **email only, on both sides**. Never LinkedIn URL. | The lead list already has emails, and the user still wants other people at those companies |

**Contact level never runs without emails.** `attio_suppress.py` refuses a target with no email column or no emails,
and puts rows with a blank email in `<target>_unchecked_<date>.csv`, never in clean. `gtm.contacts` has no email
column until the email-enrichment step, so contact level against Supabase is refused today. That's expected.

## Categories (`--categories`, or `all`)

| Category | Attio signal | How long | Domain level | Contact level |
|---|---|---|---|---|
| `customer` | company `account_type` = Customer (every customer has a Won deal) | no limit | ✓ | people at that company |
| `competitor` | company `account_type` = Competitor | no limit | ✓ | people at that company |
| `do_not_recontact` | Lost deal with `lost_reason` = "Do not recontact" | no limit | ✓ | people on that deal |
| `closed_lost` | Lost deal, any other reason | no limit (Attio has no close date); `--lost-days N` to limit | ✓ | people on that deal |
| `pipeline_lead` | open deal in stage Lead | while open | ✓ | people on that deal |
| `pipeline_in_progress` | open deal in stage In Progress | while open | ✓ | people on that deal |
| `recently_contacted` | company `last_contacted` within `--days` | `--days` (default 90) | ✓ | people at that company |
| `in_conversation` | a person's last email/calendar interaction within `--days` | `--days` (default 90) | the person's **whole company** | that person |
| `opted_out` | person `email_opt_out`, or on the Newsletter Unsubscribes list | no limit | n/a | ✓ |

- `all` at domain level quietly skips `opted_out`. Naming `opted_out` explicitly at domain level is an error.
- **Inheritance (agreed):** at contact level a person inherits their company's customer, competitor and
  recently-contacted status. In today's data that's 31 people, all at customer companies, and 30 are on the Won deal.
- `in_conversation` at domain level holds the whole company: if an SDR is talking to someone there, no company-level outbound.
- `--days` is one window for both dated categories. Offer 90 (default), 120 or 365, or any whole number.

## Output columns

`suppression_attio_domain_<date>.csv`: domain, company_name, suppression_reason (all hits, `; `-joined),
suppress_until (blank = no end date or while open), account_type, deal_stage, stage_since, last_contacted,
last_interaction, lost_reason, deal_value_usd, deal_count, deal_owner_id, attio_company_id, pulled_on.

`suppression_attio_contact_<date>.csv`: linkedin_url, email, full_name, job_title, company_domain, company_name,
then the same reason/deal columns, attio_person_id, pulled_on.

`<target>_suppressed_<date>.csv` = the target's own columns + suppression_reason + suppress_until.
`<target>_clean_<date>.csv` = the target's rows that didn't match, columns unchanged.
