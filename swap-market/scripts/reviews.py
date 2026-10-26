#!/usr/bin/env python3
"""Turn public reviews into ranked complaints, with a link on every quote.

Standard library only. Never touches the network: you collect the reviews (from public
pages you are allowed to read), this counts and quotes them.

Usage:
  reviews.py reviews.csv [--max-rating 2] [--themes themes.json] [--json out.json]

reviews.csv columns
  required: source, url, rating (1-5), text
  optional: date

Rules the script enforces
  - A row without an http(s) link is dropped and counted. No link, no quote.
  - Duplicates are dropped and counted: the same text under the same link, or identical text (ignoring case
    and spacing) under different links, which is how syndicated and copied reviews inflate a count.
  - A "source" is the web host of the link (www. removed), never the label you typed, so three labels on one
    site count as one source. The label is only shown next to a quote.
  - Every quote printed is a verbatim substring of the review it came from, shown with that
    review's link, source and rating. Nothing is paraphrased or composed.
  - A theme with fewer than 3 reviews, or only 1 source, is marked THIN.
  - Themes are assigned by keyword match, which is a rough filter: read the quotes.

themes.json (optional): {"pricing": ["price", "expensive"], "support": ["support", "no reply"]}
Keywords match case-insensitively as whole words or phrases.

Exit codes: 0 ok, 2 bad input.
"""
import argparse
import csv
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlsplit

DEFAULT_THEMES = {
    "pricing": ["price", "pricing", "expensive", "costs too much", "per seat", "per user", "overpriced", "subscription"],
    "reliability": ["bug", "bugs", "buggy", "crash", "crashes", "crashed", "crashing", "broken", "outage", "glitch",
                    "glitchy", "freezes", "freezing", "lost data", "slow"],
    "support": ["support", "customer service", "no reply", "no response", "ticket", "unhelpful"],
    "missing features": ["missing", "wish", "no way to", "can't", "cannot", "doesn't have", "does not have", "lacks"],
    "usability": ["confusing", "hard to use", "clunky", "complicated", "unintuitive", "difficult"],
    "lock-in and data": ["export", "locked in", "lock-in", "cancel", "refund", "data"],
}
URL = re.compile(r"^https?://[^\s/]+\.[^\s/]+", re.I)


class InputError(Exception):
    pass


def load(path):
    try:
        fh = open(path, newline="", encoding="utf-8-sig")
    except OSError as e:
        raise InputError("cannot read %s: %s" % (path, e))
    try:
        return _load_rows(fh)
    except (UnicodeDecodeError, csv.Error) as e:
        raise InputError("reviews file is not readable CSV text: %s" % e)


def _load_rows(fh):
    with fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise InputError("empty file")
        reader.fieldnames = [n.strip() for n in reader.fieldnames]
        if len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise InputError("duplicate column names: the last one would silently win")
        for c in ("source", "url", "rating", "text"):
            if c not in reader.fieldnames:
                raise InputError("missing required column '%s'" % c)
        rows = []
        for i, r in enumerate(reader, start=2):
            if None in r or None in r.values():
                raise InputError("line %d has a different number of cells than the header" % i)
            if not any((v or "").strip() for v in r.values() if isinstance(v, str)):
                continue
            raw = (r.get("rating") or "").strip()
            try:
                rating = float(raw)
            except ValueError:
                raise InputError("line %d: rating must be a number 1 to 5, got %r" % (i, raw))
            if not (1.0 <= rating <= 5.0) or rating != rating:
                raise InputError("line %d: rating must be from 1 to 5, got %r" % (i, raw))
            text = (r.get("text") or "").strip()
            if not text:
                raise InputError("line %d: text is blank" % i)
            rows.append({"source": (r.get("source") or "").strip() or "unknown", "url": (r.get("url") or "").strip(),
                         "rating": rating, "text": text, "date": (r.get("date") or "").strip(), "line": i})
    if not rows:
        raise InputError("no data rows")
    return rows


def load_themes(path):
    if not path:
        return DEFAULT_THEMES
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError) as e:
        raise InputError("cannot read themes file: %s" % e)
    if not isinstance(d, dict) or not d:
        raise InputError("themes file must be a non-empty object")
    for k, v in d.items():
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            raise InputError("theme %r must be a non-empty list of keywords" % k)
    return d


def kw_regex(words):
    return re.compile(r"(?<![\w])(?:" + "|".join(re.escape(w.strip()) for w in words) + r")(?![\w])", re.I)


def excerpt(text, match):
    """Return the sentence containing the match, as an exact substring of text, at most 240 chars."""
    start = max(text.rfind(c, 0, match.start()) for c in ".!?\n")
    start = 0 if start < 0 else start + 1
    ends = [text.find(c, match.end()) for c in ".!?\n"]
    ends = [e for e in ends if e >= 0]
    end = (min(ends) + 1) if ends else len(text)
    if end - start > 240:
        # a long sentence: keep a 240-character window that contains the matched keyword
        start = max(start, match.start() - 120)
        end = min(end, max(start + 240, match.end()))
    q = text[start:end].strip()
    assert q in text and match.group(0).lower() in q.lower(), "excerpt is not a verbatim substring around the match"
    return q, (start > 0 and text[:start].strip() not in ("",)) or end < len(text)


def host_of(url):
    try:
        h = (urlsplit(url).hostname or "").lower()
    except ValueError:                      # e.g. an unclosed [ in the link
        return ""
    return h[4:] if h.startswith("www.") else h


def run(rows, max_rating, themes):
    kept, no_link, dupes, seen = [], 0, 0, set()
    for r in rows:
        if not URL.match(r["url"]) or not host_of(r["url"]):
            no_link += 1
            continue
        key = re.sub(r"\s+", " ", r["text"]).strip().lower()
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        r["host"] = host_of(r["url"])
        kept.append(r)
    neg = [r for r in kept if r["rating"] <= max_rating]
    sources = {}
    for r in kept:
        sources[r["host"]] = sources.get(r["host"], 0) + 1
    out_themes = []
    themed_ids = set()
    for name, words in themes.items():
        rx = kw_regex(words)
        hits = []
        for r in neg:
            m = rx.search(r["text"])
            if m:
                hits.append((r, m))
        for r, _ in hits:
            themed_ids.add(id(r))
        hits.sort(key=lambda h: (h[0]["rating"], h[0]["date"] or "~", h[0]["line"]))
        srcs = {h[0]["host"] for h in hits}
        out_themes.append({
            "theme": name, "reviews": len(hits), "sources": len(srcs),
            "share_of_negative": round(len(hits) / len(neg), 3) if neg else 0.0,
            "thin": len(hits) < 3 or len(srcs) < 2,
            "quotes": [dict(zip(("quote", "cut"), excerpt(r["text"], m)), url=r["url"], source=r["source"], rating=r["rating"])
                       for r, m in hits[:3]],
        })
    out_themes = [t for t in out_themes if t["reviews"] > 0]
    out_themes.sort(key=lambda t: (-t["reviews"], t["theme"]))
    return {
        "max_rating": max_rating,
        "rows_given": len(rows), "dropped_no_link": no_link, "dropped_duplicates": dupes,
        "reviews_used": len(kept), "negative_reviews": len(neg), "by_source": sources,
        "unthemed_negative": len([r for r in neg if id(r) not in themed_ids]),
        "small_sample": len(kept) < 30, "themes": out_themes,
    }


def fmt(rep):
    L = ["Sample: %d reviews with links from %d web host(s) (%s); %d negative (rating %g or below). "
         "Dropped: %d with no link, %d duplicates (same text)." % (
             rep["reviews_used"], len(rep["by_source"]),
             ", ".join("%s %d" % kv for kv in sorted(rep["by_source"].items())),
             rep["negative_reviews"], rep["max_rating"], rep["dropped_no_link"], rep["dropped_duplicates"])]
    if rep["small_sample"]:
        L.append("SMALL SAMPLE: under 30 reviews. Treat every theme as a lead to check, not a finding.")
    L.append("")
    for t in rep["themes"]:
        L.append("## %s: %d negative review(s), %d web host(s), %.0f%% of negatives%s" % (
            t["theme"], t["reviews"], t["sources"], t["share_of_negative"] * 100, "  [THIN]" if t["thin"] else ""))
        for q in t["quotes"]:
            L.append('- %s"%s"%s (%s, %g stars) %s' % ("... " if q["cut"] else "", q["quote"], " ..." if q["cut"] else "",
                                                       q["source"], q["rating"], q["url"]))
        L.append("")
    if rep["unthemed_negative"]:
        L.append("%d negative review(s) matched no theme: read them for a theme the keywords missed." % rep["unthemed_negative"])
    L.append("Themes come from keyword matches. A count is a lead, not a finding, until you have read the quotes.")
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
    p.add_argument("--max-rating", type=float, default=2.0)
    p.add_argument("--themes", default=None)
    p.add_argument("--json", default=None)
    a = p.parse_args(argv)
    if not (1.0 <= a.max_rating <= 5.0):
        print("error: --max-rating must be from 1 to 5", file=sys.stderr)
        return 2
    try:
        rep = run(load(a.csv), a.max_rating, load_themes(a.themes))
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print(fmt(rep))
    if a.json:
        try:
            safe_write(a.json, json.dumps(rep, indent=2, allow_nan=False), [a.csv, a.themes])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (a.json, e), file=sys.stderr)
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
