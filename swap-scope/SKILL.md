---
name: swap-scope
description: >
  Cuts a mapped tool down to the features a business really uses and adds up the build effort. Runs every
  feature through fixed rules (vendor-owned, unused, unknown, must, should, could), holds back anything
  undecided, estimates days with a contingency multiplier, and writes the master feature list the build
  and diff steps use. Use for "scope the replacement", "what do we actually need to build", "cut this to
  the 20% we use", "estimate the build", "what's in and out". Step 3 of both tracks of the swap series. Do
  NOT use to map the tool in the first place, use swap-recon. Do NOT use to decide whether the swap pays
  back, use swap-roi. Do NOT use to plan the stack and schema, use swap-architect.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Scope

## Purpose
Decide what gets built, what is left out and why, and what it will take, using rules a person can audit. A feature nobody uses, or that the vendor owns, never enters the build.

Step 3 of both tracks. Reads `swap/features.csv` and `swap/recon.md`; writes `swap/scope.md`, `swap/scope.json` and the annotated master `swap/features.csv`.

## Mode
Read `swap/mode.txt` and pass it: `<skill-folder>/scripts/scope.py ... --mode lean|full`.
- **Lean (default):** the rules in the workflow below.
- **Full:** the product is for sale, so nothing is judged by this business's own use. Everything the vendor does not own and that is not dead (`usage=never`) is in scope, whatever its priority; there is no HOLD. Expect a much larger estimate, and say so. `priority` still orders the build and weights the parity score.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Feature list | `swap/features.csv` (from swap-recon) | Priority, usage, kind, confirmed |
| Recon notes | `swap/recon.md`, `swap/data-model.md` | Size drivers, integrations, unknowns |
| Users | The people named in recon | Answers for every `unknown` usage; effort sanity checks |

## Quick Start
Commands run from the project root; `<skill-folder>` is this skill's folder. Below, `[--subset swap/subset.txt]` is added in full mode after a NARROW verdict (step 3) and left out otherwise; `<mode>` is the contents of `swap/mode.txt`.
1. **First scoping only:** move the recon list aside, `mv swap/features.csv swap/features.recon.csv`. From now on the recon list is the input, and `swap/features.csv` becomes the master the build and diff steps use. (The annotate step refuses to write over an existing master.)
2. Get `effort_days` for every row that could be in scope from the builder, in `swap/features.recon.csv`. If there is no builder yet, give your own estimate and label it as yours; never fill a number nobody made.
3. **Full mode after a NARROW verdict:** write the approved feature names, one per line, to `swap/subset.txt` (from `## Approved subset` in `market.md`). Anything not listed will be out of scope with that reason.
4. **Look first, write nothing:** `python3 -I <skill-folder>/scripts/scope.py swap/features.recon.csv --mode <mode> [--subset swap/subset.txt]`. Resolve every HOLD row by asking a user and updating `usage` (or, if nobody can say, add `--backlog-unknown`); rerun until HOLD is empty.
5. **Write the outputs:** the same command plus `--json swap/scope.json --annotate swap/features.csv`. That creates the master with `in_scope` and `status`, copying `effort_days` exactly as written. **Rescoping later** (usage changed, a feature added): the same command plus `--rescope`; statuses and extra columns of features still in scope are kept, and anything done or partial that is now out of scope is reported. Never delete the master to rescope: that resets every status to todo.
6. Write `swap/scope.md`.

## Workflow
1. **Let the script decide, then argue with it in writing.** The rules are fixed (see the script's docstring): vendor-owned out; never-used out; unknown on hold; must in; should in if used at least monthly; could in only if daily; integrations in only if used monthly or more. A person may override a lean-mode decision only by editing the CSV and saying why in `scope.md`. **One rule cannot be overridden by anyone: a vendor-owned item (`kind` network, content or licence) stays out of scope.** Changing its `kind` to get it in is falsifying the list.
2. **Never guess usage to clear a HOLD.** Ask. If nobody can say, rerun with `--backlog-unknown` (lean only): the feature stays out and goes to the backlog with the reason "usage unknown and nobody could say". Its `usage` stays `unknown` in the file; it is never changed to a guess.
3. **Estimate in days, with the contingency.** The script prints raw days and days with the multiplier (default 1.5). Quote both. A row with no estimate is listed and makes the total "incomplete"; do not fill it silently.
4. **Write the out-of-scope list as carefully as the in-scope one.** Each line says why, so nobody rebuilds it later by accident.
5. **Name the first slice:** the smallest set of in-scope features that makes one real workflow work end to end.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "It's a must-have, so include it" | A must the vendor owns (a network, content, a licence) cannot be rebuilt. The script rules it out. |
| "Usage is unknown but it's probably used" | Probably-used features are how scope doubles. Ask, or backlog it. |
| "The estimate is just a bit short, round it up" | Unestimated rows stay unestimated and the total says incomplete. |
| "Include the could-haves, they're cheap" | Cheap features still cost tests, docs and maintenance forever. Daily-use only. |

## Output Format
EXACT. `swap/scope.md` headings in order: `## Decision summary` (counts in / out / hold, effort raw and with contingency), `## In scope` (script table), `## Out of scope` (each with reason), `## Overrides` (any manual change and why, or "none"), `## First slice`, `## Open questions`. `swap/scope.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
## Decision summary
In 8, out 6, hold 0. Effort 18.5 days raw, 27.75 with x1.5 contingency.

## Out of scope
- Partner marketplace: vendor-owned (network): not rebuildable
- Waitlist: nobody uses it

## First slice
Online booking page, staff availability and email reminders, end to end.
```

## Rules
- Rebuild what the software does, never what the vendor owns: no copied code, assets, logos, trademarks, copy or content.
- Do not put estimates into the CSV that nobody made.
- Do not edit `scope.json` by hand; rerun the script.

## Cross-Skill Routing
HOLD empty and estimate complete -> `swap-roi` in forecast mode (it decides whether to continue). Estimate incomplete -> say what is missing and stop.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/scope.json` counts add up: in + out + hold equals the number of rows in the CSV
- [ ] `hold` is empty, or the run stopped here and says so
- [ ] Every out-of-scope row has a reason in the output
- [ ] `estimate_complete` is true, or `unestimated_in_scope` is listed in Open questions
- [ ] The master `swap/features.csv` has `in_scope` and `status` columns and no `todo` on an out-of-scope row
- [ ] Both effort figures (raw and with contingency) are quoted
- [ ] `mode` in `swap/scope.json` equals the contents of `swap/mode.txt`

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
