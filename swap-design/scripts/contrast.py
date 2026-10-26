#!/usr/bin/env python3
"""Check WCAG 2.x contrast on a design-token file.

Standard library only. Never touches the network.

Usage:
  contrast.py tokens.json [--json out.json]

tokens.json
  {
    "colors": {"text": "#1a1a1a", "bg": "#ffffff", "muted": "#6b6b6b", "primary": "#0b5fff",
               "on-primary": "#ffffff"},
    "pairs":  [["text", "bg"], ["muted", "bg"], ["on-primary", "primary"], ["muted", "bg", 3.0]]
  }

Each pair is [foreground, background, minimum ratio]. The minimum defaults to 4.5
(AA, normal text); use 3.0 for large text or UI components.
Light and dark themes: put them under "themes": {"light": {...}, "dark": {...}}, each
with its own "colors" and "pairs"; every theme is checked.

Exit codes: 0 all pairs pass, 1 any pair fails, 2 bad input.
"""
import argparse
import json
import os
import re
import sys
import tempfile

HEX = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


class InputError(Exception):
    pass


def parse_hex(value, where):
    if not isinstance(value, str) or not HEX.match(value.strip()):
        raise InputError("%s: %r is not a #rgb or #rrggbb colour" % (where, value))
    h = value.strip()[1:]
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(rgb):
    def lin(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def check_theme(name, theme):
    if not isinstance(theme, dict) or not isinstance(theme.get("colors"), dict) or not theme["colors"]:
        raise InputError("%s: needs a non-empty 'colors' object" % name)
    colors = {k: parse_hex(v, "%s.colors.%s" % (name, k)) for k, v in theme["colors"].items()}
    pairs = theme.get("pairs")
    if not isinstance(pairs, list) or not pairs:
        raise InputError("%s: needs a non-empty 'pairs' list" % name)
    out = []
    for i, p in enumerate(pairs):
        if not isinstance(p, list) or len(p) not in (2, 3):
            raise InputError("%s.pairs[%d]: must be [fg, bg] or [fg, bg, min]" % (name, i))
        fg, bg = p[0], p[1]
        for ref in (fg, bg):
            if not isinstance(ref, str) or ref not in colors:
                raise InputError("%s.pairs[%d]: unknown colour %r" % (name, i, ref))
        mn = 4.5
        if len(p) == 3:
            mn = p[2]
            if isinstance(mn, bool) or not isinstance(mn, (int, float)) or not (1.0 <= mn <= 21.0):
                raise InputError("%s.pairs[%d]: minimum must be a number from 1 to 21" % (name, i))
        r = ratio(colors[fg], colors[bg])
        out.append({"theme": name, "fg": fg, "bg": bg, "ratio": round(r, 2), "min": mn, "pass": r >= mn})
    return out


def run(doc):
    if not isinstance(doc, dict):
        raise InputError("top level must be an object")
    if "themes" in doc:
        if not isinstance(doc["themes"], dict) or not doc["themes"]:
            raise InputError("'themes' must be a non-empty object")
        results = []
        for n, t in doc["themes"].items():
            results += check_theme(n, t)
        return results
    return check_theme("default", doc)


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
    p.add_argument("tokens")
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    try:
        with open(a.tokens, encoding="utf-8") as fh:
            doc = json.load(fh)
        results = run(doc)
    except (OSError, ValueError) as e:
        print("error: cannot read tokens: %s" % e, file=sys.stderr)
        return 2
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    for r in results:
        print("%s  %s on %s  %.2f:1 (needs %.1f)  [%s]" % (
            "PASS" if r["pass"] else "FAIL", r["fg"], r["bg"], r["ratio"], r["min"], r["theme"]))
    fails = [r for r in results if not r["pass"]]
    print("\n%d of %d pairs pass" % (len(results) - len(fails), len(results)))
    if a.json:
        try:
            safe_write(a.json, json.dumps({"passed": not fails, "results": results}, indent=2, allow_nan=False), [a.tokens])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
