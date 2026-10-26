#!/usr/bin/env python3
"""Score the new build against the scoped feature list and say whether it can ship.

Standard library only. Never touches the network.

Usage:
  parity.py features.csv [--ship-threshold 85] [--json out.json]

CSV columns
  required: feature, priority (must|should|could), in_scope (yes|no),
            status (done|partial|missing|todo|dropped|added)

Scoring covers only rows with in_scope=yes.
  weight  must 3, should 2, could 1
  credit  done 1.0, partial 0.5, missing/todo 0
  score   sum(weight x credit) / sum(weight) x 100

Left out of the score on purpose, and listed so nothing hides:
  in_scope=no, status dropped   deliberately cut by the scope decision
  in_scope=no, status added     built beyond the original, shown as extras
  in_scope=no, any other status is a contradiction and is reported as an error
An in_scope=yes row marked dropped is a contradiction and counts as missing.

SHIPPABLE needs: every in-scope must-have is done (partial is not enough) AND score
>= --ship-threshold. Otherwise NOT SHIPPABLE, with the reasons.

Exit codes: 0 shippable, 1 not shippable, 2 bad input.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
import tempfile

PRIORITIES = ("must", "should", "could")
STATUSES = ("done", "partial", "missing", "todo", "dropped", "added")
WEIGHT = {"must": 3, "should": 2, "could": 1}
CREDIT = {"done": 1.0, "partial": 0.5, "missing": 0.0, "todo": 0.0, "dropped": 0.0}


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
            for col in ("feature", "priority", "in_scope", "status"):
                if col not in reader.fieldnames:
                    raise InputError("missing required column '%s'" % col)
            rows, seen = [], set()
            for i, row in enumerate(reader, start=2):
                if None in row or None in row.values():
                    raise InputError("line %d has a different number of cells than the header" % i)
                if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
                    continue
                f = (row.get("feature") or "").strip()
                if not f:
                    raise InputError("line %d: 'feature' is blank" % i)
                if f.lower() in seen:
                    raise InputError("line %d: duplicate feature %r" % (i, f))
                seen.add(f.lower())
                pr = (row.get("priority") or "").strip().lower()
                ins = (row.get("in_scope") or "").strip().lower()
                st = (row.get("status") or "").strip().lower()
                if pr not in PRIORITIES:
                    raise InputError("line %d: priority must be one of %s, got %r" % (i, "/".join(PRIORITIES), pr))
                if ins not in ("yes", "no"):
                    raise InputError("line %d: in_scope must be yes or no, got %r" % (i, ins))
                if st not in STATUSES:
                    raise InputError("line %d: status must be one of %s, got %r" % (i, "/".join(STATUSES), st))
                rows.append({"feature": f, "priority": pr, "in_scope": ins == "yes", "status": st})
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError("features file is not readable CSV text: %s" % e)
    if not rows:
        raise InputError("no data rows")
    return rows


def run(rows, threshold):
    scored, extras, cut, contradictions = [], [], [], []
    for r in rows:
        if r["in_scope"]:
            if r["status"] == "added":
                contradictions.append("%s: in scope but status 'added'" % r["feature"])
                continue
            if r["status"] == "dropped":
                contradictions.append("%s: in scope but status 'dropped': counted as missing" % r["feature"])
            scored.append(r)
        elif r["status"] == "dropped":
            cut.append(r["feature"])
        elif r["status"] == "added":
            extras.append(r["feature"])
        else:
            contradictions.append("%s: out of scope but status '%s'" % (r["feature"], r["status"]))
    tw = sum(WEIGHT[r["priority"]] for r in scored)
    earned = sum(WEIGHT[r["priority"]] * CREDIT[r["status"]] for r in scored)
    score = (earned / tw * 100.0) if tw else 0.0
    by = {}
    for p in PRIORITIES:
        grp = [r for r in scored if r["priority"] == p]
        by[p] = {"total": len(grp),
                 "done": sum(1 for r in grp if r["status"] == "done"),
                 "partial": sum(1 for r in grp if r["status"] == "partial"),
                 "gaps": sum(1 for r in grp if r["status"] not in ("done", "partial"))}
    must_gaps = [r["feature"] for r in scored if r["priority"] == "must" and r["status"] != "done"]
    missing = [r["feature"] for r in scored if r["status"] in ("missing", "todo", "dropped")]
    partial = [r["feature"] for r in scored if r["status"] == "partial"]
    reasons = []
    if not scored:
        reasons.append("no in-scope features to score")
    if must_gaps:
        reasons.append("must-have not done: " + ", ".join(must_gaps))
    if scored and score < threshold:
        reasons.append("score %.1f is under the %.0f threshold" % (score, threshold))
    if contradictions:
        reasons.append("%d contradictory row(s): fix the list" % len(contradictions))
    return {
        "score": score, "threshold": threshold, "shippable": not reasons,
        "reasons": reasons, "by_priority": by, "in_scope_count": len(scored),
        "must_gaps": must_gaps, "missing": missing, "partial": partial,
        "deliberately_cut": cut, "extras": extras, "contradictions": contradictions,
    }


def fmt(rep):
    L = ["Parity score: %.1f / 100 (ship threshold %g) over %d in-scope features" % (
        rep["score"], rep["threshold"], rep["in_scope_count"]), ""]
    L += ["| priority | in scope | done | partial | gaps |", "|---|---|---|---|---|"]
    for p in PRIORITIES:
        b = rep["by_priority"][p]
        L.append("| %s | %d | %d | %d | %d |" % (p, b["total"], b["done"], b["partial"], b["gaps"]))
    for title, key in (("Missing", "missing"), ("Partial", "partial"),
                       ("Deliberately cut (not scored)", "deliberately_cut"),
                       ("Extras built beyond the original (not scored)", "extras"),
                       ("Contradictions", "contradictions")):
        if rep[key]:
            L += ["", title + ":"] + ["- " + x for x in rep[key]]
    L += ["", "SHIPPABLE" if rep["shippable"] else "NOT SHIPPABLE"]
    L += ["- " + x for x in rep["reasons"]]
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
    p.add_argument("--ship-threshold", type=float, default=85.0)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    if not (0 <= a.ship_threshold <= 100):
        print("error: --ship-threshold must be 0 to 100", file=sys.stderr)
        return 2
    try:
        rows = load(a.csv)
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    rep = run(rows, a.ship_threshold)
    with open(a.csv, "rb") as fh:
        rep["input_sha256"] = hashlib.sha256(fh.read()).hexdigest()      # lets the cutover gate see the score is stale
    print(fmt(rep))
    if a.json:
        try:
            safe_write(a.json, json.dumps(rep, indent=2, allow_nan=False), [a.csv])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0 if rep["shippable"] else 1


if __name__ == "__main__":
    sys.exit(main())
