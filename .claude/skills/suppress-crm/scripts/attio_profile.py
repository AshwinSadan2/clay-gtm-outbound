#!/usr/bin/env python3
"""Stage 1 of 3: profile the Attio CRM for suppression. Read-only; writes nothing but the run log.

Counts each chosen category. Categories with few entries list them (companies by name and domain,
people by job title and company); big ones show counts only (--detail-threshold).

Usage (from the project folder):
    .venv/bin/python .claude/skills/suppress-crm/scripts/attio_profile.py \
        --level domain --categories all --days 90
    .venv/bin/python .claude/skills/suppress-crm/scripts/attio_profile.py \
        --level contact --categories customer pipeline_lead pipeline_in_progress opted_out --days 120

Next stage: attio_download.py with the same flags.
"""
import attio_common as ac


def main():
    parser = ac.base_parser(__doc__ + "\n" + ac.__doc__.split("\n\n", 1)[1])
    ac.add_category_args(parser)
    args = ac.setup(parser)
    rows, crm = ac.classify(args)
    print(f"CRM: {crm['companies']} companies, {crm['deals']} deals, {crm['people']} people "
          f"({crm['people_with_interaction']} with an email/calendar interaction on record) | {ac.describe(args)}")
    if "in_conversation" in args.categories and not crm["people_with_interaction"]:
        print("  note: no person has an interaction on record (mailbox/calendar not synced to Attio), "
              "so in_conversation can't match anyone yet")
    ac.report(rows, args.detail_threshold, "Suppression list", args.level)


if __name__ == "__main__":
    main()
