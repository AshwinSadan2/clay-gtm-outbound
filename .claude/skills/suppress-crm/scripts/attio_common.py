"""Shared code for the three Attio suppression scripts (attio_profile.py, attio_download.py, attio_suppress.py).

Reads the Attio CRM (read-only) and decides which companies or people to suppress. Not run directly.

Levels (--level):
    domain    a company that hits a category is suppressed whole: every row with its domain is removed
    contact   only the people Attio holds who hit a category are suppressed, matched on EMAIL only (both sides,
              never LinkedIn URL); other people at the same company stay. Needs a lead list with emails.

Categories (--categories, or `all`). A person inherits company signals from their company and deal signals
from the deals they're linked to. At domain level, a company also inherits in_conversation from its people.
    customer              company account_type = Customer                       no time limit
    competitor            company account_type = Competitor                     no time limit
    do_not_recontact      Lost deal, lost_reason = "Do not recontact"           no time limit
    closed_lost           Lost deal, any other reason                           no time limit (no close date in Attio); --lost-days N to limit
    pipeline_lead         open deal in stage Lead                               while open
    pipeline_in_progress  open deal in stage In Progress                        while open
    recently_contacted    company last_contacted within --days                  --days (default 90)
    in_conversation       a person's last email/calendar interaction within --days   --days (default 90). Needs mailbox/calendar sync in Attio.
    opted_out             person email_opt_out or on the Unsubscribes list      contact level only
"""
import argparse
import collections
import csv
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
API = "https://api.attio.com"
LOG_FILE = ROOT / "logs" / "attio_suppression.log"
ERROR_LOG = ROOT / "logs" / "attio_suppression_errors.log"
PROCESSED = ROOT / "data" / "processed"

# How this Attio workspace stores each signal (CRM setup, not campaign settings).
ACCOUNT_TYPE = "account_type"
CUSTOMER, COMPETITOR = "Customer", "Competitor"
STAGE, LOST, LEAD, IN_PROGRESS = "stage", "Lost", "Lead", "In Progress"
LOST_REASON, DO_NOT_RECONTACT = "lost_reason", "Do not recontact"
LAST_CONTACTED = "last_contacted"
LAST_INTERACTION = "last_interaction"  # Attio system field: latest email or calendar interaction
OPT_OUT_FLAG, OPT_OUT_LIST = "email_opt_out", "newsletter_unsubscribes"

CATEGORIES = ["customer", "competitor", "do_not_recontact", "closed_lost", "pipeline_lead",
              "pipeline_in_progress", "recently_contacted", "in_conversation", "opted_out"]
CONTACT_ONLY = {"opted_out"}
DEAL_COLUMNS = ["account_type", "deal_stage", "stage_since", "last_contacted", "last_interaction", "lost_reason",
                "deal_value_usd", "deal_count", "deal_owner_id"]
LIST_COLUMNS = {
    "domain": ["domain", "company_name", "suppression_reason", "suppress_until"] + DEAL_COLUMNS
              + ["attio_company_id", "pulled_on"],
    "contact": ["linkedin_url", "email", "full_name", "job_title", "company_domain", "company_name",
                "suppression_reason", "suppress_until"] + DEAL_COLUMNS + ["attio_person_id", "pulled_on"],
}


def suppression_file(level, stamp):
    return PROCESSED / f"suppression_attio_{level}_{stamp}.csv"


# ---------- arguments ----------

def base_parser(description):
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--level", choices=["domain", "contact"], required=True,
                        help="domain: suppress whole companies; contact: suppress only the matching people")
    parser.add_argument("--detail-threshold", type=int, default=15,
                        help="list entries for categories with at most this many (default 15), else counts only")
    parser.add_argument("--date", default=date.today().isoformat(), help="file date stamp (default today)")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    return parser


def add_category_args(parser):
    parser.add_argument("--categories", nargs="+", required=True, choices=CATEGORIES + ["all"],
                        help="categories to suppress, or all")
    parser.add_argument("--days", type=int, default=90,
                        help="window for recently_contacted and in_conversation, in days (default 90)")
    parser.add_argument("--lost-days", type=int,
                        help="limit closed_lost to deals marked Lost within N days (default: no limit)")


def setup(parser):
    """Parse, apply --env, validate categories, start logging. Returns args."""
    global ENV_FILE
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    args.as_of = date.today().isoformat()
    if getattr(args, "categories", None):
        cats = CATEGORIES if "all" in args.categories else args.categories
        if args.level == "domain":
            wrong = [c for c in cats if c in CONTACT_ONLY]
            if wrong and "all" not in args.categories:
                parser.error(f"{', '.join(wrong)} is a contact-level category: use --level contact")
            cats = [c for c in cats if c not in CONTACT_ONLY]
        if args.days < 1:
            parser.error("--days must be a positive number of days")
        args.categories = cats
    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
    return args


def describe(args):
    dated = [c for c in args.categories if c in ("recently_contacted", "in_conversation")]
    return (f"level {args.level} | categories: {', '.join(args.categories)}"
            + (f" | window {args.days}d for {', '.join(dated)}" if dated else "")
            + (f" | lost window {args.lost_days}d" if args.lost_days else ""))


# ---------- Attio ----------

def env_get(key):
    if not ENV_FILE.is_file():
        sys.exit(f"No .env at {ENV_FILE}: run from the project folder or pass --env PATH")
    for line in ENV_FILE.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip()
    sys.exit(f"{key} missing from .env")


def log_error(code, message, request):
    ERROR_LOG.parent.mkdir(exist_ok=True)
    with open(ERROR_LOG, "a") as f:
        f.write(json.dumps({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "code": code,
                            "message": message, "request": request}) + "\n")


def call(path, body=None, attempts=3):
    """GET (or POST a read query). Retries 429/500/503; anything else is logged and stops the run."""
    req = urllib.request.Request(
        API + path, method="POST" if body is not None else "GET",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {env_get('ATTIO_API_KEY')}", "Content-Type": "application/json"})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)["data"]
        except urllib.error.HTTPError as e:
            code, message = e.code, e.read().decode(errors="replace")[:1000]
        except (urllib.error.URLError, TimeoutError) as e:
            code, message = "network", str(e)
        if code in (429, 500, 503) and attempt < attempts:
            wait = 60 if code == 429 else 2 ** attempt
            logging.warning("HTTP %s on %s, retrying in %ss", code, path, wait)
            time.sleep(wait)
            continue
        log_error(code, message, {"path": path, "body": body})
        sys.exit(f"Attio call failed (HTTP {code}) on {path}: see {ERROR_LOG.relative_to(ROOT)}. "
                 "Nothing was written for this step; fix the cause and re-run. "
                 "(Attio reads are free and take seconds, so a failed pull is re-run in full: "
                 "a partial, mixed-time snapshot would be worse than none.)")


def pull(path, raw_file=None):
    """Page through an Attio query. With raw_file, stream every record to disk as it arrives."""
    out, offset = [], 0
    f = open(raw_file, "w") if raw_file else None
    try:
        while True:
            rows = call(path, {"limit": 500, "offset": offset})
            if f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
                f.flush()
            out += rows
            offset += len(rows)
            if len(rows) < 500:
                return out
    finally:
        if f:
            f.close()


# ---------- helpers ----------

def norm_domain(value):
    """example.com from 'https://www.Example.com/about' or 'Example.com'."""
    d = str(value or "").strip().lower()
    for prefix in ("https://", "http://"):
        d = d[len(prefix):] if d.startswith(prefix) else d
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


vals = lambda r, k: r["values"].get(k) or []
day = lambda s: (s or "")[:10]
join = lambda xs: "; ".join(str(x) for x in xs if x not in (None, "", False))


def title(r, k):
    v = vals(r, k)
    return (v[0].get("status") or v[0].get("option") or {}).get("title") if v else None


def interaction_day(r):
    """Date of the record's last email/calendar interaction, or ''."""
    v = vals(r, LAST_INTERACTION)
    return day(v[0].get("interacted_at")) if v else ""


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


# ---------- classification ----------

def classify(args, raw_dir=None):
    """Pull Attio and return (suppression list rows for args.level, CRM counts).
    With raw_dir, every record is also saved untouched to data/raw."""
    raw = (lambda name: raw_dir / f"attio_{name}_{args.date}.jsonl") if raw_dir else (lambda name: None)
    companies = pull("/v2/objects/companies/records/query", raw("companies"))
    deals = pull("/v2/objects/deals/records/query", raw("deals"))
    people = pull("/v2/objects/people/records/query", raw("people"))
    unsub = pull(f"/v2/lists/{OPT_OUT_LIST}/entries/query", raw(f"list_{OPT_OUT_LIST}"))

    today = date.fromisoformat(args.as_of)
    window_from = today - timedelta(days=args.days)
    lost_from = today - timedelta(days=args.lost_days) if args.lost_days else None
    timed = {"recently_contacted", "in_conversation"} | ({"closed_lost"} if lost_from else set())
    recent = lambda d: d and date.fromisoformat(d) >= window_from
    lapse = lambda d: date.fromisoformat(d) + timedelta(days=args.days)

    def deal_hits(d):
        """Categories one deal triggers, and the date its time limit ends (or None)."""
        stage, since = title(d, STAGE), day(vals(d, STAGE)[0].get("active_from"))
        if stage == LEAD: return ["pipeline_lead"], None
        if stage == IN_PROGRESS: return ["pipeline_in_progress"], None
        if stage == LOST and title(d, LOST_REASON) == DO_NOT_RECONTACT: return ["do_not_recontact"], None
        if stage == LOST and (not lost_from or date.fromisoformat(since) >= lost_from):
            return ["closed_lost"], (date.fromisoformat(since) + timedelta(days=args.lost_days) if lost_from else None)
        return [], None

    def deal_fields(ds):
        return {
            "deal_stage": join(title(d, STAGE) for d in ds),
            "stage_since": join(day(vals(d, STAGE)[0].get("active_from")) for d in ds),
            "lost_reason": join(title(d, LOST_REASON) for d in ds),
            "deal_value_usd": join(int((vals(d, "value") or [{}])[0].get("currency_value") or 0) for d in ds),
            "deal_count": len(ds),
            "deal_owner_id": join((vals(d, "owner") or [{}])[0].get("referenced_actor_id") for d in ds),
        }

    def finish(hits, ends):
        """Keep only the chosen categories. suppress_until is set only when every hit is time-limited."""
        hits = [h for h in dict.fromkeys(hits) if h in args.categories]
        until = max(ends).isoformat() if hits and set(hits) <= timed and ends else ""
        return hits, until

    deals_by_co, deals_by_person = collections.defaultdict(list), collections.defaultdict(list)
    for d in deals:
        for c in vals(d, "associated_company"):
            deals_by_co[c["target_record_id"]].append(d)
        for p in vals(d, "associated_people"):
            deals_by_person[p["target_record_id"]].append(d)
    domain_of = {c["id"]["record_id"]: norm_domain(vals(c, "domains")[0]["domain"])
                 for c in companies if vals(c, "domains")}
    company_of = {p["id"]["record_id"]: (vals(p, "company") or [{}])[0].get("target_record_id") for p in people}

    # Latest in-window person interaction per company: an SDR in conversation holds the whole company.
    talking = {}
    for p in people:
        when = interaction_day(p)
        cid = company_of[p["id"]["record_id"]]
        if recent(when) and cid:
            talking[cid] = max(talking.get(cid, ""), when)

    # Company signals: used directly at domain level, inherited by people at contact level.
    company_info = {}
    for c in companies:
        cid = c["id"]["record_id"]
        acct = title(c, ACCOUNT_TYPE)
        contacted = day((vals(c, LAST_CONTACTED) or [{}])[0].get("value"))
        hits, ends = [], []
        if acct == CUSTOMER: hits.append("customer")
        if acct == COMPETITOR: hits.append("competitor")
        if recent(contacted):
            hits.append("recently_contacted"); ends.append(lapse(contacted))
        company_info[cid] = {"name": vals(c, "name")[0]["value"], "account_type": acct, "last_contacted": contacted,
                             "last_interaction": max(interaction_day(c), talking.get(cid, "")),
                             "hits": hits, "ends": ends}

    rows = []
    if args.level == "domain":
        for cid, info in company_info.items():
            if cid not in domain_of:
                logging.warning("Attio company %s has no domain: can't be matched, skipped", cid)
                continue
            hits, ends = list(info["hits"]), list(info["ends"])
            if cid in talking:
                hits.append("in_conversation"); ends.append(lapse(talking[cid]))
            for d in deals_by_co.get(cid, []):
                h, end = deal_hits(d)
                hits += h
                ends += [end] if end else []
            hits, until = finish(hits, ends)
            if hits:
                rows.append({"domain": domain_of[cid], "company_name": info["name"],
                             "suppression_reason": join(hits), "suppress_until": until,
                             "account_type": info["account_type"], "last_contacted": info["last_contacted"],
                             "last_interaction": info["last_interaction"], **deal_fields(deals_by_co.get(cid, [])),
                             "attio_company_id": cid, "pulled_on": args.as_of})
        rows.sort(key=lambda r: (CATEGORIES.index(r["suppression_reason"].split("; ")[0]), r["company_name"].lower()))
    else:
        on_list = {e["parent_record_id"] for e in unsub}
        blank = {"name": "", "account_type": None, "last_contacted": "", "last_interaction": "", "hits": [], "ends": []}
        for p in people:
            pid = p["id"]["record_id"]
            cid = company_of[pid]
            info = company_info.get(cid, blank)
            hits, ends = list(info["hits"]), list(info["ends"])
            when = interaction_day(p)
            if recent(when):
                hits.append("in_conversation"); ends.append(lapse(when))
            ds = deals_by_person.get(pid, [])
            for d in ds:
                h, end = deal_hits(d)
                hits += h
                ends += [end] if end else []
            if (vals(p, OPT_OUT_FLAG) and vals(p, OPT_OUT_FLAG)[0].get("value")) or pid in on_list:
                hits.append("opted_out")
            hits, until = finish(hits, ends)
            if hits:
                rows.append({
                    "linkedin_url": (vals(p, "linkedin") or [{}])[0].get("value", ""),
                    "email": join(e.get("email_address", "").lower() for e in vals(p, "email_addresses")),
                    "full_name": (vals(p, "name") or [{}])[0].get("full_name", ""),
                    "job_title": (vals(p, "job_title") or [{}])[0].get("value", ""),
                    "company_domain": domain_of.get(cid, ""), "company_name": info["name"],
                    "suppression_reason": join(hits), "suppress_until": until,
                    "account_type": info["account_type"], "last_contacted": info["last_contacted"],
                    "last_interaction": when, **deal_fields(ds), "attio_person_id": pid, "pulled_on": args.as_of})
        rows.sort(key=lambda r: (CATEGORIES.index(r["suppression_reason"].split("; ")[0]), r["company_domain"]))
    crm = {"companies": len(companies), "deals": len(deals), "people": len(people),
           "people_with_interaction": sum(1 for p in people if interaction_day(p))}
    return rows, crm


def report(rows, threshold, label, level):
    """Per category: list the entries when there are few, counts only when there are many."""
    by_cat = collections.defaultdict(list)
    for r in rows:
        for cat in r["suppression_reason"].split("; "):
            by_cat[cat].append(r)
    print(f"\n{label}: {len(rows)} unique {'domains' if level == 'domain' else 'people'}")
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        hits = by_cat[cat]
        print(f"  {cat:<22} {len(hits)}")
        if len(hits) <= threshold:
            for r in hits:
                extra = join([r.get("deal_stage"), r.get("lost_reason"),
                              r.get("last_contacted") and f"contacted {r['last_contacted']}",
                              r.get("last_interaction") and f"interaction {r['last_interaction']}",
                              r.get("suppress_until") and f"until {r['suppress_until']}"])
                if level == "domain":
                    print(f"      - {r['domain']:<26} {str(r.get('company_name'))[:30]:<30} {extra}")
                else:  # people: job title + company, never name or email
                    who = f"{str(r.get('job_title') or '')[:28]} @ {r.get('company_domain') or '?'}"
                    print(f"      - {who:<56} {extra}")
