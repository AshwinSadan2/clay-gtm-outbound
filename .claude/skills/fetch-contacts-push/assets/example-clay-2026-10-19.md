# Worked example: the Clay cascade (2026-10-19)

Persona: the best-available marketing or RevOps leader at each US SaaS company (`docs/BRIEF.md` §2c).
Approved request doc: `docs/contact-search-request.md`. Six tiers → Waterfall ICP.

```bash
S=.claude/skills/fetch-contacts-push/scripts
python3 $S/blitz_contact_search.py \
  --companies data/processed/companies_blitz_2026-10-19.csv \
  --tier "VP Marketing" "Vice President Marketing" "SVP Marketing" "Senior Vice President Marketing" \
         "EVP Marketing" "CMO" "Chief Marketing Officer" "VP Growth" "Vice President Growth" \
         "VP Demand Generation" "VP Demand Gen" "Vice President Demand Generation" \
  --tier "Head Marketing" "Head Growth" "Head Demand Generation" "Head Demand Gen" \
  --tier "Director Marketing" "Director Growth" "Director Demand Generation" "Director Demand Gen" \
  --tier "VP Revenue Operations" "Vice President Revenue Operations" "Head Revenue Operations" \
         "Director Revenue Operations" "RevOps" "GTM Engineer" "Go To Market Engineer" \
  --tier "Founder" "CEO" "Chief Executive Officer" "[Owner]" \
  --tier "Marketing" "Growth" "Demand Generation" "Demand Gen" "Revenue Operations" \
  --exclude-title Assistant Intern Junior Coordinator Freelance Brand Communications Content PR "Social Media" \
  --tier-exclude 5 "Chief of Staff" Advisor \
  --headline-tier 6 --location WORLD \
  --limit 10          # sample; then the same command without --limit (and with --date 2026-10-19) to scale
```

Outcome: 300 companies → 292 found, 8 no-match (mostly acquired). 5 had no first name and were skipped
at push, leaving 287 contacts. Tiers: 1: 117 · 2: 41 · 3: 25 · 4: 14 · 5: 77 · 6: 13.

## Single-title example

```bash
python3 $S/blitz_contact_search.py --companies data/processed/companies_supabase_<date>.csv \
  --title "Head Partnerships" "Director Partnerships" "VP Partnerships" \
  --exclude-title Intern Assistant --location WORLD --limit 10
```
