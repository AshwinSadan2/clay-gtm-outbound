# **Campaign Brief**

> This brief is the single source of truth for everything that gets built. If something changes mid-program - the ICP shifts, the offer evolves - we update it here first and everything downstream follows.

---

## **2a: About the Client**

> This is the top of the brief - who you're building for. Every choice further down (which companies you pull, who you write to, what you say) is made from this client's point of view, so pin down their identity and market first. Even when the client is you, fill it in as if you were briefing someone who has never heard of them - that plain, external description is exactly the grounding the rest of the brief leans on.

**Client Name:** Clay

**Client Website:** clay.com

**Client LinkedIn URL:** https://www.linkedin.com/company/grow-with-clay/

**Industry:** Go-to-market (GTM) software — B2B SaaS / sales & marketing technology.

**Description:** Clay is the enrichment + orchestration layer between raw data providers and the tools GTM teams work in (CRM, sequencer, ad platforms): "waterfall" enrichment across 150+ providers (pay only for matches), an AI research agent (Claygent), workflow orchestration, and intent/signal tracking — a single surface where GTM teams find, enrich, and act on prospect data ([Clay · Waterfall ↗](https://www.clay.com/waterfall-enrichment)). Used by 10,000+ organisations including OpenAI, Anthropic, Intercom, Canva, and Rippling; raised a $100M Series C in 2025 at a $3.1B valuation ([Couch & Associates, *Clay Explained* ↗](https://couch.associates/clay-data-orchestration-reshaping-go-to-market/)).

**Target geography:** United States

---

### **2b. ICP — Company Criteria**

> These become the actual filters in your list-building tool. The tighter and more specific these are, the better the list quality on Day 1. Don't default to broad categories — narrow is better at this stage. You can always widen later; you can't easily remove bad leads from a campaign that's already running.

**Industry to target:** SaaS / software companies. In Blitz this is the exact LinkedIn industry string `"Software Development"`, plus a `keywords.include: ["SaaS"]` bias to drop tech-media brands that self-tag under Software Development.

**Company size** *(employee count range, e.g. 10–200):* 51–200 employees. A tight mid-market band — narrow is better on Day 1, and you can widen later.

**Geography** *(country, region, or city-level if relevant):* United States (company HQ).

**Company type** *(startup, private, public, nonprofit, etc.):* Not filtered on type — predominantly private, venture-backed software companies.

**Any other company-level signals** *(e.g. recently funded, uses specific tech, hiring SDRs, etc.):* Funding stage is deliberately **not** filtered in this build (parked). Blitz company search does support funding filters (`last_funding_type`, `total_funding`, `lead_investors`), so "raised beyond seed" is available as a later lever — it just isn't applied here.

**Exclusions** *(types of companies you don't want in the list):* Tech-media / publishing brands that self-tag under "Software Development" (biased out via the `SaaS` keyword).

---

### **2c. Persona — People Criteria**

> These become the filters on the people search - who you're looking for at each of those companies.

**Target job titles:** The best-available marketing or RevOps leader at each account, via a 6-tier title cascade (the first tier with a match wins; one per company; the matched tier is recorded as `icp_tier`):

1. **Senior marketing** — VP / SVP / CMO of Marketing (+ VP of Growth / Demand Generation)
2. **Head** of Marketing / Growth / Demand Gen / Marketing Ops
3. **Director** of Marketing / Growth / Demand Gen / Marketing Ops
4. **RevOps** — VP / Head / Director of Revenue Operations · RevOps · GTM Engineer
5. **Founder fallback** — Founder / Co-founder / CEO / Owner (small companies where the founder runs GTM)
6. **Manager / IC + headline proof** — Marketing / Growth / Demand-Gen Manager, plus a headline catch-all on "marketing / growth / demand generation / revenue operations"

**Seniority level(s):** Best-available, most senior first — VP / C-level → Head → Director → RevOps leaders → Founder → Manager / IC.

**Location** *(if different from the company-level geography above):* WORLD. The company is US-based, but its marketing leader may sit anywhere; a contact-side geo filter over-produces no-matches.

**Exclusions at the people level** *(titles or roles you specifically don't want):* assistant, intern, junior, coordinator, freelance — and brand, communications, content, PR, social media (not Clay's audience).

---

### **2d. Offer & Problem Statement**

> Every email in your sequence is ultimately communicating one thing: here is a problem you have, and here is what we do about it. Get this crisp before anything gets written.

**What is the offer?** *(one sentence):* Clay — a go-to-market data aggregator/platform that runs every lead and account through 150+ data providers in a single "waterfall", then layers an AI research agent (Claygent) and automated workflows on top — so a marketing/RevOps team gets near-complete, always-fresh data and can build, enrich, and act on target lists in minutes instead of days, replacing the stack of single-source data tools they run today.

**What specific problem does it solve?** Mid-market SaaS marketing and RevOps teams run on incomplete, decaying data scattered across siloed single-source tools (ZoomInfo, Clearbit, Apollo, Cognism). Any one provider leaves a large share of records blank or stale (i.e. OpenAI was stuck in the low 40s on coverage with a single provider ([OpenAI × Clay ↗](https://www.clay.com/customers/openai))) so leads can't be scored or routed, outbound lists are thin, and ABM/ad targeting runs on partial data. On top of that, list-building and account research are done by hand (10+ minutes per prospect, days per list), and the team pays for several overlapping annual contracts whether the data matches or not. The downstream cost is bad targeting, slow routing, wasted ad and outbound spend, and a sales team that stops trusting the data. Clay consolidates all of it into one waterfall that maximises coverage, charges only for hits, and automates the manual research and CRM upkeep.

**Why is now the right moment for this prospect to pay attention?** *(what's the urgency or trigger):* Four converging triggers. **(1) Renewal pressure** — annual ZoomInfo/Clearbit/Cognism contracts are up for re-evaluation, and teams are questioning per-record fees they pay whether the record matches or not. **(2) The 2026 "GTM singularity"** — AI is resetting how GTM teams operate, and every AI/agent initiative depends on a clean, complete data foundation first; a consolidated enrichment layer is the prerequisite, and Clay *is* that layer. **(3) Lean-team scaling** — a 51–200-person SaaS company is growing inbound volume and outbound ambition faster than it can add RevOps headcount, and manual enrichment doesn't scale. **(4) Signal decay** — job changes, funding rounds, and hiring surges are time-boxed windows; the longer the data foundation stays broken, the more of them the team misses.

---

### **2e. Messaging Hypothesis**

> Your hypothesis is the core assumption behind the campaign - the belief you're testing. It keeps the sequence focused and gives you a clear signal when the campaign succeeds or fails.

Fill in the sentence below as completely as you can:

> *"We believe* **[persona]** *at* **[type of company]** *is struggling with* **[specific problem]** *because* **[root cause]***. Our* **[offer]** *helps them* **[desired outcome]** *by* **[the mechanism or approach]***."*

**Your hypothesis:** *"We believe* **marketing and RevOps leaders** *at* **51–200-employee B2B SaaS companies** *is struggling with* **incomplete, stale, siloed GTM data that leaves them unable to target, route, and personalise at scale** *because* **they rely on single-source enrichment tools that each cover only part of their records and lock them into expensive annual contracts, while a lean team fills the gaps by hand.** *Our* **waterfall-enrichment + AI research platform (Claygent)** *helps them* **get near-complete, always-fresh data and stand up enriched target lists in minutes** *by* **running every record through 150+ providers in one pass, and automating the research and CRM upkeep that used to be manual.**"*

---

### **2f. Pain Points**

> These are the raw material for copy generation. Be as concrete and specific as you can. The more specific the pain, the more the email reads like it was written by someone who actually understands the prospect's world. Aim for 2–3 pain points. For each one, capture three layers.

**Pain Point 1** — Coverage gaps from single-source enrichment

* The pain itself: Their enrichment tool (ZoomInfo / Clearbit / Apollo) only fills a fraction of records, often 40–60%, so a large share of leads and accounts land in the CRM with a missing email, title, or firmographic. The data they *do* have quietly decays as people change jobs.
* What happens if they don't solve it (implication of inaction): Half their inbound leads can't be scored or routed, outbound lists are too thin to run, and segmentation, ABM, and ad targeting all run on partial data. So, marketing spend and rep time get pointed at the wrong accounts, and the "insights" the team reports up are built on holes.
* How the offer addresses it: Clay's waterfall runs each record through 150+ providers in sequence until it hits a verified match, and only charges for hits. OpenAI more than doubled coverage (low 40s → high 80s) ([OpenAI × Clay ↗](https://www.clay.com/customers/openai)) and Anthropic 3x'd theirs ([Anthropic × Clay ↗](https://www.clay.com/customers/anthropic)), with close to zero manual work, turning a half-blank CRM into one complete enough to score, route, and target on.

**Pain Point 2** — Manual list-building and research eats a lean team alive

* The pain itself: Building a target list, researching each account, and personalising outreach is done by hand, up to 10 minutes per prospect ([Sendoso × Clay ↗](https://www.clay.com/customers/sendoso)), and days to stand up a single list. A 51–200-person SaaS team is absorbing rising inbound volume *and* trying to run outbound, with no headcount to spare for data entry.
* Implication of inaction: Campaigns ship slowly and speed-to-lead slips, reps spend their day researching instead of selling, personalisation gets dropped to hit volume, and promising new campaign ideas never launch because standing up the list is too expensive to justify.
* How the offer addresses it: Claygent (the AI research agent) and automated workflows enrich and research every row for you. Intercom cut list-building from days to minutes and sourced 4,000+ accounts / 21,000 contacts in a single month ([Intercom × Clay ↗](https://www.clay.com/customers/intercom)); Oyster saved 40 hours per rep per month on intent-based outbound ([Oyster × Clay ↗](https://www.clay.com/customers/oyster)); Anthropic reclaimed hours a week (4 of them just on automated CRM upserts) ([Anthropic × Clay ↗](https://www.clay.com/customers/anthropic)).

**Pain Point 3** *(optional)* — A sprawling, expensive, siloed data stack that sales doesn't trust

* The pain itself: They pay for several overlapping tools on annual contracts (a database, an enrichment vendor, an intent tool, an email finder), the data lives in separate silos, and because enrichment arrives from opaque, scattered sources, sales doesn't trust it and reverts to researching by hand anyway.
* Implication of inaction: Budget bleeds on redundant contracts and per-record fees paid whether the record matched or not; RevOps burns cycles stitching tools together; conflicting data across systems breaks routing and reporting; and sales adoption stalls, so the whole tooling investment underdelivers.
* How the offer addresses it: Clay consolidates 150+ providers behind one interface and one bill, pay only for matches, so multiple contracts collapse into one (Anthropic and Oyster consolidated and cancelled data vendors — [Anthropic ↗](https://www.clay.com/customers/anthropic), [Oyster ↗](https://www.clay.com/customers/oyster)). Its "glass box" transparency lets reps audit every raw signal and firmographic in one place, which rebuilt sales' trust at Intercom and helped grow their outbound-sourced pipeline 140% ([Intercom × Clay ↗](https://www.clay.com/customers/intercom)).

---

### **2g. Key Assumptions**

> These are the things that need to be true for this campaign to work. Writing them down now makes debugging later much faster — when a campaign underperforms, you check the assumptions first.

**What needs to be true about the ICP for this to land?** That 51–200-employee US SaaS companies have enough inbound *and* outbound volume, and enough data spend, to feel the coverage and cost pain, but are small enough that they haven't over-built a RevOps org or locked into an enterprise Customer Data Platform (CDP), so a consolidated, largely self-serve data layer is still a live buying decision. In practice this means there's an incumbent to displace or augment: they already pay for at least one enrichment/data tool, so the problem is real to them and the switching conversation is concrete rather than educational.

**What needs to be true about the persona?** That the marketing/RevOps leader owns or heavily influences the data/enrichment budget and the CRM-data-quality problem, and feels it personally: they're the one explaining bad data to sales, watching campaigns run on thin lists, or defending the enrichment line item at renewal. At this company size the same person tends to span demand gen *and* ops, so "your data is incomplete and your team is doing it by hand" is their problem to fix, not something they can wave off to another department.

**What needs to be true about the offer or the timing?** Two things have to hold. First, that Clay is a genuine step-change over their current single-source tool, not a marginal upgrade — the headline claim (2–3x the coverage, list-building from days down to minutes, one bill in place of four) has to be both true *and* provable, which the named peers make credible ([OpenAI ↗](https://www.clay.com/customers/openai), [Anthropic ↗](https://www.clay.com/customers/anthropic), [Intercom ↗](https://www.clay.com/customers/intercom), [Oyster ↗](https://www.clay.com/customers/oyster)). Second, that a real trigger is live right now — a renewal, a coverage or deliverability problem they can already feel, a lean-team scaling push, or an AI/data-foundation initiative — so that acting this quarter is clearly better than parking it.

---

### **2h. Email Sequence**

> A rough structure is fine here — you'll have time to polish it before the Copy Generation block. At minimum, give each email a purpose. If you already have a more complete draft with placeholder slots (e.g. `{{personalised_opener}}`), place that here. We will take it straight into the program as the sequence template.

**The three-email sequence below is final copy, ready for the sender.** The mail-merge variables:

- `{FIRST_NAME}` — substitution (the contact's first name).
- `{OPENER}` — Email 1, line 1: the ONE **AI-composed** slot, a two-pass LLM opener written from the contact's About (falling back to the company About). Everything else in every email is fixed static copy; the model fills only this slot.
- `{ROLE}` — Email 1, line 2: **deterministic**, set from the contact's title. See **the `{ROLE}` bank** below.
- `{PS_LINE}` — appended to Email 1: **deterministic**, chosen from the Ex-4 `tech_stack_type`. Fires only when a tech signal is present. See **the `{PS_LINE}` (P.S.) bank** below.
- `{{tech_stack}}` — substitution (the specific tool detected in Ex-4), used inside the P.S. line.
- `{a|b}` — spintax, auto-rotated per send · `%signature%` — the per-mailbox sender block · Email 3 uses a conditional greeting.

> **EmailBison merge-tag syntax (Session 9):** merge tags are **single-brace UPPERCASE** — `{FIRST_NAME}`, `{OPENER}`, `{ROLE}`, `{PS_LINE}` (a valueless/mistyped tag renders **empty**, not literal). `{PS_LINE}` is **fully resolved before the push** — `{{tech_stack}}` (the detected tool) is already substituted into the P.S. text by the copy script, so there is no separate `tech_stack` tag in the sent email. **`%signature%` is NOT an EmailBison token** — the signature is a **property of the sender email account** (set per mailbox), so it is dropped from the pushed body and comes from the mailbox, not the copy. Spintax `{a|b}` (with a pipe) is distinct from a merge tag and rotates per send.

**Standing rule: no dashes anywhere in the copy sent to prospects** (no "—", no "–", no " - " as punctuation).

**Email 1: the coverage gap**

> Hey {FIRST_NAME}, {OPENER}
>
> We have been talking to a lot of {ROLE} like you, and kept hearing the same thing. Their enrichment tool pulls from one source, so half their records land empty.
>
> Clay pulls from 150+ sources instead, and only bills you for hits. You get a full record you can actually work with.
>
> Anthropic tripled their coverage this way, with almost no cleanup.
>
> {Would it help to see this on your list?|Open to a look?}
>
> %signature%
>
> {PS_LINE}

**Email 2: show, don't tell (the sample)**

> Hello {FIRST_NAME},
>
> Rather than make the case over email, it's easier to just show you.
>
> I can pull a sample of 500 contacts from your ICP, fully enriched, so you can judge the coverage yourself before we ever talk.
>
> {Worth putting together?|Want me to pull one?}
>
> %signature%

**Email 3: the one-line bump**

> {FIRST_NAME}, {is this worth exploring on your end|any info I could send on this|happy to park it if now's not the time}?
>
> %signature%

#### The `{ROLE}` bank (deterministic)

Email 1, line 2 reads "a lot of `{ROLE}` like you". `{ROLE}` is set from the contact's title, checked **top to bottom, first match wins** (so a founder is always "founders"; and an explicit marketing signal beats a stray revenue word, so a "Product Marketing / GTM" title stays marketing):

| If the title contains | `{ROLE}` becomes |
|---|---|
| founder, co-founder, CEO, chief executive, owner | **founders** |
| marketing, demand gen | **marketing leaders** |
| sales, revenue, RevOps, GTM, business development | **revenue leaders** |
| anything else | **marketing leaders** |

#### The `{PS_LINE}` bank (deterministic)

One P.S. line is appended to Email 1, chosen by the Ex-4 `tech_stack_type`. It fires **only** when a tech signal is present; a company with no signal gets no P.S. If a company matches more than one type, the tie breaks in this priority: **CRM > Ad Pixel > Marketing Automation**. `{{tech_stack}}` is the specific tool name detected.

| `tech_stack_type` | `{PS_LINE}` |
|---|---|
| **CRM** | P.S. {{tech_stack}} plugs right into Clay, so your enriched data syncs straight back to your CRM. |
| **Ad Pixel** | P.S. Clay Ads builds your {{tech_stack}} audiences from the same enriched data, with self-updating exclusion lists so ad spend skips the customers you already have. |
| **Marketing Automation** | P.S. {{tech_stack}} connects natively to Clay, so you can keep your campaigns filled with enriched leads without juggling CSVs. |

---
