#!/usr/bin/env python3
"""Rank a company's software subscriptions by how much of what it pays for goes unused.

Standard library only. Never touches the network.

Usage:
  spend.py spend.csv [--min-cost 1000] [--today YYYY-MM-DD] [--json out.json]

CSV columns
  required: tool, annual_cost
  optional: category, pricing (per_seat|flat), seats, active_users,
            features_used, features_total, renewal_date (YYYY-MM-DD), notice_days

Verdicts (thresholds are flags, not hidden constants)
  REGULATED   category is payroll, payments, identity, tax, banking or compliance:
              owning it adds liability, so it is never offered as a swap.
  NEEDS-CATEGORY  no category given. The regulated-tool rule can only work on a category you state, so a tool
              with none is never offered as a swap until you classify it (is it payroll, payments, identity, tax,
              banking or compliance?). The script does not guess a category from a tool's name.
  NO-DATA     features_used / features_total missing: cannot judge, never a candidate.
  CANDIDATE   annual_cost >= min-cost and utilisation <= --cand-util (default 0.35)
  LOOK        annual_cost >= min-cost and (utilisation <= --look-util (default 0.60)
              or idle seat share >= 0.30 on per-seat pricing)
  KEEP        everything else, including anything under min-cost

Exit codes: 0 ok, 2 bad input.
"""
import argparse
import csv
import datetime
import json
import os
import sys
import tempfile

REGULATED = {"payroll", "payments", "payment", "identity", "tax", "banking", "compliance", "accounting-ledger"}
REQUIRED = ("tool", "annual_cost")
COUNT_COLUMNS = ("seats", "active_users", "features_used", "features_total", "notice_days")


class InputError(Exception):
    pass


def _num(row, key, line, allow_blank=True, integer=False):
    raw = (row.get(key) or "").strip().replace(",", "").lstrip("$")
    if raw == "":
        if allow_blank:
            return None
        raise InputError("line %d: '%s' is required" % (line, key))
    try:
        v = float(raw)
    except ValueError:
        raise InputError("line %d: '%s' is not a number: %r" % (line, key, raw))
    if v != v or v in (float("inf"), float("-inf")):
        raise InputError("line %d: '%s' is not finite" % (line, key))
    if v < 0:
        raise InputError("line %d: '%s' is negative" % (line, key))
    if key == "notice_days" and v > 3650:
        raise InputError("line %d: 'notice_days' is over 3650 (ten years)" % line)
    if key in COUNT_COLUMNS:
        if v != int(v):
            raise InputError("line %d: '%s' must be a whole number, got %s" % (line, key, raw))
        if v > 1e9:
            raise InputError("line %d: '%s' is implausibly large" % (line, key))
    return v


def _date(row, key, line):
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        raise InputError("line %d: '%s' must be YYYY-MM-DD, got %r" % (line, key, raw))


def load(path):
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        raise InputError("cannot read %s: %s" % (path, e))
    try:
        with fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                raise InputError("empty file")
            names = [n.strip() for n in reader.fieldnames]
            reader.fieldnames = names
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise InputError("duplicate column names: the last one would silently win")
            for col in REQUIRED:
                if col not in names:
                    raise InputError("missing required column '%s'" % col)
            rows, seen = [], set()
            for i, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    raise InputError("line %d has a different number of cells than the header" % i)
                if not any((v or "").strip() for v in row.values() if not isinstance(v, list)):
                    continue
                tool = (row.get("tool") or "").strip()
                if not tool:
                    raise InputError("line %d: 'tool' is blank" % i)
                if tool.lower() in seen:
                    raise InputError("line %d: duplicate tool %r" % (i, tool))
                seen.add(tool.lower())
                rec = {
                    "tool": tool,
                    "category": (row.get("category") or "").strip().lower(),
                    "pricing": (row.get("pricing") or "").strip().lower(),
                    "annual_cost": _num(row, "annual_cost", i, allow_blank=False),
                    "seats": _num(row, "seats", i),
                    "active_users": _num(row, "active_users", i),
                    "features_used": _num(row, "features_used", i),
                    "features_total": _num(row, "features_total", i),
                    "renewal_date": _date(row, "renewal_date", i),
                    "notice_days": _num(row, "notice_days", i),
                }
                if rec["pricing"] not in ("", "per_seat", "flat"):
                    raise InputError("line %d: 'pricing' must be per_seat or flat, got %r" % (i, rec["pricing"]))
                if rec["features_total"] is not None and rec["features_used"] is not None:
                    if rec["features_total"] == 0:
                        raise InputError("line %d: features_total is 0" % i)
                    if rec["features_used"] > rec["features_total"]:
                        raise InputError("line %d: features_used exceeds features_total" % i)
                if rec["seats"] is not None and rec["active_users"] is not None and rec["active_users"] > rec["seats"]:
                    raise InputError("line %d: active_users exceeds seats" % i)
                rows.append(rec)
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError("spend file is not readable CSV text: %s" % e)
    if not rows:
        raise InputError("no data rows")
    return rows


def assess(rec, min_cost, cand_util, look_util, today):
    util = None
    if rec["features_used"] is not None and rec["features_total"]:
        util = rec["features_used"] / rec["features_total"]
    idle_share = None
    if rec["pricing"] == "per_seat" and rec["seats"] and rec["active_users"] is not None:
        idle_share = 1.0 - rec["active_users"] / rec["seats"]
    cost_per_user = None
    if rec["active_users"]:
        cost_per_user = rec["annual_cost"] / rec["active_users"]
    unused = rec["annual_cost"] * (1.0 - util) if util is not None else None

    if rec["category"] in REGULATED:
        verdict, why = "REGULATED", "regulated category (%s): owning it adds liability" % rec["category"]
    elif not rec["category"]:
        verdict, why = "NEEDS-CATEGORY", "no category given: classify it (payroll, payments, identity, tax, banking, compliance or other) before it can be a candidate"
    elif util is None:
        verdict, why = "NO-DATA", "features used / total not given: cannot judge"
    elif rec["annual_cost"] < min_cost:
        verdict, why = "KEEP", "under the %.0f minimum: build cost will not pay back" % min_cost
    elif util <= cand_util:
        verdict, why = "CANDIDATE", "uses %.0f%% of features at %.0f a year" % (util * 100, rec["annual_cost"])
    elif util <= look_util or (idle_share is not None and idle_share >= 0.30):
        verdict, why = "LOOK", "uses %.0f%% of features%s" % (
            util * 100, "; %.0f%% of seats idle" % (idle_share * 100) if idle_share is not None else "")
    else:
        verdict, why = "KEEP", "uses %.0f%% of features" % (util * 100)

    renewal = {"days_to_renewal": None, "notice_deadline": None, "days_to_notice_deadline": None, "flag": ""}
    if rec["renewal_date"]:
        renewal["days_to_renewal"] = (rec["renewal_date"] - today).days
        if rec["notice_days"] is not None:
            try:
                dl = rec["renewal_date"] - datetime.timedelta(days=int(rec["notice_days"]))
            except OverflowError:
                raise InputError("renewal_date and notice_days give a date out of range for %s" % rec["tool"])
            renewal["notice_deadline"] = dl.isoformat()
            renewal["days_to_notice_deadline"] = (dl - today).days
            if renewal["days_to_notice_deadline"] < 0:
                renewal["flag"] = "notice window missed: auto-renews, plan for the cycle after"
            elif renewal["days_to_notice_deadline"] <= 90:
                renewal["flag"] = "notice deadline within 90 days"
        elif renewal["days_to_renewal"] < 0:
            renewal["flag"] = "renewal date is in the past: confirm the real date"
    return {
        "tool": rec["tool"], "category": rec["category"], "annual_cost": rec["annual_cost"],
        "utilisation": util, "idle_seat_share": idle_share,
        "cost_per_active_user": cost_per_user, "unused_value": unused,
        "verdict": verdict, "reason": why, **renewal,
    }


ORDER = {"CANDIDATE": 0, "LOOK": 1, "NEEDS-CATEGORY": 2, "NO-DATA": 3, "REGULATED": 4, "KEEP": 5}


def run(rows, min_cost, cand_util, look_util, today, currency=None):
    out = [assess(r, min_cost, cand_util, look_util, today) for r in rows]
    for a in out:
        for k in ("cost_per_active_user", "unused_value", "utilisation", "idle_seat_share"):
            if a[k] is not None and (a[k] != a[k] or a[k] in (float("inf"), float("-inf"))):
                raise InputError("%s: %s overflowed; check the units" % (a["tool"], k))
    out.sort(key=lambda a: (ORDER[a["verdict"]], -(a["unused_value"] or 0), -a["annual_cost"]))
    total = sum(a["annual_cost"] for a in out)
    if total != total or total == float("inf"):
        raise InputError("the annual costs are so large that their total overflowed; check the units")
    cand = [a for a in out if a["verdict"] == "CANDIDATE"]
    look = [a for a in out if a["verdict"] == "LOOK"]
    return {
        "currency": currency or "not stated",
        "currency_note": "amounts are in whatever currency the input file uses; this report does not assume one",
        "today": today.isoformat(),
        "thresholds": {"min_cost": min_cost, "candidate_util": cand_util, "look_util": look_util},
        "total_annual_spend": total,
        "candidate_spend": sum(a["annual_cost"] for a in cand),
        "look_spend": sum(a["annual_cost"] for a in look),
        "unused_value_in_candidates": sum(a["unused_value"] or 0 for a in cand),
        "no_data_count": sum(1 for a in out if a["verdict"] == "NO-DATA"),
        "tools": out,
    }


def fmt(report):
    L = []
    L.append("| verdict | tool | annual | feature use | idle seats | per active user | notice deadline | why |")
    L.append("|---|---|---|---|---|---|---|---|")
    for a in report["tools"]:
        pct = lambda v: "n/a" if v is None else "%.0f%%" % (v * 100)
        cpu = "n/a" if a["cost_per_active_user"] is None else "%.0f" % a["cost_per_active_user"]
        dl = a["notice_deadline"] or "n/a"
        if a["flag"]:
            dl += " (%s)" % a["flag"]
        L.append("| %s | %s | %.0f | %s | %s | %s | %s | %s |" % (
            a["verdict"], a["tool"], a["annual_cost"], pct(a["utilisation"]),
            pct(a["idle_seat_share"]), cpu, dl, a["reason"]))
    L.append("")
    L.append("Total annual spend: %.0f (currency: %s)" % (report["total_annual_spend"], report["currency"]))
    L.append("Candidates: %.0f a year (of which unused by feature count: %.0f)" % (
        report["candidate_spend"], report["unused_value_in_candidates"]))
    L.append("Look closer: %.0f a year" % report["look_spend"])
    nc = [a["tool"] for a in report["tools"] if a["verdict"] == "NEEDS-CATEGORY"]
    if nc:
        L.append("NEEDS-CATEGORY: %d tool(s) have no category, so they cannot be offered as swaps yet." % len(nc))
    if report["no_data_count"]:
        L.append("NO-DATA: %d tool(s) cannot be judged until feature use is counted." % report["no_data_count"])
    L.append("Feature use is a count of features used out of features offered, not a measure of how much "
             "each feature matters. Confirm with the people who use the tool before acting.")
    return "\n".join(L)


def check_destination(path, inputs=()):
    """Refuse to write a report over anything that is not a plain report file of our own: a symlink, a device or
    pipe, or any input file (the same file under another name, including a hard link, counts)."""
    if os.path.islink(path):
        raise OSError("%s is a symlink: refusing to write through it" % path)
    if os.path.exists(path):
        if not os.path.isfile(path):
            raise OSError("%s exists and is not a regular file" % path)
        for i in inputs:
            if i and os.path.exists(i) and os.path.samefile(i, path):
                raise OSError("%s is one of the input files: refusing to overwrite it" % path)


def safe_write(path, text, inputs=()):
    """Write text to path without touching anything that is not ours: validate the destination, stage in the same
    folder, then replace, so a failure leaves any existing file as it was."""
    check_destination(path, inputs)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".swap-report-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv")
    p.add_argument("--min-cost", type=float, default=1000.0)
    p.add_argument("--cand-util", type=float, default=0.35)
    p.add_argument("--look-util", type=float, default=0.60)
    p.add_argument("--today", default=None)
    p.add_argument("--currency", default=None, help="label for the amounts, e.g. USD; never assumed")
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    try:
        today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
    except ValueError:
        print("error: --today must be YYYY-MM-DD", file=sys.stderr)
        return 2
    for name in ("min_cost", "cand_util", "look_util"):
        v = getattr(a, name)
        if v != v or v < 0 or v == float("inf"):
            print("error: --%s must be a finite non-negative number" % name.replace("_", "-"), file=sys.stderr)
            return 2
    if a.cand_util > 1 or a.look_util > 1:
        print("error: --cand-util and --look-util are fractions from 0 to 1", file=sys.stderr)
        return 2
    if a.cand_util > a.look_util:
        print("error: --cand-util cannot exceed --look-util", file=sys.stderr)
        return 2
    try:
        rows = load(a.csv)
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    try:
        report = run(rows, a.min_cost, a.cand_util, a.look_util, today, a.currency)
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print(fmt(report))
    if a.json:
        try:
            text = json.dumps(report, indent=2, allow_nan=False)      # serialise first: a failure leaves no partial file
            safe_write(a.json, text, [a.csv])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
