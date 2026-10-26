#!/usr/bin/env python3
"""Structural check for the swap skill series against skill-build-standard.md.

Usage: check.py [skills_dir [min_exclusions]]   (defaults: skills/, 3)
Exit 0 = all pass, 1 = any failure. Report-only: it changes nothing.
"""
import json
import os
import re
import sys

SERIES = ["swap-audit", "swap-market", "swap-recon", "swap-scope", "swap-roi", "swap-brand", "swap-architect",
          "swap-design", "swap-build", "swap-backend", "swap-migrate", "swap-test", "swap-diff", "swap-launch",
          "swap-cutover", "swap-deploy"]
# skills that must say how they behave in each mode (they run in lean, full, or both)
MODE_AWARE = {"swap-audit", "swap-market", "swap-recon", "swap-scope", "swap-roi", "swap-architect", "swap-design",
              "swap-build", "swap-migrate", "swap-test", "swap-diff", "swap-cutover"}
# files that must be byte-identical wherever they appear
SHARED_COPIES = [("swap-cutover", "swap-deploy", "preflight.py"), ("swap-cutover", "swap-deploy", "test_preflight.py")]
HEADINGS = ["## Purpose", "## Context Routing Table", "## Quick Start", "## Workflow", "## Anti-Rationalization",
            "## Output Format", "## Rules", "## Cross-Skill Routing", "## Exit Checklist", "## Self-Improvement"]
FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)
TOOLS = {"swap-audit": ["spend.py"], "swap-scope": ["scope.py"], "swap-design": ["contrast.py"],
         "swap-migrate": ["mapcheck.py"], "swap-diff": ["parity.py"], "swap-roi": ["roi.py", "sellmodel.py"],
         "swap-cutover": ["preflight.py"], "swap-market": ["reviews.py"], "swap-brand": ["sweep.py"],
         "swap-launch": ["listing.py"], "swap-deploy": ["preflight.py"]}


def description(fm):
    m = re.search(r"^description:\s*>\s*\n((?:[ \t]+.*\n?)+)", fm + "\n", re.M)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip()


def check(root, min_excl=3):
    errs = []

    def bad(skill, msg):
        errs.append("%s: %s" % (skill, msg))

    for s in SERIES:
        d = os.path.join(root, s)
        p = os.path.join(d, "SKILL.md")
        if not os.path.isfile(p):
            bad(s, "SKILL.md missing")
            continue
        text = open(p, encoding="utf-8").read()
        m = FM.match(text)
        if not m:
            bad(s, "no frontmatter")
            continue
        fm = m.group(1)
        nm = re.search(r"^name:\s*(\S+)\s*$", fm, re.M)
        if not nm or nm.group(1) != s:
            bad(s, "name does not match folder")
        desc = description(fm)
        if not desc:
            bad(s, "description is not a folded block")
        else:
            if len(desc) >= 1024:
                bad(s, "description is %d chars (limit 1023)" % len(desc))
            if "<" in desc or ">" in desc:
                bad(s, "description contains angle brackets")
            if "Do NOT use" not in desc:
                bad(s, "description has no exclusion")
            for ref in set(re.findall(r"\bswap-[a-z]+(?:-[a-z]+)*\b", desc)):
                if ref not in SERIES:
                    bad(s, "description names a sibling that does not exist: %r (broken by a wrap?)" % ref)
            # a hyphenated name split across lines would leave 'swap- word'
            if re.search(r"swap- \w", desc):
                bad(s, "a swap-* name is split across lines in the description")
            excl = re.findall(r"Do NOT use[^.]*?, use ([a-z0-9-]+)\.", desc)
            if len(excl) < min_excl:
                bad(s, "only %d exclusions that name a skill (need %d)" % (len(excl), min_excl))
        body = text[m.end():]
        if text.count("\n") > 500:
            bad(s, "over 500 lines")
        for h in HEADINGS:
            if h not in body:
                bad(s, "missing heading %r" % h)
        if "**Reference Output**" not in body:
            bad(s, "no Reference Output in the Output Format section (skill-build-standard.md)")
        if "Any feedback to capture for this skill?" not in body:
            bad(s, "self-improvement ask is missing")
        if os.path.exists(os.path.join(d, "README.md")):
            bad(s, "README.md inside the skill folder")
        ev = os.path.join(d, "evals", "evals.json")
        try:
            e = json.load(open(ev, encoding="utf-8"))
            if len(e.get("evals", [])) < 5:
                bad(s, "fewer than 5 evals")
            if e.get("skill_name") != s:
                bad(s, "evals.json skill_name mismatch")
        except Exception as ex:
            bad(s, "evals.json unreadable: %s" % ex)
        for tool in TOOLS.get(s, []):
            for f in (tool, "test_" + tool):
                if not os.path.isfile(os.path.join(d, "scripts", f)):
                    bad(s, "scripts/%s missing" % f)
            if "scripts/" + tool not in body:
                bad(s, "SKILL.md never calls scripts/%s" % tool)
            sp = os.path.join(d, "scripts", tool)
            if os.path.isfile(sp):
                code = open(sp, encoding="utf-8").read()
                # Hostile-input rules, each learned from a reproduced audit finding. A script that reads CSV must
                # survive bad bytes and duplicate headers; one that writes JSON must survive an unwritable path
                # and must not emit NaN/Infinity; one that reads JSON must survive bad bytes.
                if "csv." in code and "UnicodeDecodeError" not in code:
                    bad(s, "scripts/%s reads CSV but never handles UnicodeDecodeError" % tool)
                if "DictReader" in code and "duplicate column" not in code:
                    bad(s, "scripts/%s reads a CSV header but never rejects duplicate column names" % tool)
                if ('"--json"' in code or "json.dump(" in code) and not re.search(r"except \(?OSError", code):
                    bad(s, "scripts/%s writes JSON but never handles an unwritable path" % tool)
                if '"--json"' in code and ("safe_write" not in code or "samefile" not in code):
                    bad(s, "scripts/%s writes a --json report but not through safe_write (input-file, hard-link and symlink checks)" % tool)
                if "DictReader" in code and "different number of cells" not in code:
                    bad(s, "scripts/%s reads CSV rows but never rejects a row with the wrong number of cells" % tool)
                if "json.load(" in code and "UnicodeDecodeError" not in code and "ValueError" not in code:
                    bad(s, "scripts/%s reads JSON but never handles malformed bytes" % tool)
        if s in MODE_AWARE and "swap/mode.txt" not in body:
            bad(s, "does not mention swap/mode.txt (lean/full behaviour)")
        # every scripts/ path mentioned must exist
        for sp in set(re.findall(r"scripts/([A-Za-z0-9_]+\.py)", body)):
            if not os.path.isfile(os.path.join(d, "scripts", sp)):
                bad(s, "SKILL.md names scripts/%s which does not exist" % sp)
        # shared-folder names used across skills must be spelled consistently
        for f in re.findall(r"`swap/([A-Za-z0-9_./-]+)`", body):
            pass
        # private-only markers balanced
        if body.count("<!-- private-only -->") != body.count("<!-- /private-only -->"):
            bad(s, "unbalanced private-only markers")
    for a, b, f in SHARED_COPIES:
        pa, pb = os.path.join(root, a, "scripts", f), os.path.join(root, b, "scripts", f)
        if os.path.isfile(pa) and os.path.isfile(pb):
            if open(pa, "rb").read() != open(pb, "rb").read():
                errs.append("%s and %s copies of %s differ (they must be byte-identical)" % (a, b, f))
        else:
            errs.append("shared file %s missing from %s or %s" % (f, a, b))
    return errs


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "skills"
    errs = check(root, int(sys.argv[2]) if len(sys.argv) > 2 else 3)
    for e in errs:
        print("FAIL " + e)
    print("SWAP_SERIES_CHECK: %s (%d skills)" % ("ALL PASS" if not errs else "%d FAIL" % len(errs), len(SERIES)))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
