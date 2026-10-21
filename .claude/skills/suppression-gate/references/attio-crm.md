# The Attio CRM: what the scripts read and its known gaps

Workspace: **Bootprint-CEM**. Access is read-only: the key can't create, change or delete anything.
API: `https://api.attio.com/v2`, `Authorization: Bearer <ATTIO_API_KEY>`. Record lists use `POST .../query`,
which is a read-only call despite the name. Reads are free, so there's no record budget like Blitz has.

## What's read

| Object / list | Fields used |
|---|---|
| companies | `domains` (match key), `name`, `account_type` (Prospect / Customer / Competitor), `last_contacted`, `last_interaction` |
| deals | `stage` (Lead / In Progress / Won 🎉 / Lost) + its `active_from`, `lost_reason`, `value`, `owner`, `associated_company`, `associated_people` |
| people | `email_addresses`, `linkedin`, `name`, `job_title`, `company`, `email_opt_out`, `last_interaction` |
| list `newsletter_unsubscribes` | entries' `parent_record_id` (people) |

The field and stage names are fixed at the top of `scripts/attio_common.py`, because they describe this
workspace's setup, not a campaign. If the CRM is reconfigured (e.g. a stage is renamed), update them there.

## Known gaps (tell the user when relevant)

- **Import dates.** Every company, person and deal was created on 2026-08-10 (a bulk import), and every
  deal stage is dated then too. `stage_since` therefore can't show when a deal was won or lost, which is
  why closed-lost has no time limit by default.
- **No interaction data yet.** `last_interaction` (email + calendar) is empty for all records, because no
  mailbox or calendar is synced to Attio. `in_conversation` works, but matches nobody until it is. The
  profile stage prints a note when that's the case.
- **Deal owner names** need the extra `user_management:read` scope, so only `deal_owner_id` is filled.
- **Notes, tasks, email threads, meetings** aren't readable with the current scopes.

## Data quality (as profiled on 2026-10-21)

72 companies (each with exactly one domain, no duplicates, no `www.`) · 75 people (all emails on the company's
domain, 1 with no company) · 25 deals (10 Won, 7 Lost, 6 In Progress, 2 Lead). The Customers list = account_type
Customer = companies with a Won deal. The Active Pipeline list = open-stage deals. Unsubscribes list = email_opt_out
flag. The lists and fields agree exactly, so the scripts read the fields.

## Failures

A failed call is logged to `logs/attio_suppression_errors.log` (time, HTTP code, message, request) and the stage
stops with nothing written. 429 / 500 / 503 are retried. There's no resume: a pull takes seconds and costs nothing,
and a half-old, half-new snapshot would be worse than re-running.
