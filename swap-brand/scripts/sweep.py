#!/usr/bin/env python3
"""Find anything of the original product left in your code before you launch.

Standard library only. Never touches the network. Read-only.

Usage:
  sweep.py DIR --avoid "Original App" [--avoid "Other Name"] [--domain original.com]
               [--color "#112233"] [--allow word] [--exclude swap] [--accept-skipped] [--json out.json]

What it finds
  names    each --avoid name matched case-insensitively with any separator, and inside identifiers:
           "Original App" also catches OriginalApp, original_app, original-app, ORIGINAL.APP, OriginalAppEmbed
  domains  each --domain, with or without www, in any text
  colours  each --color as #rgb, #rrggbb (with or without alpha digits) and rgb()/rgba() with the same values, in
           comma form, the modern space form, decimals, percentages, signs, exponents and values split across lines
           (rgb(100% 0% 0%) is #ff0000; out-of-range values clamp as CSS does). Names are matched across line
           breaks too. NOT checked: hsl(), named colours, colours inside images or fonts.
  paths    file and folder names containing a name
Skipped on purpose (not counted): .git, node_modules, __pycache__, .venv, dist, build, hidden folders,
anything given to --exclude.
Not scanned and therefore a problem: binary files (any NUL byte anywhere), files that are not valid UTF-8,
files over 2 MB, unreadable files and folders,
symlinks (never followed: they could point outside the folder you named or loop). A scan that reads zero files fails too.
They are listed. The run is NOT CLEAN while any exist, because the original could be inside them. Check them
by hand, then rerun with --accept-skipped to record that you did; the JSON keeps the list and the acceptance.

The report shows the matched text (which is what you asked it to find), the file and the line. It never
prints the surrounding line, because a matching line can hold secrets or customer data.

--allow removes a harmless longer word from the line before matching (for a short name that sits inside
a common word). Use it sparingly; every use is printed.

The scan covers the code you point it at. Keep research notes (the swap/ folder) outside the scanned tree or
pass --exclude swap, since they name the original on purpose.

Exit codes: 0 clean and fully scanned, 1 anything found or anything not scanned, 2 bad arguments.
"""
import argparse
import bisect
import json
import os
import re
import stat
import sys
import tempfile

SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
MAX_BYTES = 2 * 1024 * 1024


def name_regex(name):
    toks = [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]
    if not toks:
        raise ValueError("name %r has no letters or digits" % name)
    return re.compile(r"[\s_\-.]*".join(re.escape(t) for t in toks), re.I)


def hex_to_rgb(h):
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        raise ValueError("colour %r is not #rgb or #rrggbb" % h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)), h.lower()


def colour_regexes(c):
    (r, g, b), six = hex_to_rgb(c)
    short = six[0] == six[1] and six[2] == six[3] and six[4] == six[5]
    # six digits (optionally followed by two alpha digits), or the three-digit short form
    # (optionally followed by one alpha digit): both are the same colour.
    alts = [six + "(?:[0-9a-f]{2})?"]
    if short:
        alts.append(six[0] + six[2] + six[4] + "[0-9a-f]?")
    hexpat = "#(?:" + "|".join(alts) + ")"
    return [re.compile(hexpat + r"(?![0-9a-fA-F])", re.I)]


_TOK = r"[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?%?"
RGB_FN = re.compile(r"rgba?\(\s*(%s)\s*[,\s]\s*(%s)\s*[,\s]\s*(%s)" % (_TOK, _TOK, _TOK), re.I)


def channel(tok):
    """One rgb() channel as 0-255 the way CSS reads it: a number or a percentage of 255, signs and exponents
    allowed, clamped to the range. Absurd values clamp instead of raising."""
    v = float(tok.rstrip("%"))
    if tok.endswith("%"):
        v *= 2.55
    if v != v:
        raise ValueError("not a number")
    return int(round(max(0.0, min(255.0, v))))


def shown(m):
    """The matched text only, shortened. Never the rest of the line."""
    t = m.group(0).strip()
    return t if len(t) <= 60 else t[:57] + "..."


def sweep(root, names, domains, colours, allow, excludes):
    pats = []
    for n in names:
        pats.append(("name", n, name_regex(n)))
    for d in domains:
        d0 = re.sub(r"^www\.", "", d.strip(), flags=re.I)
        pats.append(("domain", d, re.compile(r"(?:www\.)?" + re.escape(d0), re.I)))
    rgb_targets = []
    for c in colours:
        for rx in colour_regexes(c):
            pats.append(("colour", c, rx))
        rgb_targets.append((c, hex_to_rgb(c)[0]))
    allow_rx = [re.compile(re.escape(a), re.I) for a in allow]
    hits, skipped, scanned = [], [], 0
    ex = {e.strip("/") for e in excludes}
    def on_error(err):
        skipped.append("%s (unreadable folder: %s)" % (os.path.normpath(os.path.relpath(err.filename or root, root)), err.strerror))

    for dirpath, dirnames, filenames in os.walk(root, onerror=on_error):
        rel_dir = os.path.relpath(dirpath, root)
        keep = []
        for d in sorted(dirnames):
            if d in SKIP_DIRS or d in ex or os.path.normpath(os.path.join(rel_dir, d)) in ex:
                continue
            if os.path.islink(os.path.join(dirpath, d)):
                skipped.append("%s (symlink to a folder, not followed)" % os.path.normpath(os.path.join(rel_dir, d)))
                continue
            keep.append(d)
        dirnames[:] = keep
        for entry in dirnames + filenames:
            rel = os.path.normpath(os.path.join(rel_dir, entry))
            for kind, label, rx in pats:
                if kind == "name" and rx.search(entry):
                    hits.append({"kind": "path", "what": label, "file": rel, "line": 0, "match": entry})
        for f in sorted(filenames):
            p = os.path.join(dirpath, f)
            rel = os.path.normpath(os.path.relpath(p, root))
            if rel in ex or f in ex:
                continue
            if os.path.islink(p):
                skipped.append("%s (symlink, not followed)" % rel)
                continue
            try:
                regular = stat.S_ISREG(os.lstat(p).st_mode)
            except OSError as e:
                skipped.append("%s (%s)" % (rel, e.strerror))
                continue
            if not regular:
                skipped.append("%s (not a regular file: pipe, socket or device)" % rel)
                continue
            try:
                size = os.path.getsize(p)
                if size > MAX_BYTES:
                    skipped.append("%s (over 2 MB)" % rel)
                    continue
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError as e:
                skipped.append("%s (%s)" % (rel, e.strerror))
                continue
            if b"\0" in data:
                skipped.append("%s (binary)" % rel)
                continue
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                skipped.append("%s (not valid UTF-8 text)" % rel)
                continue
            scanned += 1
            # Scan the WHOLE file, not line by line: a colour or a name can be split across lines. Words the user
            # allowed are blanked out with spaces (newlines kept) so offsets and line numbers stay true.
            probe = text
            for al in allow_rx:
                probe = al.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), probe)
            newlines = [i for i, ch in enumerate(probe) if ch == "\n"]
            line_of = lambda pos: bisect.bisect_left(newlines, pos) + 1
            for m in RGB_FN.finditer(probe):
                try:
                    got = tuple(channel(g) for g in m.groups())
                except (ValueError, OverflowError):
                    continue
                for label, target in rgb_targets:
                    if got == target:
                        hits.append({"kind": "colour", "what": label, "file": rel, "line": line_of(m.start()), "match": "rgb(...)"})
            hit_lines = set()
            for kind, label, rx in pats:
                for m in rx.finditer(probe):
                    ln = line_of(m.start())
                    if kind == "name":
                        hit_lines.add(ln)
                    hits.append({"kind": kind, "what": label, "file": rel, "line": ln, "match": shown(m)})
            for kind, label, rx in pats:
                if kind != "name":
                    continue
                key = re.sub(r"[^a-z0-9]", "", label.lower())
                if len(key) < 6:
                    continue
                for ln, line in enumerate(probe.split("\n"), start=1):
                    if ln not in hit_lines and key in re.sub(r"[^a-z0-9]", "", line.lower()):
                        hits.append({"kind": "name", "what": label, "file": rel, "line": ln,
                                     "match": "(spaced or punctuated variant of the name)"})
    return hits, skipped, scanned


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
    p.add_argument("dir")
    p.add_argument("--avoid", action="append", default=[])
    p.add_argument("--domain", action="append", default=[])
    p.add_argument("--color", action="append", default=[])
    p.add_argument("--allow", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--accept-skipped", action="store_true")
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    if not os.path.isdir(a.dir):
        print("error: %s is not a directory" % a.dir, file=sys.stderr)
        return 2
    if not (a.avoid or a.domain or a.color):
        print("error: give at least one --avoid, --domain or --color to look for", file=sys.stderr)
        return 2
    for n in a.avoid:
        if len(re.sub(r"[^A-Za-z0-9]", "", n)) < 4:
            print("warning: %r is short, so it may match inside ordinary words; use --allow for harmless ones" % n,
                  file=sys.stderr)
    try:
        hits, skipped, scanned = sweep(a.dir, a.avoid, a.domain, a.color, a.allow, a.exclude)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    for h in hits:
        print("%-6s %s:%s  [%s]  %s" % (h["kind"].upper(), h["file"], h["line"] or "-", h["what"], h["match"]))
    for al in a.allow:
        print("allowed (removed before matching): %s" % al)
    for s in skipped:
        print("skipped: %s" % s)
    unscanned = bool(skipped) and not a.accept_skipped
    empty = scanned == 0
    passed = (not hits) and not unscanned and not empty
    print("\nscanned %d file(s); %d hit(s); %d file(s) not scanned" % (scanned, len(hits), len(skipped)))
    if passed:
        print("CLEAN" + (" (the %d unscanned file(s) were accepted by you as checked by hand)" % len(skipped) if skipped else ""))
    elif hits:
        print("NOT CLEAN: remove or replace every hit, then rerun")
    elif empty:
        print("NOT CLEAN: no file was scanned. Check the path and the --exclude list: an empty scan certifies nothing")
    else:
        print("NOT CLEAN: %d file(s) could not be scanned. Check them by hand, then rerun with --accept-skipped" % len(skipped))
    if a.json:
        try:
            safe_write(a.json, json.dumps({"passed": passed, "files_scanned": scanned, "hits": hits, "skipped": skipped,
                           "skipped_accepted": bool(skipped) and a.accept_skipped,
                           "looked_for": {"names": a.avoid, "domains": a.domain, "colours": a.color, "allowed": a.allow}}, indent=2, allow_nan=False), [])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
