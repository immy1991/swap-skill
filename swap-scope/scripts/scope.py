#!/usr/bin/env python3
"""Cut a feature list down to what a business actually uses, and add up the effort.

Standard library only. Never touches the network.

Usage:
  scope.py features.csv [--mode lean|full] [--backlog-unknown] [--subset subset.txt] [--contingency 1.5]
           [--json out.json] [--annotate master.csv [--rescope]]

CSV columns
  required: feature, priority (must|should|could), usage (daily|weekly|monthly|rarely|never|unknown)
  optional: kind (feature|integration|network|content|licence), effort_days, confirmed (yes|no)

Rules, applied in this order (first match wins)
  1. kind network / content / licence  -> OUT   (belongs to the vendor, not rebuildable)
  2. usage never                        -> OUT   (nobody uses it)
  3. usage unknown                      -> HOLD  (ask a user; not counted in the estimate)
  4. priority must                      -> IN
  5. kind integration                   -> IN only if usage is monthly or more often, else OUT
  6. priority should                    -> IN if usage is daily, weekly or monthly, else OUT
  7. priority could                     -> IN only if usage is daily, else OUT (backlog)

--backlog-unknown (lean only): when nobody can say how often a feature is used, leave it out and keep it on the
backlog instead of holding the whole scope. The usage stays "unknown" in the file (it is never changed to a guess)
and the output says the feature was backlogged for that reason.

--mode full is for building a product to sell, not to use. Nobody here is the user, so usage
is evidence from public sources and may be unknown. Rules in full mode:
  1. kind network / content / licence  -> OUT   (still belongs to the vendor)
  2. usage never                        -> OUT   (deprecated or unused by the vendor's own customers)
  3. everything else                    -> IN    (full parity), whatever the priority or usage
  HOLD does not exist in full mode. Default mode is lean.

Effort is reported raw and with the contingency multiplier. In-scope rows with no
effort_days are listed and the estimate is marked incomplete. It is never guessed.

--subset (full only): a text file, one feature name per line, carrying a NARROW verdict from swap-market. Features
not listed are OUT ("outside the NARROW subset"). Names that are not in the feature list are an error.

--annotate writes the master feature list that swap-build and swap-diff use: every row with in_scope (yes for IN,
no for OUT) and status (todo for IN, dropped for OUT); effort_days is copied as written, not re-formatted.
It refuses while any feature is on HOLD, because an undecided feature cannot be built or scored (exit 1).
It also refuses to overwrite an existing file (exit 2): that would reset every status to todo. To rescope after
work has started, run it on the original recon list with --rescope: features still in scope keep their status
and any extra columns, features that became out of scope while done or partial are reported, and approved
extras (status added) are kept.

Exit codes: 0 ok, 1 --annotate refused (HOLD rows), 2 bad input.
"""
import argparse
import csv
import json
import os
import sys
import tempfile

PRIORITIES = ("must", "should", "could")
USAGES = ("daily", "weekly", "monthly", "rarely", "never", "unknown")
KINDS = ("feature", "integration", "network", "content", "licence")
FREQUENT = ("daily", "weekly", "monthly")


class InputError(Exception):
    pass


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
            reader.fieldnames = [n.strip() for n in reader.fieldnames]
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise InputError("duplicate column names: the last one would silently win")
            for col in ("feature", "priority", "usage"):
                if col not in reader.fieldnames:
                    raise InputError("missing required column '%s'" % col)
            rows, seen = [], set()
            for i, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    raise InputError("line %d has a different number of cells than the header" % i)
                if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                    continue
                name = (row.get("feature") or "").strip()
                if not name:
                    raise InputError("line %d: 'feature' is blank" % i)
                if name.lower() in seen:
                    raise InputError("line %d: duplicate feature %r" % (i, name))
                seen.add(name.lower())
                pr = (row.get("priority") or "").strip().lower()
                us = (row.get("usage") or "").strip().lower()
                kd = (row.get("kind") or "feature").strip().lower() or "feature"
                if pr not in PRIORITIES:
                    raise InputError("line %d: priority must be one of %s, got %r" % (i, "/".join(PRIORITIES), pr))
                if us not in USAGES:
                    raise InputError("line %d: usage must be one of %s, got %r" % (i, "/".join(USAGES), us))
                if kd not in KINDS:
                    raise InputError("line %d: kind must be one of %s, got %r" % (i, "/".join(KINDS), kd))
                raw = (row.get("effort_days") or "").strip()
                effort = None
                if raw:
                    try:
                        effort = float(raw)
                    except ValueError:
                        raise InputError("line %d: effort_days is not a number: %r" % (i, raw))
                    if effort != effort or effort < 0 or effort == float("inf"):
                        raise InputError("line %d: effort_days must be a finite number >= 0" % i)
                conf = (row.get("confirmed") or "").strip().lower()
                if conf not in ("", "yes", "no"):
                    raise InputError("line %d: confirmed must be yes or no, got %r" % (i, conf))
                rows.append({"feature": name, "priority": pr, "usage": us, "kind": kd,
                             "effort_days": effort, "effort_text": raw, "confirmed": conf == "yes"})
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError("features file is not readable CSV text: %s" % e)
    if not rows:
        raise InputError("no data rows")
    return rows


def load_subset(path):
    try:
        with open(path, encoding="utf-8") as fh:
            names = {ln.strip().lower() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")}
    except (OSError, UnicodeDecodeError) as e:
        raise InputError("cannot read subset file: %s" % e)
    if not names:
        raise InputError("subset file lists no features")
    return names


def decide(r, mode="lean", backlog_unknown=False, subset=None):
    if mode == "full":
        if r["kind"] in ("network", "content", "licence"):
            return "OUT", "vendor-owned (%s): not rebuildable" % r["kind"]
        if r["usage"] == "never":
            return "OUT", "never used: deprecated or dead feature"
        if subset is not None and r["feature"].lower() not in subset:
            return "OUT", "outside the NARROW subset approved in the market step"
        return "IN", "full parity: %s priority, usage %s" % (r["priority"], r["usage"])
    if r["kind"] in ("network", "content", "licence"):
        return "OUT", "vendor-owned (%s): not rebuildable" % r["kind"]
    if r["usage"] == "never":
        return "OUT", "nobody uses it"
    if r["usage"] == "unknown":
        if backlog_unknown:
            return "OUT", "usage unknown and nobody could say: backlog"
        return "HOLD", "usage unknown: ask a user before deciding"
    if r["priority"] == "must":
        return "IN", "must-have, used %s" % r["usage"]
    if r["kind"] == "integration":
        if r["usage"] in FREQUENT:
            return "IN", "integration used %s" % r["usage"]
        return "OUT", "integration used only %s" % r["usage"]
    if r["priority"] == "should":
        if r["usage"] in FREQUENT:
            return "IN", "should-have, used %s" % r["usage"]
        return "OUT", "should-have but used only %s: backlog" % r["usage"]
    if r["usage"] == "daily":
        return "IN", "could-have but used daily"
    return "OUT", "could-have, used %s: backlog" % r["usage"]


def run(rows, contingency, mode="lean", backlog_unknown=False, subset=None):
    if subset is not None:
        if mode != "full":
            raise InputError("--subset only applies to --mode full (it carries a NARROW verdict from swap-market)")
        names = {r["feature"].lower() for r in rows}
        unknown = sorted(subset - names)
        if unknown:
            raise InputError("subset names not in the feature list: " + ", ".join(unknown))
    res = {"IN": [], "OUT": [], "HOLD": []}
    for r in rows:
        d, why = decide(r, mode, backlog_unknown, subset)
        res[d].append(dict(r, decision=d, reason=why))
    rank = {"must": 0, "should": 1, "could": 2}
    use = {"daily": 0, "weekly": 1, "monthly": 2, "rarely": 3, "never": 4, "unknown": 5}
    res["IN"].sort(key=lambda r: (rank[r["priority"]], use[r["usage"]], r["feature"].lower()))
    inn = res["IN"]
    est = [r for r in inn if r["effort_days"] is not None]
    missing = [r["feature"] for r in inn if r["effort_days"] is None]
    raw = sum(r["effort_days"] for r in est)
    if raw != raw or raw == float("inf") or raw * contingency == float("inf"):
        raise InputError("the effort estimates are so large that the total overflowed; check the units")
    return {
        "mode": mode,
        "backlog_unknown": bool(backlog_unknown),
        "subset": sorted(subset) if subset is not None else None,
        "contingency": contingency,
        "in_scope": inn, "out_of_scope": res["OUT"], "hold": res["HOLD"],
        "counts": {"in": len(inn), "out": len(res["OUT"]), "hold": len(res["HOLD"]), "total": len(rows)},
        "effort_days_raw": raw,
        "effort_days_with_contingency": raw * contingency,
        "estimate_complete": not missing and not res["HOLD"],
        "unestimated_in_scope": missing,
        "unconfirmed_in_scope": [r["feature"] for r in inn if not r["confirmed"]],
    }


BASE_COLS = ["feature", "priority", "usage", "kind", "effort_days", "confirmed", "in_scope", "status"]


def read_master(path):
    """Read an existing master list strictly: a corrupt one must stop a rescope, not be half-understood."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        raise InputError("the existing master %s is empty" % path)
    header = [c.strip() for c in rows[0]]
    if len(set(header)) != len(header):
        raise InputError("the existing master has duplicate column names: refusing to merge into it (the last one would win)")
    for need in ("feature", "status"):
        if need not in header:
            raise InputError("the existing master has no '%s' column: refusing to merge into it" % need)
    old = {}
    for n, r in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in r):
            continue
        if len(r) != len(header):
            raise InputError("the existing master, line %d, has a different number of cells than its header" % n)
        d = dict(zip(header, r))
        key = d["feature"].strip().lower()
        if not key:
            raise InputError("the existing master, line %d, has a blank feature name: refusing to merge into it" % n)
        if key in old:
            raise InputError("the existing master lists the same feature twice (line %d): refusing to merge, since one "
                             "row's status and notes would be lost" % n)
        if (d["status"] or "").strip().lower() not in ("todo", "partial", "done", "missing", "dropped", "added"):
            raise InputError("the existing master, line %d, has a status that is not todo, partial, done, missing, "
                             "dropped or added: refusing to merge into it" % n)
        old[key] = d
    return header, old


def build_master(rep, path, rescope=False):
    """Work out the master list WITHOUT writing it. Returns (header, rows, warnings). A first scoping needs a path
    that does not exist; rescope merges into the existing master, keeping status and extra columns of features
    still in scope."""
    old, old_cols = {}, []
    if os.path.exists(path):
        if not rescope:
            raise FileExistsError("%s already exists. Writing a fresh master would reset every status to todo and drop "
                                  "extra columns. Use --rescope to merge into it, or give a new path." % path)
        old_cols, old = read_master(path)
    extra = [c for c in old_cols if c not in BASE_COLS]
    rows = [(r, "yes") for r in rep["in_scope"]] + [(r, "no") for r in rep["out_of_scope"]]
    warnings, written, out = [], set(), []
    for r, ins in rows:
        prev = old.get(r["feature"].lower())
        status = "todo" if ins == "yes" else "dropped"
        if prev:
            pst = (prev.get("status") or "").strip().lower()
            if ins == "yes" and pst in ("todo", "partial", "done", "missing"):
                status = pst
            elif ins == "no" and pst in ("partial", "done"):
                warnings.append("%s was '%s' but is now out of scope: its built work is not part of the scored list" % (r["feature"], pst))
        written.add(r["feature"].lower())
        line = [r["feature"], r["priority"], r["usage"], r["kind"], r["effort_text"], "yes" if r["confirmed"] else "no", ins, status]
        out.append(line + [(prev or {}).get(c, "") for c in extra])
    for key, prev in old.items():
        if key not in written:
            if (prev.get("status") or "").strip().lower() == "added":
                out.append([prev.get(c, "") for c in BASE_COLS] + [prev.get(c, "") for c in extra])      # approved extras stay
            else:
                warnings.append("%s was in the old master but is not in the feature list any more: dropped from the master" % prev.get("feature", key))
    return BASE_COLS + extra, out, warnings


def write_master(path, header, rows):
    """Stage in the same folder, then replace: a failure leaves the old master untouched."""
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".master-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(header)
            w.writerows(rows)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def fmt(rep):
    L = ["MODE: %s" % rep["mode"], "", "IN SCOPE (%d)" % rep["counts"]["in"], "| feature | priority | usage | effort days | reason |", "|---|---|---|---|---|"]
    for r in rep["in_scope"]:
        L.append("| %s | %s | %s | %s | %s |" % (
            r["feature"], r["priority"], r["usage"],
            "?" if r["effort_days"] is None else "%g" % r["effort_days"], r["reason"]))
    L += ["", "HOLD (%d): ask a user first" % rep["counts"]["hold"]]
    L += ["- %s: %s" % (r["feature"], r["reason"]) for r in rep["hold"]]
    L += ["", "OUT OF SCOPE (%d)" % rep["counts"]["out"]]
    L += ["- %s: %s" % (r["feature"], r["reason"]) for r in rep["out_of_scope"]]
    L += ["", "Effort: %g days raw, %g days with x%g contingency" % (
        rep["effort_days_raw"], rep["effort_days_with_contingency"], rep["contingency"])]
    if not rep["estimate_complete"]:
        why = []
        if rep["unestimated_in_scope"]:
            why.append("no estimate for: " + ", ".join(rep["unestimated_in_scope"]))
        if rep["hold"]:
            why.append("%d feature(s) on HOLD are not counted" % rep["counts"]["hold"])
        L.append("ESTIMATE INCOMPLETE: " + "; ".join(why))
    if rep["unconfirmed_in_scope"]:
        L.append("Usage not confirmed by a real user for: " + ", ".join(rep["unconfirmed_in_scope"]))
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
    p.add_argument("--mode", choices=("lean", "full"), default="lean")
    p.add_argument("--backlog-unknown", action="store_true")
    p.add_argument("--subset", default=None)
    p.add_argument("--rescope", action="store_true")
    p.add_argument("--contingency", type=float, default=1.5)
    p.add_argument("--json", default=None)
    p.add_argument("--annotate", default=None)
    a = p.parse_args(argv)
    if not (a.contingency >= 1.0) or a.contingency == float("inf"):
        print("error: --contingency must be a finite number >= 1", file=sys.stderr)
        return 2
    try:
        rows = load(a.csv)
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    try:
        subset = None
        if a.subset:
            subset = load_subset(a.subset)
        rep = run(rows, a.contingency, a.mode, a.backlog_unknown, subset)
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print(fmt(rep))
    # 1. Refuse path collisions before anything is written: an output must never be one of the inputs or the other output.
    real = lambda x: os.path.realpath(x)
    inputs = {"the feature list": real(a.csv)}
    if a.subset:
        inputs["the subset file"] = real(a.subset)
    outputs = {}
    if a.json:
        outputs["--json"] = real(a.json)
    if a.annotate:
        outputs["--annotate"] = real(a.annotate)
    seen = dict((v, k) for k, v in inputs.items())
    for name, path in outputs.items():
        if path in seen:
            print("error: %s points at the same file as %s: refusing to overwrite it" % (name, seen[path]), file=sys.stderr)
            return 2
        seen[path] = name
    # 2. Work out everything that can fail BEFORE writing anything.
    master = None
    if a.annotate:
        if rep["hold"]:
            print("error: --annotate refused: %d feature(s) on HOLD. Ask a user, update usage, rerun." % len(rep["hold"]), file=sys.stderr)
            return 1
        try:
            master = build_master(rep, a.annotate, a.rescope)
        except FileExistsError as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
        except InputError as e:
            print("error: %s" % e, file=sys.stderr)
            return 2
        except (OSError, UnicodeDecodeError, csv.Error) as e:
            print("error: cannot read the existing master %s: %s" % (a.annotate, e), file=sys.stderr)
            return 2
    text = None
    if a.json:
        try:
            text = json.dumps(rep, indent=2, allow_nan=False)
        except ValueError as e:
            print("error: cannot serialise the report: %s" % e, file=sys.stderr)
            return 2
    # 3. Write.
    if a.json:
        try:
            safe_write(a.json, text, [a.csv, a.subset])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    if master:
        header, mrows, warns = master
        try:
            write_master(a.annotate, header, mrows)
        except OSError as e:
            print("error: cannot write %s: %s" % (a.annotate, e), file=sys.stderr)
            return 2
        for w in warns:
            print("WARNING: " + w)
        print("wrote %s" % a.annotate)
    return 0


if __name__ == "__main__":
    sys.exit(main())
