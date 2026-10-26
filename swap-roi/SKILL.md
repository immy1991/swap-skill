---
name: swap-roi
description: >
  Works out whether a swap pays back, and checks it again after the switch with real numbers. Lean track:
  replacing a subscription with your own build, with payback, a stress case with cost overrun, and the
  most you can spend. Full track (sell mode): whether a product you will sell pays back, from price,
  churn, acquisition cost and build cost, with unit economics and the lowest cash point. Run as a forecast
  after scope (the go or stop gate) and as actuals 90 days after launch. Use for "does this pay back", "is
  it worth building", "what's the payback on replacing X", "will this product make money", "did the swap
  save money". Do NOT use to list which tools to replace, use swap-audit.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap ROI

## Purpose
Give a verdict on a swap from inputs the user can see on the page, and make the same calculation again after the switch so the forecast is tested against what happened.

Both tracks. It runs twice: **forecast** right after `swap-scope` (a gate before any architecture), and **actuals** about 90 days after `swap-cutover` (lean) or `swap-deploy` (full).

## Mode
Read `swap/mode.txt`. **Lean** uses `scripts/roi.py` (the steps below). **Full** uses `scripts/sellmodel.py`: the question is whether a product you sell pays back, not whether a swap saves money. Its inputs are all flags you supply: `--price`, `--new-per-month`, `--churn` (above zero), `--cac`, `--cost-per-customer-month`, `--fixed-monthly`, build cost (days and rate, from `effort_days_raw`), `--launch-cost`. Write `--json swap/sellmodel.json`. Verdicts: SELL (pays back inside the limit even with build overrun and half the expected acquisition, and LTV:CAC at or above the line), MARGINAL (needs the user's explicit choice with both numbers shown), DON'T SELL (stop). Acquisition and churn are guesses until customers exist: say so in the output, never take them from a "typical" figure, and mark every one as the user's assumption. In actuals mode rerun with real customers, churn and CAC and write `swap/sellmodel-actuals.json`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Audit | `swap/audit.json` | `annual_cost` of the tool, notice and renewal dates |
| Scope | `swap/scope.json` | `effort_days_raw` (use the RAW figure; see rule 1) |
| Architecture | `swap/architecture.md` (if present) | Yearly hosting and service costs |
| The user | Their day rate, hourly rate, price-rise history, the old contract | Everything priced by a person |
| Actuals mode | Invoices, hosting bills, time log | What the build and the first 90 days really cost |

## Quick Start
1. Say the mode: forecast or actuals.
2. Collect the inputs below. Every one is an explicit flag; ask for the missing ones in one batched message.
3. Run `python3 -I <skill-folder>/scripts/roi.py ... --json swap/roi.json` (actuals: `--json swap/roi-actuals.json`) from the project root (<skill-folder> is this skill's folder).
4. Print the table and warnings as the script prints them. Write `swap/roi.md`.

Inputs: `--subscription` (per year), `--build-days` and `--day-rate` (or `--build-cost`), `--migration-cost`, `--run-cost` (per year, 0 only if truly free), `--maintenance-hours-month` with `--hourly-rate`, `--price-growth` (fraction), `--overlap-months`, `--overrun`, `--years`, `--payback-limit`.

## Workflow
1. **Rule 1: do not stack contingencies.** `swap-scope` quotes days with a 1.5 multiplier. Here pass the RAW days; this script applies its own overrun in the stress case. Using both counts the cushion twice.
2. **Price every hour.** If the user builds and maintains it, their time has a rate. A build priced at 0 labour or 0 maintenance gets the script's WARNING; keep it in the output.
3. **Run costs come from a real price page or quote,** which the user supplies. Do not look up or invent a price.
4. **Read the verdict as defined by the script:**
   - BUILD: pays back inside the limit even with overrun, and is positive over the horizon. Continue to `swap-architect`.
   - MARGINAL: pays back, but only in the base case or after the limit. Say both numbers and ask the user to choose explicitly. Do not continue on silence. Record the choice as a line `Marginal approved by: <name> on <date>` in the plan file (`cutover.md` or `deploy.md`): the final gate refuses a MARGINAL forecast without it.
   - KEEP SAAS: does not pay back in the horizon. Stop. This is a valid result; say how far off the numbers are and what would have to change (the build budget ceiling is in the output).
5. **Actuals mode:** run the same command with real costs, then put forecast and actual side by side for payback months, build cost and run cost. Explain every gap larger than 20 percent from the user's evidence, not from guesses.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Use the scope total with contingency, to be safe" | The script already stress-tests with an overrun. Doing both double counts. |
| "Their time is free, leave maintenance at 0" | Unpriced time flatters payback and the swap then fails in month 8. |
| "It's marginal, press on" | MARGINAL needs the user's explicit choice with both numbers in front of them. |
| "Assume a typical hosting cost" | Typical is a guess. Ask for the quote or mark the run cost as unknown and stop. |
| "The old price will probably rise 10 percent" | Only use a rise the user has evidence for; the default is 0. |

## Output Format
EXACT. `swap/roi.md` headings in order: `## Mode`, `## Inputs` (each with its source), `## Result` (the script's tables), `## Warnings`, `## Verdict and next step`. In actuals mode add `## Forecast vs actual` as a table. `swap/roi.json` is the script's output, unedited.

**Reference Output** (invented example, abridged):

```
## Verdict and next step
BUILD (lean). Base payback month 11, overrun case month 16, net over 36 months 25,830. Most you can spend and still
pay back inside 18 months: 17,340. Next: swap-architect.

Full mode, same shape: MARGINAL. Base pays back in month 24, the stress case not within 36, lowest cash point -26,552.
Owner's choice recorded: "go on, with a 12-month review". These are the owner's assumptions, not benchmarks.
```

## Rules
- Every number in the verdict traces to an input the user gave or an output file; nothing is looked up.
- Currency: use the one the user states; never infer it.
- Do not present a payback figure without the stress case beside it.

## Cross-Skill Routing
Forecast BUILD (or user-confirmed MARGINAL) -> lean: `swap-architect`. Forecast SELL (or user-confirmed MARGINAL) -> full: `swap-brand` (identity phase) and then `swap-architect`. Forecast KEEP SAAS -> stop and report. Actuals mode complete -> done; offer to run `swap-audit` on the next tool.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] The result file exists (`swap/roi.json` in lean, `swap/sellmodel.json` in full) and `verdict` matches the verdict stated in `roi.md`
- [ ] Both base and stress cases are shown
- [ ] Every input in `## Inputs` names where it came from
- [ ] All script WARNING lines appear in `## Warnings`
- [ ] Build days passed to the script equal `effort_days_raw` from `scope.json`, not the contingency figure
- [ ] For MARGINAL: the user's explicit choice is quoted; for KEEP SAAS: the budget ceiling is quoted

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
