#!/usr/bin/env python3
"""Go / no-go gate before switching off the old tool, or before putting a product you sell live.

Standard library only. Never touches the network. It reads the files the earlier
swap skills wrote and refuses to say GO unless every one of them says it is safe.

Usage:
  preflight.py [--mode lean|full] [--dir swap] [--renewal YYYY-MM-DD --notice-days N] [--today YYYY-MM-DD] [--json out.json]

Freshness: parity.json records a hash of the features.csv it scored, and the gate re-hashes <dir>/features.csv; a
changed list means a stale score and a NO-GO. The other evidence (tests, sweep, listing, forecast) carries no such
binding: this gate checks that the files agree with each other, and re-running the producing scripts right before
the gate is the only way to know they are current.

Every run first checks that <dir>/mode.txt exists and says the same as --mode, so evidence
from one track cannot satisfy the other. Each JSON artifact must also have the fields and types
the producing script writes, finite numbers, and a verdict that agrees with its own numbers
(a score of 0 marked shippable, a failed nested check under passed:true, a BUILD verdict whose
stress case never pays back, all fail). This cannot authenticate evidence: a determined person can
still write a consistent fake. It rejects stubs and contradictions, which is how honest mistakes look.

A MARGINAL verdict (from swap-roi) needs the owner's recorded choice: the plan file must carry a
non-empty 'Marginal approved by:' line.

Lean checks (all must pass for GO)
  1. parity.json       from swap-diff:    "shippable" is true and "reasons" is empty
  2. mapcheck.json     from swap-migrate: "passed" and "key_checked" are both true (a run without a key proves nothing)
  3. bugs.csv          from swap-test:    no unfixed S1 or S2 (columns id,severity,status; status open|fixed|accepted;
                                          S1 and S2 can never be 'accepted')
  4. roi.json          from swap-roi:     verdict is BUILD or MARGINAL (not KEEP SAAS)
  5. cutover.md        from swap-cutover: has non-empty 'Rollback:' and 'Old tool kept until:' (YYYY-MM-DD) lines
  6. design/contrast.json (only if present): "passed" is true

--mode full is the gate before putting a product you will sell live (swap-deploy). All required:
  1. parity.json      as above
  2. bugs.csv         as above
  3. sellmodel.json   from swap-roi: verdict is SELL or MARGINAL (not DON'T SELL)
  4. sweep.json       from swap-brand: no hits, and no unscanned files unless you accepted them ("skipped_accepted")
  5. listing.json     from swap-launch: "passed" is true and "fails" is empty
  6. deploy.md        non-empty 'Rollback:' and 'Domain:' lines
  7. design/contrast.json (only if present): "passed" is true
No migration check and no renewal guard in full mode: there is no old tool to leave.

Renewal guard (reported, never blocks): with --renewal and --notice-days (0 to 3650) it prints the
last day you can cancel without paying another term, and warns if that day has passed
or is within 30 days. Without them it warns that the cancel date is unknown.

Exit codes: 0 GO, 1 NO-GO, 2 bad input.
"""
import argparse
import csv
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile

NUM = (int, float)


def _is(v, kind):
    if kind is bool:
        return isinstance(v, bool)
    if kind is int:
        return isinstance(v, int) and not isinstance(v, bool)
    if kind == NUM:
        return isinstance(v, NUM) and not isinstance(v, bool)
    return isinstance(v, kind)


SCHEMA = {
    "parity.json": {"shippable": bool, "score": NUM, "reasons": list, "threshold": NUM, "in_scope_count": int,
                    "must_gaps": list, "contradictions": list, "input_sha256": str},
    "mapcheck.json": {"passed": bool, "key_checked": bool, "source_rows": int, "target_rows": int, "checks": list},
    "roi.json": {"verdict": str, "base": dict, "stress": dict, "payback_limit_months": NUM},
    "sellmodel.json": {"verdict": str, "unit_economics": dict, "base": dict, "stress": dict, "payback_limit_months": NUM, "assumptions": dict},
    "sweep.json": {"passed": bool, "files_scanned": int, "hits": list, "skipped": list},
    "listing.json": {"passed": bool, "store": str, "fails": list},
    "contrast.json": {"passed": bool, "results": list},
}


def _finite(v):
    return isinstance(v, NUM) and not isinstance(v, bool) and v == v and v not in (float("inf"), float("-inf"))


def _pb(v):
    """A payback in months is None (never) or a whole number from 1 to 1200."""
    return v is None or (isinstance(v, int) and not isinstance(v, bool) and 1 <= v <= 1200)


def validate(name, d):
    """Cross-field checks: the verdict must follow from the numbers beside it. Returns a reason or None."""
    if name == "parity.json":
        if not _finite(d["score"]) or not (0 <= d["score"] <= 100):
            return "score is not a number from 0 to 100"
        if d["shippable"]:
            if d["contradictions"]:
                return "marked shippable with contradictions listed"
            if not _finite(d.get("threshold")) or d["score"] < d["threshold"]:
                return "marked shippable but the score is under its own threshold"
            if not isinstance(d.get("in_scope_count"), int) or d["in_scope_count"] < 1:
                return "marked shippable with nothing in scope"
            if d.get("must_gaps"):
                return "marked shippable with must-have gaps listed"
        bp = d["by_priority"] if isinstance(d.get("by_priority"), dict) else None
        if bp is None or set(bp) != {"must", "should", "could"}:
            return "the per-priority breakdown is missing"
        total = 0
        for k, g in bp.items():
            if not isinstance(g, dict) or not all(isinstance(g.get(f), int) and not isinstance(g.get(f), bool) and g[f] >= 0
                                                  for f in ("total", "done", "partial", "gaps")):
                return "breakdown for %s is malformed" % k
            if g["total"] != g["done"] + g["partial"] + g["gaps"]:
                return "breakdown for %s does not add up" % k
            total += g["total"]
        if d["in_scope_count"] != total:
            return "in_scope_count disagrees with the breakdown"
        weights = {"must": 3, "should": 2, "could": 1}
        denom = sum(weights[k] * bp[k]["total"] for k in bp)
        earned = sum(weights[k] * (bp[k]["done"] + 0.5 * bp[k]["partial"]) for k in bp)
        recomputed = (earned / denom * 100.0) if denom else 0.0
        if abs(recomputed - d["score"]) > 1e-6:
            return "the score (%s) does not follow from the breakdown (which gives %.4f)" % (d["score"], recomputed)
        if d["shippable"] and (bp["must"]["done"] != bp["must"]["total"] or bp["must"]["total"] == 0 and d["in_scope_count"] == 0):
            return "marked shippable but the breakdown shows must-haves that are not done"
    elif name == "mapcheck.json":
        if not d["checks"] or not all(isinstance(c, dict) and isinstance(c.get("pass"), bool) for c in d["checks"]):
            return "checks are missing or malformed"
        if d["source_rows"] < 1 or d["target_rows"] < 1:
            return "a migration of zero rows proves nothing"
        names = [c.get("check") for c in d["checks"]]
        required = ["row count", "keys are unique", "keys are never blank", "no unexpected keys in target"]
        missing = [n for n in required if n not in names]
        if "no source key lost" not in names and "no source key lost beyond the allowed drops" not in names:
            missing.append("no source key lost")
        if missing:
            return "mandatory migration checks are absent (%s): this is not a keyed row-by-row reconciliation" % ", ".join(missing)
        counts = [c for c in d["checks"] if c.get("check") == "row count"]
        if len(counts) != 1 or not isinstance(counts[0].get("detail"), str):
            return "there is no single 'row count' check to compare the row totals against"
        m = re.search(r"source (\d+), deliberately not migrated (\d+), expected (\d+), target (\d+)\s*$", counts[0]["detail"])
        if not m:
            return "the row-count check has an unreadable detail line"
        src, dropped, expected, tgt = (int(g) for g in m.groups())
        if src != d["source_rows"] or tgt != d["target_rows"]:
            return "source_rows/target_rows disagree with what the row-count check recorded"
        if expected != src - dropped:
            return "the row-count check's expected total is not source minus the deliberate drops"
        if counts[0]["pass"] != (tgt == expected):
            return "the row-count check's pass flag contradicts its own numbers"
        if d["passed"] and not all(c["pass"] for c in d["checks"]):
            return "marked passed with a failed check inside it"
        if d["passed"] and not d["key_checked"]:
            return "marked passed without matching rows by a key"
    elif name == "roi.json":
        for case in ("base", "stress"):
            c = d[case]
            if not _finite(c.get("net_at_horizon")) or not _finite(c.get("build_total")) or c["build_total"] < 0 \
                    or "payback_months" not in c or not _pb(c["payback_months"]):
                return "%s case is missing its numbers or they are out of range" % case
        if not _finite(d.get("payback_limit_months")) or not (0 < d["payback_limit_months"] <= 1200):
            return "payback limit is missing or out of range"
        limit = d["payback_limit_months"]
        spb, bpb = d["stress"]["payback_months"], d["base"]["payback_months"]
        if spb is not None and spb <= limit and d["stress"]["net_at_horizon"] > 0:
            expected = "BUILD"
        elif bpb is not None:
            expected = "MARGINAL"
        else:
            expected = "KEEP SAAS"
        if d["verdict"] != expected:
            return "verdict %r does not follow from its own numbers (they say %s)" % (d["verdict"], expected)
    elif name == "sellmodel.json":
        ue, base, stress = d["unit_economics"], d["base"], d["stress"]
        for key in ("margin_per_customer_month", "min_ltv_to_cac"):
            if not _finite(ue.get(key)):
                return "unit_economics.%s is missing" % key
        if ue["min_ltv_to_cac"] < 0 or not (ue.get("ltv_to_cac") is None or (_finite(ue["ltv_to_cac"]) and 0 <= ue["ltv_to_cac"] <= 1e9)):
            return "ltv_to_cac must be absent or a believable number from 0 to a billion"
        for case, c in (("base", base), ("stress", stress)):
            if not _finite(c.get("net_at_horizon")) or "payback_months" not in c or not _pb(c["payback_months"]):
                return "%s case is missing its numbers or they are out of range" % case
        if not _finite(d.get("payback_limit_months")) or not (0 < d["payback_limit_months"] <= 1200):
            return "payback limit is missing or out of range"
        if not isinstance(d.get("assumptions"), dict) or not d["assumptions"]:
            return "assumptions are missing (the forecast is not reproducible)"
        limit, ratio = d["payback_limit_months"], ue.get("ltv_to_cac")
        spb, bpb = stress["payback_months"], base["payback_months"]
        allowed = set()
        for r in [ratio]:                                  # the producer stores the exact ratio
            if ue["margin_per_customer_month"] <= 0 or bpb is None:
                allowed.add("DON'T SELL")
            elif spb is not None and spb <= limit and r is not None and r >= ue["min_ltv_to_cac"]:
                allowed.add("SELL")
            else:
                allowed.add("MARGINAL")
        if d["verdict"] not in allowed:
            return "verdict %r does not follow from its own numbers (they say %s)" % (d["verdict"], "/".join(sorted(allowed)))
    elif name == "sweep.json":
        if d["files_scanned"] < 1:
            return "no file was scanned: an empty scan certifies nothing"
        unscanned = bool(d["skipped"]) and d.get("skipped_accepted") is not True
        if d["passed"] and (d["hits"] or unscanned):
            return "marked passed with hits or unaccepted unscanned files"
    elif name == "listing.json":
        if d["store"] not in ("apple", "google", "web"):
            return "store must be apple, google or web"
        if d["passed"] and d["fails"]:
            return "marked passed with failures listed"
    elif name == "contrast.json":
        if not d["results"] or not all(isinstance(r, dict) and isinstance(r.get("pass"), bool) for r in d["results"]):
            return "results are missing or malformed"
        for r in d["results"]:
            if not (_finite(r.get("ratio")) and _finite(r.get("min")) and 1 <= r["min"] <= 21 and 1 <= r["ratio"] <= 21):
                return "a result has a missing or impossible contrast ratio or minimum"
            if abs(r["ratio"] - r["min"]) > 0.006 and r["pass"] != (r["ratio"] >= r["min"]):
                return "a result's pass flag contradicts its own ratio and minimum"
        if d["passed"] and not all(r["pass"] for r in d["results"]):
            return "marked passed with a failing pair inside it"
        if d["passed"] != all(r["pass"] for r in d["results"]):
            return "passed disagrees with the results"
    return None


def load_artifact(path, name):
    """Return (dict, None) or (None, reason). Checks presence, JSON, and the fields the producer writes."""
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return None, "not found"
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return None, "unreadable: %s" % e
    if not isinstance(d, dict):
        return None, "not a JSON object"
    for field, kind in SCHEMA[name].items():
        if field not in d:
            return None, "missing field '%s' (not written by its script?)" % field
        if not _is(d[field], kind):
            return None, "field '%s' has the wrong type" % field
    try:
        bad = validate(name, d)
    except (TypeError, KeyError, ValueError, AttributeError, IndexError, OverflowError):
        bad = "has a malformed nested structure"
    if bad:
        return None, "is inconsistent: " + bad
    return d, None


def check_mode(dir_, mode):
    try:
        with open(os.path.join(dir_, "mode.txt"), encoding="utf-8") as fh:
            said = fh.read().strip().lower()
    except FileNotFoundError:
        return False, "mode.txt not found: write '%s' or 'full' in it (the track you are on)" % "lean"
    except (OSError, UnicodeDecodeError) as e:
        return False, "mode.txt unreadable: %s" % e
    if said != mode:
        return False, "mode.txt says %r but this gate was run with --mode %s: evidence from one track cannot clear the other" % (said, mode)
    return True, "track is %s" % mode


def check_bugs(path):
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh))
    except FileNotFoundError:
        return False, "bugs.csv not found: run swap-test"
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        return False, "bugs.csv unreadable: %s" % e
    if not rows:
        return False, "bugs.csv is empty: a test run with zero logged bugs still writes the header"
    header = [h.strip() for h in rows[0]]
    if len(set(header)) != len(header):
        return False, "bugs.csv has duplicate column names: the last one would silently win"
    for c in ("id", "severity", "status"):
        if c not in header:
            return False, "bugs.csv is missing column '%s'" % c
    ix = {c: header.index(c) for c in ("id", "severity", "status")}
    blocking, total, open_low = [], 0, 0
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(header):
            return False, "bugs.csv line %d has %d cells but the header has %d" % (n, len(r), len(header))
        total += 1
        sev, st = r[ix["severity"]].strip().upper(), r[ix["status"]].strip().lower()
        if sev not in ("S1", "S2", "S3", "S4"):
            return False, "bugs.csv line %d: severity must be S1 to S4, got %r" % (n, sev)
        if st not in ("open", "fixed", "accepted"):
            return False, "bugs.csv line %d: status must be open, fixed or accepted, got %r" % (n, st)
        if sev in ("S1", "S2") and st != "fixed":
            blocking.append((r[ix["id"]].strip() or "?") + " (%s, %s)" % (sev, st))
        elif st == "open":
            open_low += 1
    if blocking:
        return False, "S1/S2 not fixed: " + ", ".join(blocking)
    return True, "%d logged, no S1/S2 unfixed, %d lower-severity still open" % (total, open_low)


def _plan_lines(path, fname):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read(), None
    except FileNotFoundError:
        return None, "%s not found: write the plan first" % fname
    except (OSError, UnicodeDecodeError) as e:
        return None, "%s unreadable: %s" % (fname, e)


def _line(text, label):
    return re.search(r"^[ \t]*(?:[-*][ \t]*)?" + label + r":[ \t]*(\S[^\n]*)$", text, re.M | re.I)


def check_cutover(path, today):
    text, err = _plan_lines(path, "cutover.md")
    if err:
        return False, err
    rb = _line(text, "Rollback")
    ok = re.search(r"^[ \t]*(?:[-*][ \t]*)?Old tool kept until:[ \t]*(\d{4}-\d{2}-\d{2})[ \t]*$", text, re.M | re.I)
    if not rb:
        return False, "cutover.md has no non-empty 'Rollback:' line"
    if not ok:
        return False, "cutover.md has no 'Old tool kept until: YYYY-MM-DD' line"
    try:
        until = datetime.date.fromisoformat(ok.group(1))
    except ValueError:
        return False, "'Old tool kept until' is not a real date: %s" % ok.group(1)
    if until < today:
        return False, "'Old tool kept until' (%s) is already in the past: there is no overlap left to roll back into" % until
    return True, "rollback written; old tool kept until %s" % ok.group(1)


def check_deploy(path):
    text, err = _plan_lines(path, "deploy.md")
    if err:
        return False, err
    rb, dm = _line(text, "Rollback"), _line(text, "Domain")
    if not rb:
        return False, "deploy.md has no non-empty 'Rollback:' line"
    if not dm:
        return False, "deploy.md has no non-empty 'Domain:' line"
    return True, "rollback written; domain %s" % dm.group(1).strip()


def check_marginal(plan_path, verdict):
    """MARGINAL needs the owner's recorded choice. Other verdicts need nothing here."""
    if verdict != "MARGINAL":
        return None
    text, err = _plan_lines(plan_path, os.path.basename(plan_path))
    if err or not _line(text, "Marginal approved by"):
        return (False, "the forecast is MARGINAL: the plan file needs a non-empty 'Marginal approved by:' line "
                       "recording the owner's choice")
    return True, "owner's choice on MARGINAL recorded"


def parity_is_current(dir_, d):
    """parity.json records the hash of the list it scored. If features.csv has changed since, the score is stale."""
    try:
        with open(os.path.join(dir_, "features.csv"), "rb") as fh:
            now = hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return False, "features.csv is not in %s, so there is no way to tell whether the parity score is current" % dir_
    if now != d["input_sha256"]:
        return False, "features.csv has changed since parity was run: run swap-diff again so the score matches the list"
    return True, "the score was computed from the features.csv that is here now"


def shared_checks(a, add):
    """Checks common to both tracks."""
    ok, detail = check_mode(a.dir, a.mode)
    add("the track matches mode.txt", ok, detail)
    d, err = load_artifact(os.path.join(a.dir, "parity.json"), "parity.json")
    if err:
        add("parity is shippable", False, "parity.json %s: run swap-diff" % err)
    else:
        add("parity is shippable", d["shippable"] is True and not d["reasons"],
            "score %s; %s" % (d["score"], "; ".join(map(str, d["reasons"])) or "no blockers"))
        fresh, why = parity_is_current(a.dir, d)
        add("parity was computed from the current features.csv", fresh, why)
    ok, detail = check_bugs(os.path.join(a.dir, "bugs.csv"))
    add("no open S1 or S2 bugs", ok, detail)


def contrast_check(a, add):
    cpath = os.path.join(a.dir, "design", "contrast.json")
    if os.path.exists(cpath):
        d, err = load_artifact(cpath, "contrast.json")
        add("design contrast passes", err is None and d["passed"] is True, err or "checked")


def finish(a, add, checks, extra):
    go = all(c["pass"] for c in checks)
    for c in checks:
        print("%s  %s: %s" % ("PASS" if c["pass"] else "FAIL", c["check"], c["detail"]))
    for w in extra.get("warnings", []):
        print("WARN  " + w)
    if extra.get("cancel_by"):
        print("Last day to cancel without another term: %s" % extra["cancel_by"])
    print("\n%s" % ("GO" if go else "NO-GO"))
    if a.json:
        try:
            safe_write(a.json, json.dumps(dict({"go": go, "mode": a.mode, "checks": checks, "warnings": [], "cancel_by": None}, **extra), indent=2, allow_nan=False), [os.path.join(a.dir, n) for n in ("parity.json", "mapcheck.json", "bugs.csv", "roi.json", "sellmodel.json", "sweep.json", "listing.json", "cutover.md", "deploy.md", "mode.txt")])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0 if go else 1


def run_full(a, add, checks):
    shared_checks(a, add)
    d, err = load_artifact(os.path.join(a.dir, "sellmodel.json"), "sellmodel.json")
    if err:
        add("the product still pays back", False, "sellmodel.json %s: run swap-roi in sell mode" % err)
    else:
        add("the product still pays back", d["verdict"] in ("SELL", "MARGINAL"), "verdict %s" % d["verdict"])
        m = check_marginal(os.path.join(a.dir, "deploy.md"), d["verdict"])
        if m:
            add("the owner's choice on a MARGINAL forecast is recorded", *m)
    d, err = load_artifact(os.path.join(a.dir, "sweep.json"), "sweep.json")
    if err:
        add("nothing of the original is left", False, "sweep.json %s: run swap-brand's sweep" % err)
    else:
        unscanned = bool(d["skipped"]) and d.get("skipped_accepted") is not True
        add("nothing of the original is left", d["passed"] is True and not d["hits"] and not unscanned,
            "%d hit(s); %d file(s) not scanned%s" % (len(d["hits"]), len(d["skipped"]),
                                                    " (accepted as checked by hand)" if d["skipped"] and not unscanned else ""))
    d, err = load_artifact(os.path.join(a.dir, "listing.json"), "listing.json")
    if err:
        add("the listing passes its lint", False, "listing.json %s: run swap-launch's lint" % err)
    else:
        add("the listing passes its lint", d["passed"] is True and not d["fails"], "%d problem(s)" % len(d["fails"]))
    ok, detail = check_deploy(os.path.join(a.dir, "deploy.md"))
    add("rollback and domain are written down", ok, detail)
    contrast_check(a, add)
    return finish(a, add, checks, {})


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
    p.add_argument("--mode", choices=("lean", "full"), default="lean")
    p.add_argument("--dir", default="swap")
    p.add_argument("--renewal", default=None)
    p.add_argument("--notice-days", type=int, default=None)
    p.add_argument("--today", default=None)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    try:
        today = datetime.date.fromisoformat(a.today) if a.today else datetime.date.today()
        renewal = datetime.date.fromisoformat(a.renewal) if a.renewal else None
    except ValueError:
        print("error: dates must be YYYY-MM-DD", file=sys.stderr)
        return 2
    if a.notice_days is not None and not (0 <= a.notice_days <= 3650):
        print("error: --notice-days must be from 0 to 3650", file=sys.stderr)
        return 2
    if (renewal is None) != (a.notice_days is None):
        print("error: give --renewal and --notice-days together", file=sys.stderr)
        return 2
    if not os.path.isdir(a.dir):
        print("error: %s is not a directory" % a.dir, file=sys.stderr)
        return 2

    checks = []

    def add(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    if a.mode == "full":
        return run_full(a, add, checks)

    shared_checks(a, add)
    d, err = load_artifact(os.path.join(a.dir, "mapcheck.json"), "mapcheck.json")
    if err:
        add("migration reconciles", False, "mapcheck.json %s: run swap-migrate" % err)
    else:
        add("migration reconciles", d["passed"] is True and d["key_checked"] is True,
            "%d source rows, %d target rows; %s" % (d["source_rows"], d["target_rows"],
                                                  "matched row by row on a key" if d["key_checked"] else "NOT matched by a key, so it proves nothing"))
    d, err = load_artifact(os.path.join(a.dir, "roi.json"), "roi.json")
    if err:
        add("the swap still pays back", False, "roi.json %s: run swap-roi" % err)
    else:
        add("the swap still pays back", d["verdict"] in ("BUILD", "MARGINAL"), "verdict %s" % d["verdict"])
        m = check_marginal(os.path.join(a.dir, "cutover.md"), d["verdict"])
        if m:
            add("the owner's choice on a MARGINAL forecast is recorded", *m)
    ok, detail = check_cutover(os.path.join(a.dir, "cutover.md"), today)
    add("rollback and overlap are written down", ok, detail)
    contrast_check(a, add)

    warnings, cancel_by = [], None
    if renewal is not None:
        try:
            cancel_by = renewal - datetime.timedelta(days=a.notice_days)
        except OverflowError:
            print("error: the renewal date and notice period give a date out of range", file=sys.stderr)
            return 2
        left = (cancel_by - today).days
        if left < 0:
            warnings.append("cancel-by date %s has passed: the old tool renews on %s. Time the switch for the next window and budget for the extra term." % (cancel_by, renewal))
        elif left <= 30:
            warnings.append("cancel-by date %s is %d day(s) away" % (cancel_by, left))
    else:
        warnings.append("cancel-by date unknown: give --renewal and --notice-days, or you may pay another term")
    return finish(a, add, checks, {"warnings": warnings, "cancel_by": cancel_by.isoformat() if cancel_by else None}
                  if cancel_by or warnings else {})


if __name__ == "__main__":
    sys.exit(main())
