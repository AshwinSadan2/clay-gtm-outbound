# Tech distiller — Clay (outbound campaign, 2026-10-27)

The client's distiller doc: which detected tools count as a signal for this campaign, their type, and the
ranking of the types. Converted to its config with `distill_tech_stack.py config --doc docs/clay-tech-distiller.md --config data/processed/distiller_clay_<date>.json`. Drawn from the
evergreen universe in `docs/clay-relevant-tech-providers.md` (CRM, sequencer and ad-pixel groups only).

## Decisions

| Point | Decision |
|---|---|
| Types allowed | CRM · Sequencer · Ad pixel. Nothing else (no chat, no general marketing automation, no intent tools) |
| Sequencer | Email outreach / sequencing tools only |
| HubSpot | CRM. **HubSpot CMS Hub is not counted** (a website platform, not the CRM) |
| Ad pixels | Paid-media pixels only. Publisher ad tech (Google AdSense) excluded: it means they sell ad space |
| Ranking | CRM 1 · Sequencer 2 · Ad pixel 3: the owner's listed order, **to be confirmed** |
| Relation | All corresponding: Clay pushes enriched records into CRMs, feeds sequencers, and syncs ad audiences |

## Allowlist

Tool = the exact name the detection API returns (case-insensitive). Names drift (Sendinblue → Brevo): when a known
tool is missed, add its detected spelling as another row.

| Rank | Type | Tool | Relation |
|---|---|---|---|
| 1 | CRM | Salesforce | corresponding |
| 1 | CRM | HubSpot | corresponding |
| 1 | CRM | Zoho CRM | corresponding |
| 1 | CRM | Zoho | corresponding |
| 1 | CRM | Pipedrive | corresponding |
| 1 | CRM | Close | corresponding |
| 1 | CRM | Microsoft Dynamics 365 | corresponding |
| 1 | CRM | Freshsales | corresponding |
| 1 | CRM | Freshworks CRM | corresponding |
| 1 | CRM | SugarCRM | corresponding |
| 1 | CRM | Copper | corresponding |
| 1 | CRM | Insightly | corresponding |
| 1 | CRM | Attio | corresponding |
| 1 | CRM | amoCRM | corresponding |
| 1 | CRM | Bitrix24 | corresponding |
| 2 | Sequencer | Outreach | corresponding |
| 2 | Sequencer | Salesloft | corresponding |
| 2 | Sequencer | Apollo | corresponding |
| 2 | Sequencer | Apollo.io | corresponding |
| 2 | Sequencer | Smartlead | corresponding |
| 2 | Sequencer | Instantly | corresponding |
| 2 | Sequencer | lemlist | corresponding |
| 2 | Sequencer | Reply.io | corresponding |
| 2 | Sequencer | Woodpecker | corresponding |
| 3 | Ad pixel | Linkedin Ads | corresponding |
| 3 | Ad pixel | LinkedIn Insight Tag | corresponding |
| 3 | Ad pixel | Google Ads | corresponding |
| 3 | Ad pixel | Google Ads Conversion Tracking | corresponding |
| 3 | Ad pixel | Google Remarketing | corresponding |
| 3 | Ad pixel | Facebook Pixel | corresponding |
| 3 | Ad pixel | Meta Pixel | corresponding |
| 3 | Ad pixel | Twitter Ads | corresponding |
| 3 | Ad pixel | X Ads | corresponding |
| 3 | Ad pixel | Reddit Ads | corresponding |
| 3 | Ad pixel | Reddit Pixel | corresponding |
| 3 | Ad pixel | TikTok Pixel | corresponding |
