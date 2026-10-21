#!/usr/bin/env python3
"""Suppress companies or contacts we must not prospect, using the Attio CRM (read-only).

Two levels (--level):
    domain    a company that hits a category is suppressed whole: every row with its domain is removed
    contact   only the people Attio holds who hit a category are suppressed, matched on LinkedIn URL or email;
              other people at the same company stay

Four modes, run in order, each a gate for the user:
    profile        Read Attio and count each chosen category. Small categories list their entries; big ones show counts only.
    download       Save the raw Attio pull (data/raw) and the suppression list CSV (data/processed).
    check-target   Load the list to suppress against (a CSV, or Supabase), profile it, preview the matches. Writes nothing
                   except the Supabase download.
    suppress       Write the suppressed and clean CSVs. Never changes the database.

Categories (pick with --categories, or `all`). A person inherits company signals from their company
and deal signals from the deals they're linked to.
    customer              company account_type = Customer                       no time limit
    competitor            company account_type = Competitor                     no time limit
    do_not_recontact      Lost deal, lost_reason = "Do not recontact"           no time limit
    closed_lost           Lost deal, any other reason                           no time limit (Attio has no close date); --lost-days N to limit
    pipeline_lead         open deal in stage Lead                               while open
    pipeline_in_progress  open deal in stage In Progress                        while open
    recently_contacted    company last_contacted within --contacted-days N      N days (required with this category)
    opted_out             person email_opt_out or on the Unsubscribes list      contact level only

Example:
    S=.claude/skills/suppress-companies/scripts; PY=.venv/bin/python
    C='--level domain --categories all --contacted-days 90'
    $PY $S/attio_suppression.py profile $C
    $PY $S/attio_suppression.py download $C
    $PY $S/attio_suppression.py check-target --level domain --target-supabase      # or --target-csv FILE
    $PY $S/attio_suppression.py suppress --level domain --target-supabase

Writes (date stamp = --date, default today; <level> = domain or contact):
    data/raw/attio_<object>_<date>.jsonl                   every Attio record exactly as returned (download)
    data/processed/suppression_attio_<level>_<date>.csv    the suppression list (download)
    data/processed/<companies|contacts>_supabase_<date>.csv  the target list, when it comes from Supabase
    data/processed/<target>_suppressed_<date>.csv          target rows that matched, with reasons (suppress)
    data/processed/<target>_clean_<date>.csv               target rows safe to enrich (suppress)
Run log: logs/attio_suppression.log. Failed calls: logs/attio_suppression_errors.log.
Attio reads are free and take seconds, so a failed pull is simply re-run in full (no resume): a partial,
mixed-time snapshot would be worse than none.
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
from datetime import date, timedelta
from pathlib import Path

# The project folder is wherever the script is run from (the skill folder holds only code).
ROOT = Path.cwd()
ENV_FILE = ROOT / ".env"  # --env overrides
API = "https://api.attio.com"
LOG_FILE = ROOT / "logs" / "attio_suppression.log"
ERROR_LOG = ROOT / "logs" / "attio_suppression_errors.log"

# How this Attio workspace stores each signal (CRM setup, not campaign settings).
ACCOUNT_TYPE = "account_type"
CUSTOMER, COMPETITOR = "Customer", "Competitor"
STAGE, LOST, LEAD, IN_PROGRESS = "stage", "Lost", "Lead", "In Progress"
LOST_REASON, DO_NOT_RECONTACT = "lost_reason", "Do not recontact"
LAST_CONTACTED = "last_contacted"
OPT_OUT_FLAG, OPT_OUT_LIST = "email_opt_out", "newsletter_unsubscribes"

CATEGORIES = ["customer", "competitor", "do_not_recontact", "closed_lost",
              "pipeline_lead", "pipeline_in_progress", "recently_contacted", "opted_out"]
CONTACT_ONLY = {"opted_out"}
DEAL_COLUMNS = ["account_type", "deal_stage", "stage_since", "last_contacted", "lost_reason",
                "deal_value_usd", "deal_count", "deal_owner_id"]
LIST_COLUMNS = {
    "domain": ["domain", "company_name", "suppression_reason", "suppress_until"] + DEAL_COLUMNS
              + ["attio_company_id", "pulled_on"],
    "contact": ["linkedin_url", "email", "full_name", "job_title", "company_domain", "company_name",
                "suppression_reason", "suppress_until"] + DEAL_COLUMNS + ["attio_person_id", "pulled_on"],
}


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
                 "Nothing was written for this step; fix the cause and re-run.")


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


def norm_domain(value):
    """example.com from 'https://www.Example.com/about' or 'Example.com'."""
    d = str(value or "").strip().lower()
    for prefix in ("https://", "http://"):
        d = d[len(prefix):] if d.startswith(prefix) else d
    d = d.split("/")[0]
    return d[4:] if d.startswith("www.") else d


def norm_linkedin(value):
    """linkedin.com/in/someone from any http/www/trailing-slash variant."""
    u = str(value or "").strip().lower().split("?")[0].rstrip("/")
    for prefix in ("https://", "http://"):
        u = u[len(prefix):] if u.startswith(prefix) else u
    return u[4:] if u.startswith("www.") else u


vals = lambda r, k: r["values"].get(k) or []
day = lambda s: (s or "")[:10]
join = lambda xs: "; ".join(str(x) for x in xs if x not in (None, "", False))


def title(r, k):
    v = vals(r, k)
    return (v[0].get("status") or v[0].get("option") or {}).get("title") if v else None


def classify(args, raw_dir=None):
    """Pull Attio and return (suppression list rows for args.level, CRM counts)."""
    raw = (lambda name: raw_dir / f"attio_{name}_{args.date}.jsonl") if raw_dir else (lambda name: None)
    companies = pull("/v2/objects/companies/records/query", raw("companies"))
    deals = pull("/v2/objects/deals/records/query", raw("deals"))
    people = pull("/v2/objects/people/records/query", raw("people"))
    unsub = pull(f"/v2/lists/{OPT_OUT_LIST}/entries/query", raw(f"list_{OPT_OUT_LIST}"))

    today = date.fromisoformat(args.as_of)
    contacted_from = today - timedelta(days=args.contacted_days) if args.contacted_days else None
    lost_from = today - timedelta(days=args.lost_days) if args.lost_days else None
    timed = {"recently_contacted"} | ({"closed_lost"} if lost_from else set())

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

    # Company signals: used directly at domain level, inherited by people at contact level.
    company_info = {}
    for c in companies:
        cid = c["id"]["record_id"]
        acct = title(c, ACCOUNT_TYPE)
        contacted = day((vals(c, LAST_CONTACTED) or [{}])[0].get("value"))
        hits, ends = [], []
        if acct == CUSTOMER: hits.append("customer")
        if acct == COMPETITOR: hits.append("competitor")
        if contacted_from and contacted and date.fromisoformat(contacted) >= contacted_from:
            hits.append("recently_contacted")
            ends.append(date.fromisoformat(contacted) + timedelta(days=args.contacted_days))
        company_info[cid] = {"name": vals(c, "name")[0]["value"], "account_type": acct,
                             "last_contacted": contacted, "hits": hits, "ends": ends}

    rows = []
    if args.level == "domain":
        for cid, info in company_info.items():
            if cid not in domain_of:
                logging.warning("Attio company %s has no domain: can't be matched, skipped", cid)
                continue
            hits, ends = list(info["hits"]), list(info["ends"])
            for d in deals_by_co.get(cid, []):
                h, end = deal_hits(d)
                hits += h
                ends += [end] if end else []
            hits, until = finish(hits, ends)
            if hits:
                rows.append({"domain": domain_of[cid], "company_name": info["name"],
                             "suppression_reason": join(hits), "suppress_until": until,
                             "account_type": info["account_type"], "last_contacted": info["last_contacted"],
                             **deal_fields(deals_by_co.get(cid, [])), "attio_company_id": cid, "pulled_on": args.as_of})
        rows.sort(key=lambda r: (CATEGORIES.index(r["suppression_reason"].split("; ")[0]), r["company_name"].lower()))
    else:
        on_list = {e["parent_record_id"] for e in unsub}
        for p in people:
            pid = p["id"]["record_id"]
            cid = (vals(p, "company") or [{}])[0].get("target_record_id")
            info = company_info.get(cid, {"name": "", "account_type": None, "last_contacted": "", "hits": [], "ends": []})
            hits, ends = list(info["hits"]), list(info["ends"])
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
                    **deal_fields(ds), "attio_person_id": pid, "pulled_on": args.as_of})
        rows.sort(key=lambda r: (CATEGORIES.index(r["suppression_reason"].split("; ")[0]), r["company_domain"]))
    return rows, {"companies": len(companies), "deals": len(deals), "people": len(people)}


def report(rows, threshold, label, level):
    """Per category: list the entries when there are few, counts only when there are many."""
    by_cat = collections.defaultdict(list)
    for r in rows:
        for cat in r["suppression_reason"].split("; "):
            by_cat[cat].append(r)
    unit = "domains" if level == "domain" else "people"
    print(f"\n{label}: {len(rows)} unique {unit}")
    for cat in CATEGORIES:
        if cat not in by_cat:
            continue
        hits = by_cat[cat]
        print(f"  {cat:<22} {len(hits)}")
        if len(hits) <= threshold:
            for r in hits:
                extra = join([r.get("deal_stage"), r.get("lost_reason"),
                              r.get("last_contacted") and f"contacted {r['last_contacted']}",
                              r.get("suppress_until") and f"until {r['suppress_until']}"])
                if level == "domain":
                    print(f"      - {r['domain']:<26} {str(r.get('company_name'))[:30]:<30} {extra}")
                else:  # people: job title + company, never email
                    who = f"{str(r.get('job_title') or '')[:28]} @ {r.get('company_domain') or '?'}"
                    print(f"      - {who:<56} {extra}")


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def supabase_rows(sql, out):
    import psycopg  # only needed for this source; lives in the project .venv
    with psycopg.connect(env_get("SUPABASE_DB_URL_POOLER"), prepare_threshold=None, connect_timeout=10) as conn:
        cur = conn.execute(sql)
        columns = [d.name for d in cur.description]
        rows = [dict(zip(columns, r)) for r in cur]
    write_csv(out, columns, rows)
    logging.info("downloaded %d rows from Supabase to %s", len(rows), out.relative_to(ROOT))
    return rows, columns


def load_target(args):
    """The list to suppress against: (rows, columns, key columns, file stem)."""
    processed = ROOT / "data" / "processed"
    if args.target_supabase and args.level == "domain":
        rows, columns = supabase_rows(
            "select name, domain, linkedin_url, industry, employees_on_linkedin, hq_country_code, "
            "exists (select 1 from gtm.contacts p where p.company_domain = c.domain) as has_contact "
            "from gtm.companies c order by domain", processed / f"companies_supabase_{args.date}.csv")
        return rows, columns, {"domain": "domain"}, "companies_supabase"
    if args.target_supabase:
        rows, columns = supabase_rows(
            "select person_linkedin_url, company_domain, first_name, last_name, job_title, icp_tier "
            "from gtm.contacts order by company_domain", processed / f"contacts_supabase_{args.date}.csv")
        return rows, columns, {"linkedin": "person_linkedin_url"}, "contacts_supabase"
    path = Path(args.target_csv)
    if not path.is_file():
        sys.exit(f"Target CSV not found: {path}")
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows, columns = list(reader), reader.fieldnames
    keys = ({"domain": args.domain_column} if args.level == "domain"
            else {k: v for k, v in (("linkedin", args.linkedin_column), ("email", args.email_column)) if v in columns})
    missing = [v for v in keys.values() if v not in columns]
    if missing or not keys:
        sys.exit(f"{path} lacks the match column(s) {missing or [args.linkedin_column, args.email_column]} "
                 f"(columns: {columns}). Pass --domain-column / --linkedin-column / --email-column.")
    stem = path.stem[:-11] if len(path.stem) > 11 and path.stem[-10:-6].isdigit() and path.stem[-11] == "_" else path.stem
    return rows, columns, keys, stem


def match(args):
    supp_file = Path(args.suppression or ROOT / "data" / "processed" / f"suppression_attio_{args.level}_{args.date}.csv")
    if not supp_file.is_file():
        sys.exit(f"No suppression list at {supp_file}: run `download --level {args.level}` first, or pass --suppression FILE")
    with open(supp_file, newline="") as f:
        supp_rows = list(csv.DictReader(f))
    rows, columns, keys, stem = load_target(args)

    if args.level == "domain":
        index = {r["domain"]: r for r in supp_rows}
        key_of = lambda r: [norm_domain(r[keys["domain"]])]
        lookup = lambda r: next((index[k] for k in key_of(r) if k in index), None)
    else:
        by_li = {norm_linkedin(r["linkedin_url"]): r for r in supp_rows if r["linkedin_url"]}
        by_email = {e.strip(): r for r in supp_rows for e in r["email"].split(";") if e.strip()}
        def lookup(r):
            li = norm_linkedin(r[keys["linkedin"]]) if "linkedin" in keys else ""
            em = str(r[keys["email"]] or "").strip().lower() if "email" in keys else ""
            return by_li.get(li) if li and li in by_li else by_email.get(em) if em else None
        key_of = lambda r: [norm_linkedin(r[keys["linkedin"]]) if "linkedin" in keys else str(r[keys["email"]] or "").lower()]

    ids = [key_of(r)[0] for r in rows]
    seen = collections.Counter(i for i in ids if i)
    print(f"\nSuppression list: {supp_file.name} ({len(supp_rows)} {'domains' if args.level == 'domain' else 'people'})")
    print(f"Target: {len(rows)} rows | match on {', '.join(keys.values())} | unique {len(seen)} | "
          f"blank {ids.count('')} | duplicates {sum(1 for n in seen.values() if n > 1)}")

    matched, clean = [], []
    for r in rows:
        hit = lookup(r)
        if hit:
            matched.append(dict(r, suppression_reason=hit["suppression_reason"], suppress_until=hit["suppress_until"],
                                _hit=hit))
        else:
            clean.append(r)
    report([dict(m["_hit"], **{k: v for k, v in m.items() if k in ("domain", "company_name")}) for m in matched],
           args.detail_threshold, "Would be suppressed" if args.command == "check-target" else "Suppressed", args.level)
    print(f"\n  clean (safe to enrich): {len(clean)}")
    if "has_contact" in columns:
        print(f"  suppressed companies that already have a contact: {sum(1 for m in matched if m['has_contact'])}")
    if args.command == "suppress":
        processed = ROOT / "data" / "processed"
        write_csv(processed / f"{stem}_suppressed_{args.date}.csv", columns + ["suppression_reason", "suppress_until"], matched)
        write_csv(processed / f"{stem}_clean_{args.date}.csv", columns, clean)
        logging.info("suppress (%s level): %d suppressed → %s_suppressed_%s.csv, %d clean → %s_clean_%s.csv "
                     "(database unchanged)", args.level, len(matched), stem, args.date, len(clean), stem, args.date)


def main():
    global ENV_FILE
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["profile", "download", "check-target", "suppress"])
    parser.add_argument("--level", choices=["domain", "contact"], required=True,
                        help="domain: suppress whole companies; contact: suppress only the matching people")
    parser.add_argument("--categories", nargs="+", choices=CATEGORIES + ["all"],
                        help="categories to suppress (profile/download)")
    parser.add_argument("--contacted-days", type=int, help="recently_contacted window in days, e.g. 90, 120, 365")
    parser.add_argument("--lost-days", type=int, help="limit closed_lost to deals marked Lost within N days (default: no limit)")
    parser.add_argument("--detail-threshold", type=int, default=15,
                        help="list entries for categories with at most this many (default 15), else counts only")
    parser.add_argument("--target-csv", help="check-target/suppress: CSV to suppress against")
    parser.add_argument("--target-supabase", action="store_true",
                        help="check-target/suppress: gtm.companies (domain level) or gtm.contacts (contact level)")
    parser.add_argument("--domain-column", default="domain", help="domain column in --target-csv (default: domain)")
    parser.add_argument("--linkedin-column", default="person_linkedin_url",
                        help="LinkedIn URL column in --target-csv, contact level (default: person_linkedin_url)")
    parser.add_argument("--email-column", default="email", help="email column in --target-csv, contact level (default: email)")
    parser.add_argument("--suppression", help="suppression list CSV (default: today's suppression_attio_<level>_<date>.csv)")
    parser.add_argument("--date", default=date.today().isoformat(), help="file date stamp (default today)")
    parser.add_argument("--env", help="path to the .env file (default: .env in the current folder)")
    args = parser.parse_args()
    if args.env:
        ENV_FILE = Path(args.env).expanduser().resolve()
    args.as_of = date.today().isoformat()

    if args.command in ("profile", "download"):
        if not args.categories:
            parser.error(f"{args.command} needs --categories (any of: {', '.join(CATEGORIES)}, or all)")
        cats = CATEGORIES if "all" in args.categories else args.categories
        if args.level == "domain":
            dropped = [c for c in cats if c in CONTACT_ONLY]
            if dropped and "all" not in args.categories:
                parser.error(f"{', '.join(dropped)} is a contact-level category: use --level contact")
            cats = [c for c in cats if c not in CONTACT_ONLY]
        args.categories = cats
        if "recently_contacted" in cats and not args.contacted_days:
            parser.error("recently_contacted needs --contacted-days N (e.g. 90, 120, 365)")
    elif bool(args.target_csv) == bool(args.target_supabase):
        parser.error(f"{args.command} needs exactly one of --target-csv FILE or --target-supabase")

    LOG_FILE.parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])

    if args.command == "profile":
        rows, crm = classify(args)
        print(f"CRM: {crm['companies']} companies, {crm['deals']} deals, {crm['people']} people | level {args.level} | "
              f"categories: {', '.join(args.categories)}"
              + (f" | contacted window {args.contacted_days}d" if args.contacted_days else "")
              + (f" | lost window {args.lost_days}d" if args.lost_days else ""))
        report(rows, args.detail_threshold, "Suppression list", args.level)
    elif args.command == "download":
        raw_dir = ROOT / "data" / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        rows, crm = classify(args, raw_dir)
        out = ROOT / "data" / "processed" / f"suppression_attio_{args.level}_{args.date}.csv"
        write_csv(out, LIST_COLUMNS[args.level], rows)
        logging.info("download (%s level): %d entries → %s | raw → data/raw/attio_*_%s.jsonl | categories %s",
                     args.level, len(rows), out.relative_to(ROOT), args.date, ",".join(args.categories))
    else:
        match(args)


if __name__ == "__main__":
    main()
