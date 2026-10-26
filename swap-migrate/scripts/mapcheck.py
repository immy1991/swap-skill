#!/usr/bin/env python3
"""Reconcile a data migration: did everything in the old tool arrive in the new one?

Standard library only. Never touches the network. Never prints a field value, a key
value or an amount: it reports field names, counts, line numbers and whether totals agree, so it is
safe to run over customer data. Open the named line in your own system to see the row.

Usage:
  mapcheck.py mapping.csv --source old_export.csv --target new_export.csv
              [--key id] [--allow-dropped-rows 0] [--json out.json]

mapping.csv columns
  required: source_field, action (map|derive|drop)
  target_field  required unless action is drop
  required      yes|no  (target must be filled on every row)
  check         sum     (source and target numeric totals must match within 0.005; implies compare=number)
  compare       text|number   how a "map" field is compared; default text (see below)

Actions
  map     value must arrive unchanged. Compared as TEXT by default (leading/trailing space ignored), so a postcode
          or ID like 01234 that arrives as 1234 fails. Set compare=number on genuine numeric columns (amounts,
          quantities) where 10.5 and 10.50 are the same value.
  derive  value is transformed on purpose; only loss (filled -> blank) is checked
  drop    field is deliberately not migrated; it must be listed so it cannot go missing silently

--key is REQUIRED for a pass. It is the SOURCE field that identifies a row; its mapped target
field is found through the mapping. Without a usable unique key the rows cannot be matched, so
the run fails and says so: equal counts do not prove the right data arrived.

Exit codes: 0 all checks pass, 1 any check fails, 2 bad input.
"""
import argparse
import csv
import json
import os
import sys
import tempfile
from decimal import Decimal, InvalidOperation
from fractions import Fraction

ACTIONS = ("map", "derive", "drop")


class InputError(Exception):
    pass


def read_csv(path, label):
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        raise InputError("cannot read %s file: %s" % (label, e))
    try:
        with fh:
            reader = csv.reader(fh)
            try:
                header = [h.strip() for h in next(reader)]
            except StopIteration:
                raise InputError("%s file is empty" % label)
            if len(set(header)) != len(header):
                raise InputError("%s file has duplicate column names" % label)
            rows, lines = [], []
            while True:
                start = reader.line_num + 1          # the physical line this record begins on
                try:
                    r = next(reader)
                except StopIteration:
                    break
                i = start
                if not any(c.strip() for c in r):
                    continue
                if len(r) != len(header):
                    raise InputError("%s file line %d has %d cells, header has %d" % (label, i, len(r), len(header)))
                rows.append(dict(zip(header, r)))
                lines.append(i)
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError("%s file is not readable CSV text: %s" % (label, e))
    return header, rows, lines


def load_mapping(path):
    """Read the mapping. Errors name the LINE and the problem, never the cell's contents: if the wrong file was given
    as the mapping (an export, say), echoing its cells would print customer data."""
    header, rows, lines = read_csv(path, "mapping")
    for col in ("source_field", "action"):
        if col not in header:
            raise InputError("mapping is missing required column '%s'" % col)
    m, seen_src, seen_tgt = [], set(), set()
    for r, ln in zip(rows, lines):
        where = "mapping line %d" % ln
        s = r["source_field"].strip()
        act = r["action"].strip().lower()
        t = (r.get("target_field") or "").strip()
        if not s:
            raise InputError("%s: source_field is blank" % where)
        if act not in ACTIONS:
            raise InputError("%s: action must be map, derive or drop" % where)
        if s in seen_src:
            raise InputError("%s: this source_field is listed twice" % where)
        seen_src.add(s)
        if act == "drop":
            if t:
                raise InputError("%s: a dropped field must not have a target_field" % where)
        else:
            if not t:
                raise InputError("%s: target_field is required for %s" % (where, act))
            if t in seen_tgt:
                raise InputError("%s: two source fields go to the same target" % where)
            seen_tgt.add(t)
        req = (r.get("required") or "no").strip().lower()
        chk = (r.get("check") or "").strip().lower()
        cmp_ = (r.get("compare") or "text").strip().lower()
        if cmp_ not in ("text", "number"):
            raise InputError("%s: compare must be text or number" % where)
        if req not in ("yes", "no"):
            raise InputError("%s: required must be yes or no" % where)
        if chk not in ("", "sum"):
            raise InputError("%s: check must be blank or sum" % where)
        if chk == "sum" and act == "drop":
            raise InputError("%s: cannot sum-check a dropped field" % where)
        m.append({"source": s, "target": t, "action": act, "required": req == "yes", "check": chk,
                  "numeric": cmp_ == "number" or chk == "sum"})
    if not m:
        raise InputError("mapping has no rows")
    return m


def norm(v):
    return (v or "").strip()


def dec(v):
    """Exact decimal value, or None if the text is not a finite, reasonably sized number. Never goes through
    binary floats, which cannot tell 9007199254740992 from 9007199254740993. Absurd exponents (1e1000000)
    are refused so they cannot exhaust memory or raise."""
    try:
        d = Decimal(norm(v).replace(",", ""))
    except InvalidOperation:
        return None
    if not d.is_finite():
        return None
    if d != 0 and not (-200 <= d.adjusted() <= 200):
        return None
    return d


def same(a, b, numeric=False):
    a, b = norm(a), norm(b)
    if a == b:
        return True
    if not numeric:
        return False
    da, db = dec(a), dec(b)
    return da is not None and db is not None and da == db


def num(v):
    d = dec(v)
    if d is None:
        raise ValueError("not a usable number")
    return Fraction(d)          # exact: sums of Fractions lose nothing, unlike Decimal at default precision


def lines_for(keys, line_of):
    return ", ".join(str(line_of[k]) for k in keys[:5]) or "none"


def run(mapping, sh, srows, th, trows, key, allow_dropped, slines=None, tlines=None):
    checks = []
    slines = slines or list(range(2, len(srows) + 2))
    tlines = tlines or list(range(2, len(trows) + 2))

    def add(name, ok, detail):
        checks.append({"check": name, "pass": bool(ok), "detail": detail})

    src_cols = set(sh)
    mapped_src = {m["source"] for m in mapping}
    # Source column NAMES are never printed: if an export has no header row, its first line is customer data.
    unmapped = [i + 1 for i, h in enumerate(sh) if h not in mapped_src]
    add("every source column is in the mapping", not unmapped,
        ("%d source column(s) are not in the mapping, at position(s) %s (names are not shown; if the file has no header "
         "row, add one)" % (len(unmapped), ", ".join(map(str, unmapped[:10])))) if unmapped
        else "all %d source columns listed" % len(sh))
    stale = sorted(mapped_src - src_cols)
    add("every mapped source field exists in the export", not stale,
        "not in export: " + ", ".join(stale) if stale else "ok")
    live = [m for m in mapping if m["action"] != "drop"]
    no_tgt = sorted(m["target"] for m in live if m["target"] not in th)
    add("every target field exists in the new export", not no_tgt,
        "not in new export: " + ", ".join(no_tgt) if no_tgt else "ok")
    if unmapped or stale or no_tgt:
        return checks, False

    add("the exports contain rows", len(srows) > 0 and len(trows) > 0,
        "source %d row(s), target %d row(s): a migration of nothing proves nothing" % (len(srows), len(trows)))
    expected = len(srows) - allow_dropped
    add("row count", len(trows) == expected,
        "source %d, deliberately not migrated %d, expected %d, target %d" % (
            len(srows), allow_dropped, expected, len(trows)))

    tkey = None
    if key:
        km = [m for m in live if m["source"] == key]
        if key not in src_cols or not km:
            add("key field is mapped", False, "%r is not a mapped source field" % key)
        else:
            tkey = km[0]["target"]
            sk = [norm(r[key]) for r in srows]
            tk = [norm(r[tkey]) for r in trows]
            sdup = len(sk) - len(set(sk))
            tdup = len(tk) - len(set(tk))
            add("keys are unique", sdup == 0 and tdup == 0, "duplicate keys: source %d, target %d" % (sdup, tdup))
            blank_s, blank_t = sk.count(""), tk.count("")
            add("keys are never blank", blank_s == 0 and blank_t == 0, "blank keys: source %d, target %d" % (blank_s, blank_t))
            s_line, t_line = {}, {}
            for k, ln in zip(sk, slines):
                s_line.setdefault(k, ln)
            for k, ln in zip(tk, tlines):
                t_line.setdefault(k, ln)
            missing = sorted(set(sk) - set(tk) - {""}, key=lambda k: s_line[k])
            extra = sorted(set(tk) - set(sk) - {""}, key=lambda k: t_line[k])
            if allow_dropped:
                add("no source key lost beyond the allowed drops", len(missing) <= allow_dropped,
                    "%d source rows absent, %d allowed; first at source lines: %s" % (len(missing), allow_dropped, lines_for(missing, s_line)))
            else:
                add("no source key lost", not missing,
                    "%d absent; first at source lines: %s" % (len(missing), lines_for(missing, s_line)))
            add("no unexpected keys in target", not extra,
                "%d extra; first at target lines: %s" % (len(extra), lines_for(extra, t_line)))
    if not tkey:
        add("rows can be matched by a unique key", False,
            "no usable --key: rows cannot be matched one to one, so equal counts prove nothing. Give --key (a source field that identifies a row)")

    tmap = None
    if tkey:
        tmap = {norm(r[tkey]): r for r in trows}
        smap = {norm(r[key]): r for r in srows}

    for m in live:
        s, t = m["source"], m["target"]
        if m["required"]:
            blanks = sum(1 for r in trows if not norm(r[t]))
            add("required field filled: %s" % t, blanks == 0, "%d blank of %d rows" % (blanks, len(trows)))
        if tmap is not None:
            lost, diff, lex, dex = 0, 0, [], []
            for k, sr in smap.items():
                tr = tmap.get(k)
                if tr is None:
                    continue
                if norm(sr[s]) and not norm(tr[t]):
                    lost += 1
                    if len(lex) < 5:
                        lex.append(s_line[k])
                elif m["action"] == "map" and not same(sr[s], tr[t], m["numeric"]):
                    diff += 1
                    if len(dex) < 5:
                        dex.append(s_line[k])
            add("no value lost: %s -> %s" % (s, t), lost == 0, "%d rows filled in source but blank in target%s" % (
                lost, "; first at source lines: " + ", ".join(map(str, sorted(lex))) if lost else ""))
            if m["action"] == "map":
                add("values unchanged: %s -> %s" % (s, t), diff == 0, "%d rows differ%s" % (
                    diff, "; first at source lines: " + ", ".join(map(str, sorted(dex))) if diff else ""))
        elif not key:
            sb = sum(1 for r in srows if not norm(r[s]))
            tb = sum(1 for r in trows if not norm(r[t]))
            add("no new blanks (counts only): %s -> %s" % (s, t), tb <= sb + allow_dropped,
                "blank in source %d, in target %d" % (sb, tb))
        if m["check"] == "sum":
            try:
                # When rows are deliberately dropped, only source rows that arrived are summed
                # so the drops do not read as a loss. Otherwise totals must match whole.
                basis = [r for r in srows if tmap is None or not allow_dropped or norm(r[key]) in tmap]
                ssum = sum((num(r[s]) for r in basis if norm(r[s])), Fraction(0))
                tsum = sum((num(r[t]) for r in trows if norm(r[t])), Fraction(0))
                # the amounts themselves are customer data: the report says whether they agree, never what they are
                add("total matches: %s -> %s" % (s, t), abs(ssum - tsum) <= Fraction(5, 1000),
                    ("totals agree" if abs(ssum - tsum) <= Fraction(5, 1000) else "totals differ")
                    + (" (arrived rows only)" if tmap is not None and allow_dropped else ""))
            except ValueError:
                add("total matches: %s -> %s" % (s, t), False, "a non-numeric value blocks the sum check")
    dropped = [m["source"] for m in mapping if m["action"] == "drop"]
    add("deliberately dropped fields", True, ", ".join(dropped) if dropped else "none")
    return checks, True


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
    p.add_argument("mapping")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--key", default=None)
    p.add_argument("--allow-dropped-rows", type=int, default=0)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    if a.allow_dropped_rows < 0:
        print("error: --allow-dropped-rows cannot be negative", file=sys.stderr)
        return 2
    try:
        mapping = load_mapping(a.mapping)
        sh, srows, slines = read_csv(a.source, "source")
        th, trows, tlines = read_csv(a.target, "target")
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    checks, ran = run(mapping, sh, srows, th, trows, a.key, a.allow_dropped_rows, slines, tlines)
    for c in checks:
        print("%s  %s: %s" % ("PASS" if c["pass"] else "FAIL", c["check"], c["detail"]))
    fails = [c for c in checks if not c["pass"]]
    print("\n%d of %d checks pass%s" % (len(checks) - len(fails), len(checks),
                                         "" if ran else " (stopped early: fix the mapping first)"))
    key_checked = any(c["check"] == "keys are unique" for c in checks) and not any(
        c["check"] == "rows can be matched by a unique key" for c in checks)
    if a.json:
        try:
            safe_write(a.json, json.dumps({"passed": (not fails) and key_checked, "source_rows": len(srows), "target_rows": len(trows),
                           "key_checked": key_checked, "checks": checks}, indent=2, allow_nan=False), [a.mapping, a.source, a.target])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
