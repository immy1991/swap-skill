#!/usr/bin/env python3
"""Run the whole swap chain's scripts end to end on an invented company.

Usage: run_example.py [--skills-dir DIR] [--workdir DIR] [--track lean|full|both]

--workdir must be new or empty: the example writes, overwrites and deletes files inside it.

The company ("Harbour Studio Co"), its tools, customers and bookings are invented.
This exercises the data handoffs and gates between the skills, with real files passed
from one step to the next. It does not build an app: the build and test steps are
represented by the files they would write (statuses and a bug log), and the script says so.

Includes the failures on purpose: a migration that loses data, a colour that fails
contrast, an open S2 bug that blocks cutover, and a forecast that says KEEP SAAS.
Exit 0 only if every expectation below held.
"""
import argparse
import csv
import datetime
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
def _default_skills():
    # repo layout: tools/swap-series/example -> ../../../skills ; public layout: example -> ..
    for cand in (os.path.join(HERE, "..", "..", "..", "skills"), os.path.join(HERE, "..")):
        if os.path.isdir(os.path.join(cand, "swap-audit")):
            return os.path.abspath(cand)
    return os.path.abspath(os.path.join(HERE, ".."))


DEFAULT_SKILLS = _default_skills()
TODAY = "2026-10-26"
failures = []


def sh(args, cwd):
    return subprocess.run([sys.executable, "-I"] + args, cwd=cwd, capture_output=True, text=True)


def step(title):
    print("\n" + "=" * 78 + "\n" + title + "\n" + "=" * 78)


def show(r, expect, label):
    out = (r.stdout + r.stderr).rstrip()
    print(out)
    ok = r.returncode == expect
    print("[exit %d, expected %d] %s" % (r.returncode, expect, "OK" if ok else "UNEXPECTED"))
    if not ok:
        failures.append("%s: exit %d, expected %d" % (label, r.returncode, expect))
    return out


def must_contain(text, needle, label):
    if needle not in text:
        failures.append("%s: output lacks %r" % (label, needle))
        print("MISSING EXPECTED TEXT: %r" % needle)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        fh.write(text)


SPEND = """tool,category,pricing,annual_cost,seats,active_users,features_used,features_total,renewal_date,notice_days
Bookly Pro,scheduling,per_seat,14400,12,5,4,22,2027-03-15,60
Paylane Payroll,payroll,flat,9000,,,2,40,2027-01-31,30
Ledgerly,accounting-ledger,flat,3600,,,10,30,2027-06-01,30
FormForge,forms,flat,3000,,,3,25,2027-02-10,30
MailPilot,email-marketing,flat,4000,,,9,15,2027-04-01,30
ChatBox,chat,flat,2400,10,9,8,10,2027-05-01,30
CloudNotes,notes,flat,1800,,,,,2027-08-01,30
"""

FEATURES = """feature,priority,usage,kind,effort_days,confirmed
Online booking page,must,daily,feature,5,yes
Staff availability,must,daily,feature,3,yes
Email reminders,must,daily,feature,1.5,yes
Calendar sync,should,daily,integration,2,yes
Payments at booking,should,weekly,integration,2.5,yes
SMS reminders,should,weekly,feature,1,yes
Recurring bookings,should,monthly,feature,2,yes
Intake forms,should,monthly,feature,1.5,yes
Reports,should,rarely,feature,3,yes
Group classes,could,rarely,feature,4,yes
Waitlist,could,never,feature,2,yes
Branded mobile app,could,never,feature,15,yes
Partner marketplace,must,daily,network,0,yes
Custom roles,should,unknown,feature,2,no
"""


def make_bookings():
    rnd = random.Random(7)
    services = ["Initial consult", "Follow-up", "Group class", "Assessment"]
    rows = []
    for i in range(1, 41):
        phone = "" if i % 9 == 0 else "07700 900%03d" % i
        rows.append({
            "Booking ID": "B%04d" % i,
            "Customer Email": "customer%03d@example.test" % i,
            "Phone": phone,
            "Service": rnd.choice(services),
            "Start": "2026-11-%02dT%02d:00:00Z" % (1 + i % 28, 9 + i % 8),
            "Price": "%.2f" % rnd.choice([45, 60, 75, 120]),
            "Notes": "" if i % 5 else "Prefers mornings",
            "Legacy Flag": "x" if i % 7 == 0 else "",
        })
    return rows


def write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow([r[h] for h in header])


MAPPING = """source_field,target_field,action,required,check
Booking ID,id,map,yes,
Customer Email,email,map,yes,
Phone,phone,map,no,
Service,service,map,yes,
Start,starts_at,derive,yes,
Price,price,map,yes,sum
Notes,notes,map,no,
Legacy Flag,,drop,no,
"""


def tokens(grey):
    return {"themes": {
        "light": {"colors": {"text": "#16212b", "muted": grey, "bg": "#ffffff", "primary": "#0f6f78",
                             "on-primary": "#ffffff"},
                  "pairs": [["text", "bg"], ["muted", "bg"], ["on-primary", "primary"]]},
        "dark": {"colors": {"text": "#e8eef2", "muted": "#a9b6c0", "bg": "#10181e", "primary": "#4fc3cf",
                            "on-primary": "#06222a"},
                 "pairs": [["text", "bg"], ["muted", "bg"], ["on-primary", "primary"]]}}}


def run_lean(S, work):
    sw = os.path.join(work, "swap")
    os.makedirs(os.path.join(sw, "migration"), exist_ok=True)
    os.makedirs(os.path.join(sw, "design"), exist_ok=True)
    print("Invented company: Harbour Studio Co. Working folder: %s" % work)
    sc = lambda skill, script: os.path.join(S, skill, "scripts", script)
    write(os.path.join(sw, "mode.txt"), "lean\n")

    # 1 AUDIT ---------------------------------------------------------------
    step("1. swap-audit: rank the subscriptions")
    write(os.path.join(sw, "spend.csv"), SPEND)
    out = show(sh([sc("swap-audit", "spend.py"), "swap/spend.csv", "--today", TODAY, "--json", "swap/audit.json"], work), 0, "audit")
    must_contain(out, "CANDIDATE | Bookly Pro", "audit")
    must_contain(out, "REGULATED | Paylane Payroll", "audit")
    must_contain(out, "NO-DATA | CloudNotes", "audit")
    audit = json.load(open(os.path.join(sw, "audit.json")))
    bookly = [t for t in audit["tools"] if t["tool"] == "Bookly Pro"][0]
    print("\nFirst swap chosen: Bookly Pro. Cancel-by date from the script: %s" % bookly["notice_deadline"])
    if bookly["notice_deadline"] != "2027-01-14":
        failures.append("cancel-by date wrong: %s" % bookly["notice_deadline"])

    # 3 SCOPE (recon wrote features.csv) ------------------------------------
    step("3. swap-scope: first run, one feature has unknown usage")
    write(os.path.join(sw, "features.csv"), FEATURES)
    out = show(sh([sc("swap-scope", "scope.py"), "swap/features.csv", "--json", "swap/scope.json"], work), 0, "scope-1")
    must_contain(out, "ESTIMATE INCOMPLETE", "scope-1")
    print("\n-- try to write the master list while a feature is on HOLD --")
    out = show(sh([sc("swap-scope", "scope.py"), "swap/features.csv", "--annotate", "swap/master.csv"], work), 1, "annotate-refused")
    must_contain(out, "refused", "annotate-refused")

    step("3b. swap-scope: a user answers 'Custom roles: rarely'. Rerun.")
    write(os.path.join(sw, "features.csv"), FEATURES.replace("Custom roles,should,unknown,feature,2,no", "Custom roles,should,rarely,feature,2,yes"))
    out = show(sh([sc("swap-scope", "scope.py"), "swap/features.csv", "--json", "swap/scope.json", "--annotate", "swap/master.csv"], work), 0, "scope-2")
    must_contain(out, "Partner marketplace: vendor-owned (network)", "scope-2")
    scope = json.load(open(os.path.join(sw, "scope.json")))
    raw = scope["effort_days_raw"]
    print("\neffort_days_raw from scope.json = %g (this is the figure that goes to swap-roi)" % raw)

    # 4 ROI forecast ----------------------------------------------------------
    step("4. swap-roi forecast: raw days from scope.json, price from audit.json")
    sub = bookly["annual_cost"]
    roi_args = [sc("swap-roi", "roi.py"), "--subscription", "%g" % sub, "--build-days", "%g" % raw, "--day-rate", "500",
                "--migration-cost", "800", "--run-cost", "600", "--maintenance-hours-month", "2", "--hourly-rate", "60",
                "--json", "swap/roi.json"]
    out = show(sh(roi_args, work), 0, "roi")
    must_contain(out, "Verdict: BUILD", "roi")

    step("4b. Same tool, but suppose it only cost 3,000 a year: the gate must say stop")
    out = show(sh([sc("swap-roi", "roi.py"), "--subscription", "3000", "--build-days", "%g" % raw, "--day-rate", "500",
                   "--migration-cost", "800", "--run-cost", "600", "--maintenance-hours-month", "2", "--hourly-rate", "60"], work), 1, "roi-keep")
    must_contain(out, "Verdict: KEEP SAAS", "roi-keep")

    # 5 DESIGN -----------------------------------------------------------------
    step("5. swap-design: a brand grey that looks fine but fails contrast")
    write(os.path.join(sw, "design", "tokens.json"), json.dumps(tokens("#999999"), indent=2))
    out = show(sh([sc("swap-design", "contrast.py"), "swap/design/tokens.json"], work), 1, "contrast-fail")
    must_contain(out, "FAIL  muted on bg", "contrast-fail")
    step("5b. swap-design: darker grey")
    write(os.path.join(sw, "design", "tokens.json"), json.dumps(tokens("#5a6670"), indent=2))
    show(sh([sc("swap-design", "contrast.py"), "swap/design/tokens.json", "--json", "swap/design/contrast.json"], work), 0, "contrast-pass")

    # 7 MIGRATE ----------------------------------------------------------------
    step("7. swap-migrate: rehearsal 1 deliberately loses data")
    header = ["Booking ID", "Customer Email", "Phone", "Service", "Start", "Price", "Notes", "Legacy Flag"]
    src = make_bookings()
    write_csv(os.path.join(sw, "migration", "old_export.csv"), header, src)
    write(os.path.join(sw, "migration", "mapping.csv"), MAPPING)
    thead = ["id", "email", "phone", "service", "starts_at", "price", "notes"]
    def tgt(r):
        return {"id": r["Booking ID"], "email": r["Customer Email"], "phone": r["Phone"], "service": r["Service"],
                "starts_at": r["Start"].replace("T", " ").replace("Z", ""), "price": r["Price"], "notes": r["Notes"]}
    bad = [tgt(r) for r in src if r["Booking ID"] != "B0040"]          # lost row
    for r in bad:
        if r["id"] == "B0004":
            r["phone"] = ""                                             # lost value
        if r["id"] == "B0010":
            r["email"] = "customer010-changed@example.test"                  # changed value
    write_csv(os.path.join(sw, "migration", "staging_1.csv"), thead, bad)
    out = show(sh([sc("swap-migrate", "mapcheck.py"), "swap/migration/mapping.csv", "--source", "swap/migration/old_export.csv",
                   "--target", "swap/migration/staging_1.csv", "--key", "Booking ID"], work), 1, "mapcheck-fail")
    for needle in ("FAIL  row count", "FAIL  no source key lost", "FAIL  no value lost: Phone -> phone",
                   "FAIL  values unchanged: Customer Email -> email", "FAIL  total matches: Price -> price"):
        must_contain(out, needle, "mapcheck-fail")
    for secret in ("customer010-changed@example.test", "customer010@example.test", "07700"):
        if secret in out:
            failures.append("mapcheck leaked a value: %r" % secret)
    print("\n(no customer value appears in that output: checked)")

    step("7b. swap-migrate: rehearsal 2, import fixed")
    good = [tgt(r) for r in src]
    write_csv(os.path.join(sw, "migration", "staging_2.csv"), thead, good)
    show(sh([sc("swap-migrate", "mapcheck.py"), "swap/migration/mapping.csv", "--source", "swap/migration/old_export.csv",
             "--target", "swap/migration/staging_2.csv", "--key", "Booking ID", "--json", "swap/mapcheck.json"], work), 0, "mapcheck-pass")

    # 9 DIFF ---------------------------------------------------------------------
    step("9. swap-diff: statuses as observed (build and test are represented by these files, not run here)")
    rows = list(csv.DictReader(open(os.path.join(sw, "master.csv"), encoding="utf-8")))
    state = {"Email reminders": "partial"}
    for r in rows:
        if r["in_scope"] == "yes":
            r["status"] = state.get(r["feature"], "done")
        if r["feature"] == "Reports":
            r["status"] = "dropped"
    with open(os.path.join(sw, "features.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    out = show(sh([sc("swap-diff", "parity.py"), "swap/features.csv"], work), 1, "parity-block")
    must_contain(out, "NOT SHIPPABLE", "parity-block")
    must_contain(out, "must-have not done: Email reminders", "parity-block")
    print("\n-- the partial must-have is fixed and re-observed --")
    for r in rows:
        if r["feature"] == "Email reminders":
            r["status"] = "done"
    with open(os.path.join(sw, "features.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    out = show(sh([sc("swap-diff", "parity.py"), "swap/features.csv", "--json", "swap/parity.json"], work), 0, "parity-pass")
    must_contain(out, "SHIPPABLE", "parity-pass")

    # 10 CUTOVER --------------------------------------------------------------------
    step("10. swap-cutover: preflight with an open S2 bug in the log")
    write(os.path.join(sw, "bugs.csv"),
          "id,severity,status,feature,summary,steps,found,fixed\n"
          "1,S2,open,Payments at booking,Refund shows wrong total,see test,2026-10-24,\n"
          "2,S3,open,Reports,Label typo,see test,2026-10-24,\n")
    write(os.path.join(sw, "cutover.md"),
          "# Cutover\nRollback: re-enable Bookly Pro from the final export, owner decides within 7 days\n"
          "Old tool kept until: 2027-01-10\n")
    pf = [sc("swap-cutover", "preflight.py"), "--dir", "swap", "--renewal", "2027-03-15", "--notice-days", "60",
          "--today", TODAY, "--json", "swap/preflight.json"]
    out = show(sh(pf, work), 1, "preflight-nogo")
    must_contain(out, "S1/S2 not fixed: 1 (S2, open)", "preflight-nogo")
    step("10b. swap-cutover: S2 fixed and retested, preflight again")
    write(os.path.join(sw, "bugs.csv"),
          "id,severity,status,feature,summary,steps,found,fixed\n"
          "1,S2,fixed,Payments at booking,Refund shows wrong total,see test,2026-10-24,2026-10-25\n"
          "2,S3,open,Reports,Label typo,see test,2026-10-24,\n")
    out = show(sh(pf, work), 0, "preflight-go")
    must_contain(out, "GO", "preflight-go")
    must_contain(out, "Last day to cancel without another term: 2027-01-14", "preflight-go")

    # 11 ROI actuals -------------------------------------------------------------------
    step("11. swap-roi actuals, 90 days later: build ran 3 days over, hosting cheaper")
    out = show(sh([sc("swap-roi", "roi.py"), "--subscription", "%g" % sub, "--build-days", "%g" % (raw + 3), "--day-rate", "500",
                   "--migration-cost", "800", "--run-cost", "480", "--maintenance-hours-month", "2", "--hourly-rate", "60",
                   "--json", "swap/roi-actuals.json"], work), 0, "roi-actuals")

    step("RESULT (lean track)")
    print("Files written under %s/swap/: %s" % (work, ", ".join(sorted(f for f in os.listdir(sw) if not os.path.isdir(os.path.join(sw, f))))))


def make_reviews():
    """INVENTED reviews of an invented product, on a reserved example domain. For demonstration only."""
    rnd = random.Random(11)
    rows = []
    sources = ["Review site A", "App store B", "Forum C"]
    pricing = ["Far too expensive once we added a fourth seat. Per seat pricing punishes small teams.",
               "The price doubled at renewal and nobody warned us.",
               "Overpriced for what a solo practitioner actually uses.",
               "We pay for twenty features and use three. Not worth the subscription."]
    reliability = ["Reminders failed to send twice last month and clients missed appointments.",
                   "The calendar sync keeps breaking and double books me.",
                   "It crashes when I open the week view on my phone."]
    support = ["Support took nine days to answer a billing question.",
               "No reply from customer service after three tickets."]
    usability = ["Setting up recurring bookings is confusing and takes far too many steps."]
    positive = ["Does what I need, booking page looks clean.", "Reminders save me hours every week.",
                "Easy to share my link and get booked."]
    i = 0

    def add(text, rating, src=None):
        nonlocal i
        i += 1
        s = src or sources[i % 3]
        rows.append({"source": s, "url": "https://%s.example.test/r/%03d" % (s.split()[0].lower(), i),
                     "rating": rating, "date": "2026-%02d-%02d" % (1 + i % 9, 1 + i % 27), "text": text})

    for k in range(14):
        add(pricing[k % len(pricing)] + " (%d)" % k, rnd.choice([1, 2]))
    for k in range(7):
        add(reliability[k % len(reliability)] + " (%d)" % k, rnd.choice([1, 2]))
    for k in range(5):
        add(support[k % len(support)] + " (%d)" % k, rnd.choice([1, 2]))
    for k in range(4):
        add(usability[0] + " (%d)" % k, rnd.choice([1, 2]))
    for k in range(7):
        add(positive[k % len(positive)] + " (%d)" % k, rnd.choice([4, 5]))
    rows.append({"source": "Forum C", "url": "", "rating": 1, "date": "", "text": "Awful price, trust me, everyone says so."})
    rows.append({"source": "Forum C", "url": "not a link", "rating": 1, "date": "", "text": "Too expensive and support is bad."})
    rows.append(dict(rows[0]))                                   # exact duplicate
    return rows


FULL_FEATURES = """feature,priority,usage,kind,effort_days,confirmed
Online booking page,must,daily,feature,6,yes
Staff availability,must,daily,feature,4,yes
Email reminders,must,daily,feature,2,yes
SMS reminders,should,weekly,feature,2,no
Calendar sync,should,daily,integration,4,yes
Payments at booking,should,weekly,integration,5,no
Recurring bookings,should,monthly,feature,4,no
Group classes,could,unknown,feature,6,no
Intake forms,should,monthly,feature,3,no
Reports,could,rarely,feature,5,no
Waitlist,could,unknown,feature,3,no
Fax reminders,could,never,feature,2,yes
Partner marketplace,must,daily,network,0,yes
Template library,should,weekly,content,0,yes
"""


def run_full(S, work):
    sw = os.path.join(work, "swap")
    prod = os.path.join(work, "product")
    os.makedirs(os.path.join(sw, "launch"), exist_ok=True)
    os.makedirs(os.path.join(prod, "src", "Timeloop"), exist_ok=True)
    print("INVENTED product to clone and sell: Timeloop (invented, timeloop.example.test). Working folder: %s" % work)
    print("The reviews below are invented for this demonstration and use a reserved example domain.")
    sc = lambda skill, script: os.path.join(S, skill, "scripts", script)
    write(os.path.join(sw, "mode.txt"), "full\n")

    step("F1. swap-market: reviews with links in, ranked complaints out")
    hdr = ["source", "url", "rating", "date", "text"]
    write_csv(os.path.join(sw, "reviews.csv"), hdr, make_reviews())
    out = show(sh([sc("swap-market", "reviews.py"), "swap/reviews.csv", "--json", "swap/reviews.json"], work), 0, "reviews")
    must_contain(out, "2 with no link, 1 duplicates (same text)", "reviews")
    must_contain(out, "3 web host(s)", "reviews")
    must_contain(out, "## pricing", "reviews")
    rep = json.load(open(os.path.join(sw, "reviews.json")))
    texts = {r["url"]: r["text"] for r in csv.DictReader(open(os.path.join(sw, "reviews.csv"), encoding="utf-8"))}
    quotes = [q for t in rep["themes"] for q in t["quotes"]]
    bad = [q for q in quotes if q["quote"] not in texts.get(q["url"], "")]
    print("\nchecked %d printed quotes against reviews.csv: %d not verbatim" % (len(quotes), len(bad)))
    if bad or not quotes:
        failures.append("a quote is not verbatim in its source review")
    if rep["themes"][0]["theme"] != "pricing":
        failures.append("top theme should be pricing, got %s" % rep["themes"][0]["theme"])

    step("F3. swap-scope --mode full: the vendor's network and content stay out, nothing else is held back")
    write(os.path.join(sw, "features.csv"), FULL_FEATURES)
    out = show(sh([sc("swap-scope", "scope.py"), "swap/features.csv", "--mode", "full", "--json", "swap/scope.json",
                   "--annotate", "swap/master.csv"], work), 0, "scope-full")
    must_contain(out, "MODE: full", "scope-full")
    must_contain(out, "Partner marketplace: vendor-owned (network)", "scope-full")
    must_contain(out, "Template library: vendor-owned (content)", "scope-full")
    must_contain(out, "Fax reminders: never used", "scope-full")
    must_contain(out, "HOLD (0)", "scope-full")
    raw = json.load(open(os.path.join(sw, "scope.json")))["effort_days_raw"]

    step("F4. swap-roi (sell mode): will the product pay back? Inputs are assumptions")
    flags = ["--price", "29", "--new-per-month", "12", "--churn", "0.04", "--cac", "90", "--cost-per-customer-month", "4",
             "--fixed-monthly", "300", "--build-days", "%g" % raw, "--day-rate", "500", "--launch-cost", "1500"]
    out = show(sh([sc("swap-roi", "sellmodel.py")] + flags + ["--json", "swap/sellmodel.json"], work), 0, "sellmodel")
    must_contain(out, "Verdict: MARGINAL", "sellmodel")
    print("\nMARGINAL means the owner must choose with both cases in front of them: base pays back in month 24, the stress case does not pay back in 36. The example records that choice and goes on.")
    step("F4b. Same product with a 9 a month price and 12 percent monthly churn: the gate must say stop")
    out = show(sh([sc("swap-roi", "sellmodel.py"), "--price", "9", "--new-per-month", "12", "--churn", "0.12", "--cac", "120",
                   "--cost-per-customer-month", "4", "--fixed-monthly", "300", "--build-days", "%g" % raw, "--day-rate", "500"], work), 1, "sellmodel-stop")
    must_contain(out, "Verdict: DON'T SELL", "sellmodel-stop")

    step("F5. swap-brand: sweep the product code for anything of the original")
    write(os.path.join(prod, "src", "app.js"), "import { TimeloopSync } from './sync';\n// ported from timeloop-client\nexport const name = 'Skyline';\n")
    write(os.path.join(prod, "src", "sync.js"), "export class TimeloopSync {}\n")
    write(os.path.join(prod, "src", "theme.css"), ":root{--brand:#112233;--ink:#222}\n")
    write(os.path.join(prod, "README.md"), "Compare with https://www.timeloop.example.test today.\n")
    write(os.path.join(prod, "src", "Timeloop", "index.js"), "export default 1;\n")
    sweep = [sc("swap-brand", "sweep.py"), "product", "--avoid", "Timeloop", "--domain", "timeloop.example.test",
             "--color", "#112233", "--exclude", "swap", "--json", "swap/sweep.json"]
    out = show(sh(sweep, work), 1, "sweep-dirty")
    for needle in ("NAME   src/app.js:1", "NAME   src/sync.js:1", "COLOUR src/theme.css:1", "DOMAIN README.md:1", "PATH   src/Timeloop:-", "NOT CLEAN"):
        must_contain(out, needle, "sweep-dirty")

    step("F9. swap-diff: statuses as observed (build, backend and test are represented by files here, not run)")
    rows = list(csv.DictReader(open(os.path.join(sw, "master.csv"), encoding="utf-8")))
    for r in rows:
        if r["in_scope"] == "yes":
            r["status"] = "partial" if r["feature"] == "Email reminders" else "done"
    def save(rows_):
        with open(os.path.join(sw, "features.csv"), "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows_[0].keys()))
            w.writeheader()
            w.writerows(rows_)
    save(rows)
    out = show(sh([sc("swap-diff", "parity.py"), "swap/features.csv"], work), 1, "parity-full-block")
    must_contain(out, "NOT SHIPPABLE", "parity-full-block")
    must_contain(out, "must-have not done: Email reminders", "parity-full-block")
    for r in rows:
        if r["feature"] == "Email reminders":
            r["status"] = "done"
    save(rows)
    show(sh([sc("swap-diff", "parity.py"), "swap/features.csv", "--json", "swap/parity.json"], work), 0, "parity-full-pass")

    step("F12. swap-launch: a title that breaks three rules, then a clean one")
    base = {"store": "apple", "original_names": ["Timeloop"]}
    write(os.path.join(sw, "launch", "listing-input.json"), json.dumps(dict(base, title="#1 Timeloop alternative", subtitle="Free booking, 50% off",
          description="The official way to book clients.", keywords="booking, scheduling,booking"), indent=2))
    out = show(sh([sc("swap-launch", "listing.py"), "swap/launch/listing-input.json", "--json", "swap/listing.json"], work), 1, "listing-bad")
    for needle in ("FAIL  ranking or superlative claim", "FAIL  the original name 'Timeloop' appears in title", "FAIL  price or promotion word", "FAIL  'official'"):
        must_contain(out, needle, "listing-bad")
    write(os.path.join(sw, "launch", "listing-input.json"), json.dumps(dict(base, title="Skyline Booking", subtitle="Flat-price scheduling",
          description="Share a link, let clients book a time, and keep one price however big your team gets.",
          keywords="appointments,reminders,calendar"), indent=2))
    show(sh([sc("swap-launch", "listing.py"), "swap/launch/listing-input.json", "--json", "swap/listing.json"], work), 0, "listing-good")

    step("F13. swap-deploy: preflight --mode full while the sweep is dirty and an S2 bug is open")
    write(os.path.join(sw, "bugs.csv"), "id,severity,status,feature,summary,steps,found,fixed\n1,S2,open,Payments at booking,Refund total wrong,see test,2026-10-24,\n")
    write(os.path.join(sw, "deploy.md"), "# Deploy\nRollback: redeploy the previous release and pause new sign-ups\nDomain: skyline.example.test\n")
    pf = [sc("swap-deploy", "preflight.py"), "--mode", "full", "--dir", "swap", "--json", "swap/preflight.json"]
    out = show(sh(pf, work), 1, "deploy-nogo")
    must_contain(out, "FAIL  nothing of the original is left", "deploy-nogo")
    must_contain(out, "FAIL  no open S1 or S2 bugs", "deploy-nogo")
    must_contain(out, "FAIL  the owner's choice on a MARGINAL forecast is recorded", "deploy-nogo")

    step("F13b. The leftovers are replaced, the S2 is fixed, the sweep is rerun, the owner records the MARGINAL choice, preflight again")
    write(os.path.join(prod, "src", "app.js"), "import { SkylineSync } from './sync';\nexport const name = 'Skyline';\n")
    write(os.path.join(prod, "src", "sync.js"), "export class SkylineSync {}\n")
    write(os.path.join(prod, "src", "theme.css"), ":root{--brand:#0f6f78;--ink:#222}\n")
    write(os.path.join(prod, "README.md"), "Skyline: flat-price scheduling.\n")
    shutil.rmtree(os.path.join(prod, "src", "Timeloop"))
    out = show(sh(sweep, work), 0, "sweep-clean")
    must_contain(out, "CLEAN", "sweep-clean")
    write(os.path.join(sw, "bugs.csv"), "id,severity,status,feature,summary,steps,found,fixed\n1,S2,fixed,Payments at booking,Refund total wrong,see test,2026-10-24,2026-10-25\n")
    write(os.path.join(sw, "deploy.md"), "# Deploy\nRollback: redeploy the previous release and pause new sign-ups\nDomain: skyline.example.test\n"
          "Marginal approved by: the owner (invented example) on 2026-10-26, with a 12-month review\n")
    out = show(sh(pf, work), 0, "deploy-go")
    must_contain(out, "GO", "deploy-go")

    step("RESULT (full track)")
    print("Files written under %s/swap/: %s" % (work, ", ".join(sorted(f for f in os.listdir(sw) if not os.path.isdir(os.path.join(sw, f))))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skills-dir", default=DEFAULT_SKILLS)
    ap.add_argument("--workdir", default=None)
    ap.add_argument("--track", choices=("lean", "full", "both"), default="both")
    a = ap.parse_args()
    S = os.path.abspath(a.skills_dir)
    if a.workdir:
        base = os.path.abspath(a.workdir)
        if os.path.exists(base) and (not os.path.isdir(base) or os.listdir(base)):
            print("error: --workdir %s exists and is not an empty folder. The example overwrites and deletes files "
                  "inside its working folder, so it only runs in a folder it can own. Give a new or empty folder." % base,
                  file=sys.stderr)
            return 2
        os.makedirs(base, exist_ok=True)
    else:
        base = tempfile.mkdtemp(prefix="swap-example-")
    if a.track in ("lean", "both"):
        run_lean(S, os.path.join(base, "lean") if a.track == "both" else base)
    if a.track in ("full", "both"):
        run_full(S, os.path.join(base, "full") if a.track == "both" else base)
    step("RESULT")
    if failures:
        print("EXAMPLE FAILED:")
        for f in failures:
            print(" - " + f)
        return 1
    print("EXAMPLE PASSED (%s): every gate stopped what it should stop and passed what it should pass." % a.track)
    return 0


if __name__ == "__main__":
    sys.exit(main())
