# Clay-Relevant Tech Providers — Detectable Stack Reference

*An evergreen reference. Not session-specific. Share with students so they can build their own tech-detection filters without rediscovering this universe live.*

---

## Why this exists

When you run a tech-detection API (DetectZeStack, Wappalyzer, BuiltWith, etc.) against a company's website, it hands you back a **raw array of everything it can see** — usually 5–15 technologies, most of it generic plumbing: CDNs, hosting, SSL certificates, JavaScript frameworks, fonts. That raw array is **noise** for a Clay pitch.

The skill isn't fetching the stack — it's **filtering it down to the tools that actually matter for the conversation you want to have.** For Clay, that means the tools Clay plugs into, feeds, or makes more valuable: CRMs, marketing-automation platforms, sales sequencers, CDPs, ad pixels, and so on.

## What this is

This is the **allowlist of Clay-relevant providers that can be detected on a public website.** Two filters are already baked into every name here:

1. **Relevant to Clay** — it's part of the GTM/data stack Clay integrates with, sends data to, or improves the ROI of. (Random infra like Cloudflare or React is *not* here, even though it's detectable.)
2. **Detectable** — it leaves a public footprint (a tracking script, a form, an embed, a pixel, a DNS/header signature). A tool that runs purely internally with no web footprint won't reliably show, no matter how relevant it is — those are flagged below.

**Use it like this:** when you build your own enrichment script, don't hand-curate a list live. Match the API's response against the names/categories below, keep the hits, drop everything else, and derive a simple `FOUND` / `NOT_FOUND` from whether anything matched. That's the whole move.

---

## The list — Clay-relevant, detectable providers

Grouped by GTM function. **Detectability:** 🟢 shows readily · 🟡 sometimes · 🔴 rarely (internal tool — listed because a hit is high-value when it happens).

### CRM
Salesforce 🟡 · HubSpot 🟢 · Zoho 🟢 · Pipedrive 🟡 · Close 🔴 · Microsoft Dynamics 365 🔴 · Freshsales 🟡 · SugarCRM 🟡 · Copper 🟡 · Insightly 🟡 · Attio 🔴 · amoCRM 🟢 · Bitrix24 🟢

### Marketing automation / email marketing
HubSpot 🟢 · Marketo 🟢 · Pardot (Salesforce Marketing Cloud Account Engagement) 🟢 · Klaviyo 🟢 · ActiveCampaign 🟢 · Customer.io 🟡 · Braze 🟡 · Iterable 🟡 · Mailchimp 🟢 · Brevo (Sendinblue) 🟢 · MailerLite 🟢 · HighLevel 🟢 · Eloqua (Oracle) 🟡

### Sales engagement / sequencers
Outreach 🔴 · Salesloft 🔴 · Apollo 🔴 · SmartLead 🔴 · Instantly 🔴 · Lemlist 🔴 · Reply.io 🔴 · Woodpecker 🔴
*(Almost all internal — but a rare public hit is the strongest signal you can get: it means they run active outbound.)*

### Customer data platform (CDP) / tag management
Segment 🟢 · RudderStack 🟡 · Tealium 🟢 · mParticle 🟡 · Google Tag Manager 🟢 *(ubiquitous — weak signal on its own)*

### Live chat / conversational
Intercom 🟢 · Drift 🟢 · Qualified 🟢 · Zendesk 🟢 · Crisp 🟢 · tawk.to 🟢 · LiveChat 🟢 · Channel.io 🟢 · Chatlio 🟡 · Olark 🟡

### Scheduling / lead routing
Calendly 🟢 · Chili Piper 🟢 · HubSpot Meetings 🟢 · RevenueHero 🟡 · Default 🟡

### Advertising / audiences (paid-media pixels)
LinkedIn Insight Tag 🟢 · Google Ads (Conversion / Remarketing tag) 🟢 · Meta Pixel (Facebook) 🟢 · Twitter / X Ads Pixel 🟡 · Reddit Pixel 🟡 · TikTok Pixel 🟡
*(For B2B software companies, any of these = B2B ad intent — they're not running consumer ads. Exclude publisher ad tech like AdSense, which means they **sell** ad space, not run ads.)*

### Website visitor de-anonymization / intent (very Clay-adjacent)
RB2B 🟢 · Warmly 🟢 · Koala 🟢 · Vector 🟡 · Clearbit / HubSpot Breeze Intelligence (Reveal) 🟢 · ZoomInfo (FormComplete / WebSights) 🟡 · 6sense 🟡 · Demandbase 🟡
*(These identify who's on the site — the exact problem Clay-fed enrichment competes with / complements. A hit is a strong talking point.)*

### Product analytics / onboarding (PLG signals)
Amplitude 🟢 · Mixpanel 🟢 · Heap 🟢 · Pendo 🟢 · Appcues 🟡 · June 🟡 · Userpilot 🟡
*(Signals a product-led motion. Optional — include if PLG companies are in your ICP.)*

### A/B testing / personalization / ABM
Optimizely 🟢 · VWO 🟢 · Mutiny 🟡 · Intellimize 🟡 · Google Optimize 🟢 *(sunset — legacy hits only)*
*(Mutiny especially is an ABM/GTM-personalization tool — very on-theme.)*

### Forms / lead capture
Typeform 🟢 · HubSpot Forms 🟢 · Default 🟡 · Jotform 🟢 · Formstack 🟡

### Reviews / social proof
G2 🟡 · Trustpilot 🟢 · Capterra 🟡
*(Buyer-stage signal — they care about their category reputation.)*

---

## Notes — how to think about this list

- **The list is a superset; each campaign filters a subset.** For any given campaign you pick the groups whose *copy angle* you actually want to write. (Our Ex-4 run used CRM + core tech stack + ad pixels; a different campaign might lean on the intent/de-anonymization tools instead.)

- **Marketing stack shows; sales stack hides.** Public detection reads the *marketing/analytics/infra* layer — HubSpot, Segment, Intercom, ad pixels — far more than the internal *sales* layer (Salesforce back-office, Outreach, Apollo). Expect most hits to be marketing-side, and expect honest `NOT_FOUND`s. When a sales-side tool *does* surface, it's the most valuable hit — treat it accordingly.

- **`NOT_FOUND` is a real answer, not a failure.** A company can return a full stack and still be `NOT_FOUND` if none of it is on this list. That's correct: the API found things, your filter found nothing *relevant*. The filter is what decides the status — not the API. Derive it from the data, never from the vendor's label.

- **Names and categories both matter when you match.** Detection APIs tag each tech with a category (CRM, Live chat, Advertising…) *and* a name. Match on category where the category is clean, and on specific names where it isn't (e.g. Advertising — allow the named pixels, exclude publisher ad tech). Names drift and rebrand (Pardot → SF Marketing Cloud Account Engagement; Sendinblue → Brevo), so re-check the exact string your provider returns.

- **The value line is about Clay, not their tool.** The point of detecting a tool isn't to say "I see you use X." It's to say **how Clay relates to X and lifts their ROI from it** — Clay enriches every record into their CRM, feeds their sequencer verified leads, sharpens their ad audiences. Their tool is the hook; Clay's value on top of it is the message.

- **Keep the raw response.** Store the full API array even for the tools you drop — it's the escape valve. If a future campaign wants a different angle, you filter the raw again instead of paying to re-fetch.
