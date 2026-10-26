---
name: swap-diff
description: >
  Scores the finished replacement against the scoped feature list and says whether it can ship. Walks each
  in-scope feature side by side with the old tool, sets its status from what was seen, then runs the
  parity script: weighted score, must-haves done, what is missing, what was cut on purpose, what was added
  beyond scope. A partial must-have blocks shipping whatever the score. Use for "does the new one match
  the old", "how complete is the replacement", "parity check", "what's still missing before we switch",
  "can we ship this". Both tracks of the swap series. Do NOT use to find bugs, use swap-test. Do NOT use
  to scope features, use swap-scope.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Diff

## Purpose
Replace the feeling that it's nearly done with a number and a list, measured against what the business agreed to build, not against everything the vendor sells.

Step 10 or 11 depending on track. Reads `swap/features.csv`, `swap/build-log.md`, `swap/scope.md`; writes `swap/parity.json` and `swap/parity.md`.

## Mode
Read `swap/mode.txt` (`lean` or `full`). In **full**, the scoped list is the vendor's full feature set minus what it owns, so expect more rows and a lower first score. The rule is unchanged: a partial must-have blocks shipping at any score.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Master list | `swap/features.csv` | `in_scope`, `priority`, current `status` |
| Build evidence | `swap/build-log.md` | What was run and observed per feature |
| Scope decisions | `swap/scope.md` | What was cut and why |
| Both systems | The old tool (user's own account) and the new build | Side-by-side behaviour |
| Test log | `swap/bugs.csv` | Open defects that make a feature only partial |

## Quick Start
1. Walk each in-scope flow in the old tool and the new one, side by side with the user where possible.
2. Set each feature's `status` from what you saw: `done`, `partial`, `missing`.
3. Run `python3 -I <skill-folder>/scripts/parity.py swap/features.csv --json swap/parity.json` from the project root (<skill-folder> is this skill's folder).
4. Write `swap/parity.md`. If NOT SHIPPABLE, return the gap list to `swap-build`.

## Workflow
1. **Status comes from observation, not from the build log's claim.** Re-run or re-watch the feature. If the log says done and the feature fails, it is `partial` or `missing`, and the discrepancy goes in the report.
2. **Use the fixed meanings:** `done` works for the flows in scope, including error and empty states; `partial` works for some of it (state what is missing); `missing` does not exist yet. `dropped` is only for rows with `in_scope=no`; `added` is only for extras the user approved.
3. **Run the script and read all of its output,** including contradictions. A row marked in scope but `dropped`, or out of scope but `done`, is a contradiction to fix in the CSV, not to ignore.
4. **Report the three kinds of difference separately:** gaps (in scope, not done), deliberate cuts (out of scope, decided), and extras (built beyond scope).
5. **Decide with the script's rule:** SHIPPABLE needs every in-scope must-have `done` and a score at or above the threshold (default 85, adjustable with a stated reason). Never override a NOT SHIPPABLE verdict in prose.
6. **Link to evidence.** For every gap, cite the flow that fails or the log line missing.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "The build log says done, trust it" | The log is the builder's claim. Diff is the check. |
| "Score is 92, ship it" | A partial must-have blocks shipping at any score. The script enforces it. |
| "Count the out-of-scope features as missing" | They were cut deliberately. They are listed, not scored. |
| "Round the score up" | Quote the script's number. A rounded verdict is not reproducible. |
| "Extra features are a bonus" | Extras are cost nobody scoped. Shown separately so they are noticed. |

## Output Format
EXACT. `swap/parity.md` headings in order: `## Verdict` (SHIPPABLE or NOT SHIPPABLE, score, threshold), `## Table` (the script's priority table), `## Gaps` (each with the failing flow), `## Deliberate cuts`, `## Extras`, `## Contradictions fixed`, `## Next step`. `swap/parity.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
## Verdict
SHIPPABLE. Score 100.0 / 100 (threshold 85) over 8 in-scope features.
First run was 92.1, NOT SHIPPABLE: Email reminders was partial, and it is a must-have.

## Deliberate cuts
Reports, Group classes, Waitlist, Branded mobile app, Partner marketplace, Custom roles.
```

## Rules
- Compare only features and flows, never copy anything the vendor owns while doing so.
- Use only the user's own account of the old tool.
- Do not edit `parity.json` by hand; change the CSV and rerun.

## Cross-Skill Routing
SHIPPABLE -> lean: `swap-cutover`; full: `swap-brand` (its sweep phase, which writes `swap/sweep.json`), then `swap-launch`, then `swap-deploy`. NOT SHIPPABLE -> `swap-build` with the gap list, then `swap-test` for the touched features, then back here.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/parity.json` exists and `shippable` matches the verdict in `parity.md`
- [ ] Every `done` in-scope must-have has a re-run or re-observation noted
- [ ] `contradictions` in the JSON is empty, or each is explained and fixed
- [ ] Score and threshold are quoted exactly as the script printed them
- [ ] Gaps, cuts and extras are in three separate lists

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
