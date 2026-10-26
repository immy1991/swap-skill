#!/usr/bin/env python3
"""Lint a store or web listing before it goes live.

Standard library only. Never touches the network. Read-only.

Usage:
  listing.py listing.json [--json out.json]

listing.json
  {"store": "apple" | "google" | "web",
   "original_names": ["Original App"],
   "title": "...", "subtitle": "...", "short_description": "...", "description": "...",
   "keywords": "scheduling,booking,calendar", "promo_text": "..."}

Limits (characters, except where noted)
  apple   title 30, subtitle 30, keywords 100 BYTES of UTF-8 (Apple's wording: "up to 100 bytes"; a Chinese or
          accented character costs 2 to 3 bytes), promo_text 170, description 4000
  google  title 30, short_description 80, description 4000
  web     title 60, short_description 160 (search-result guidelines; over-length is a warning, not a failure)
These are the limits as best known when this was written. Store rules change: check the store's own
current documentation before submitting. Edit LIMITS below if they have moved.

FAIL (blocks launch)
  - a field over its store limit (apple, google); a required field missing (title, description; google also short_description)
  - the original product's name anywhere in any field, including inside other words or keywords
  - a ranking or superlative claim in the title, subtitle or short description ("#1", "best", "top rated", "number one",
    "leading"); on google also in the full description (Google's help article lists "#1" and similar under app descriptions)
  - price or promotion words in the title or subtitle on apple and google ("free", "$", "% off", "sale", "discount");
    on google also in the short and full description ("10% off" and price information are listed there)
  - "official" anywhere (implies you are the vendor)
WARN (read it, then decide)
  - the word "clone", "copy of" or "unofficial"
  - keyword field: spaces after commas (wasted characters), repeated words, words already in the title or subtitle

Exit codes: 0 no FAIL, 1 any FAIL, 2 bad input.
"""
import argparse
import json
import os
import re
import sys
import tempfile

LIMITS = {
    "apple": {"title": 30, "subtitle": 30, "keywords": 100, "promo_text": 170, "description": 4000},
    "google": {"title": 30, "short_description": 80, "description": 4000},
    "web": {"title": 60, "short_description": 160},
}
BYTE_FIELDS = {("apple", "keywords")}      # measured in UTF-8 bytes, not characters
REQUIRED = {"apple": ["title", "description"], "google": ["title", "short_description", "description"],
            "web": ["title", "description"]}
FIELDS = ["title", "subtitle", "short_description", "description", "keywords", "promo_text"]
RANKING = re.compile(r"(?:#\s?1\b|\bno\.?\s?1\b|\bnumber\s+(?:one|1)\b|\bbest\b|\btop[\s-]rated\b|\btop\b|\bleading\b|"
                     r"\bworld'?s\s+(?:best|first|#?1)\b|\baward[\s-]winning\b)", re.I)
PRICE = re.compile(r"(?:\bfree\b|\$|£|€|\d+\s?%\s?off\b|\bsale\b|\bdiscount\b)", re.I)
OFFICIAL = re.compile(r"\bofficial\b", re.I)
SOFT = re.compile(r"\b(?:clone|copy of|unofficial)\b", re.I)


class InputError(Exception):
    pass


def name_regex(name):
    toks = [t for t in re.split(r"[^A-Za-z0-9]+", name) if t]
    if not toks:
        raise InputError("original name %r has no letters or digits" % name)
    return re.compile(r"[\s_\-.]*".join(re.escape(t) for t in toks), re.I)


def load(path):
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        raise InputError("cannot read listing: %s" % e)
    if not isinstance(d, dict):
        raise InputError("listing must be a JSON object")
    if not isinstance(d.get("store"), str) or d.get("store") not in LIMITS:
        raise InputError("'store' must be one of %s" % ", ".join(sorted(LIMITS)))
    names = d.get("original_names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n.strip() for n in names):
        raise InputError("'original_names' must list the product(s) you are replacing; the check needs them")
    for f in FIELDS:
        if f in d and not isinstance(d[f], str):
            raise InputError("'%s' must be a string" % f)
    return d


def lint(d):
    store = d["store"]
    fails, warns = [], []
    lengths = {}
    for f in FIELDS:
        v = d.get(f, "")
        if v:
            lengths[f] = len(v)
    for f in REQUIRED[store]:
        if not d.get(f, "").strip():
            fails.append("required field '%s' is missing or empty for %s" % (f, store))
    for f, limit in LIMITS[store].items():
        n = len(d.get(f, "").encode("utf-8", "surrogatepass")) if (store, f) in BYTE_FIELDS else len(d.get(f, ""))
        unit = "bytes" if (store, f) in BYTE_FIELDS else "characters"
        if n > limit:
            (fails if store != "web" else warns).append("%s is %d %s; %s limit is %d" % (f, n, unit, store, limit))
    rxs = [(n, name_regex(n)) for n in d["original_names"]]
    for f in FIELDS:
        v = d.get(f, "")
        squashed = re.sub(r"[^a-z0-9]", "", v.lower())
        for n, rx in rxs:
            hit = False
            for m in rx.finditer(v):
                hit = True
                fails.append("the original name %r appears in %s (at character %d)" % (n, f, m.start() + 1))
            key = re.sub(r"[^a-z0-9]", "", n.lower())
            if not hit and len(key) >= 6 and key in squashed:
                fails.append("the original name %r appears in %s with spaces or punctuation inserted" % (n, f))
    rank_fields = ["title", "subtitle", "short_description"] + (["description"] if store == "google" else [])
    for f in rank_fields:
        v = d.get(f, "")
        for m in RANKING.finditer(v):
            fails.append("ranking or superlative claim %r in %s" % (m.group(0), f))
    if store in ("apple", "google"):
        price_fields = ["title", "subtitle"] + (["short_description", "description"] if store == "google" else [])
        for f in price_fields:
            for m in PRICE.finditer(d.get(f, "")):
                fails.append("price or promotion word %r in %s" % (m.group(0), f))
    for f in FIELDS:
        for m in OFFICIAL.finditer(d.get(f, "")):
            fails.append("'official' in %s implies you are the vendor" % f)
        for m in SOFT.finditer(d.get(f, "")):
            warns.append("%r in %s: describes your product by reference to another; reword" % (m.group(0), f))
    kw = d.get("keywords", "")
    if kw:
        if re.search(r",\s+|\s+,", kw):
            warns.append("keywords contain spaces around commas: those characters are wasted")
        words = [w.strip().lower() for w in kw.split(",") if w.strip()]
        dup = sorted({w for w in words if words.count(w) > 1})
        if dup:
            warns.append("repeated keywords: " + ", ".join(dup))
        indexed = set(re.findall(r"[a-z0-9]+", (d.get("title", "") + " " + d.get("subtitle", "")).lower()))
        overlap = sorted({w for w in words if w in indexed})
        if overlap and store == "apple":
            warns.append("keywords already in title or subtitle (indexed there): " + ", ".join(overlap))
    return {"passed": not fails, "store": store, "lengths": lengths, "fails": fails, "warns": warns}


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
    p.add_argument("listing")
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    try:
        rep = lint(load(a.listing))
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print("store: %s   lengths: %s" % (rep["store"], ", ".join("%s %d" % kv for kv in rep["lengths"].items()) or "none"))
    for f in rep["fails"]:
        print("FAIL  " + f)
    for w in rep["warns"]:
        print("WARN  " + w)
    print("\n%s" % ("PASS" if rep["passed"] else "FAIL: %d problem(s) to fix before launch" % len(rep["fails"])))
    print("Limits are as best known when written; confirm against the store's current rules before submitting.")
    if a.json:
        try:
            safe_write(a.json, json.dumps(rep, indent=2, allow_nan=False), [a.listing])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
