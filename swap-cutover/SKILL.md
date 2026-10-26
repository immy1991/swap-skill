---
name: swap-cutover
description: >
  Runs the switch from the old tool to the replacement safely: a go or no-go gate by script, a
  parallel-run window, a final data migration, the cutover itself, a written rollback, and the
  cancellation of the old subscription before its notice deadline. Drafts the cancellation; the owner
  sends it. Use for "switch us over", "cut over to the new system", "when can we cancel the old tool", "go
  live with the replacement", "retire the old software". Lean track of the swap series. Do NOT use to
  rehearse the data move, use swap-migrate. Do NOT use to find bugs first, use swap-test. Do NOT use to
  check parity, use swap-diff.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Cutover

## Purpose
Move the business onto the new system with a way back, and stop paying for the old one at the right moment: not before the new system is proven, not after another term has been charged.

Lean track only (the full track ends in `swap-deploy`). Reads every earlier output in `swap/`; writes `swap/cutover.md` and `swap/preflight.json`.

## Mode
Read `swap/mode.txt` (`lean` or `full`). Lean track only. Run the gate as `scripts/preflight.py --mode lean` (the default). A product being sold goes live through `swap-deploy` with `--mode full`; that script is the same file.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Gate inputs | `swap/parity.json`, `swap/mapcheck.json`, `swap/bugs.csv`, `swap/roi.json` | What the script will check |
| Contract | `swap/audit.md` | Renewal date, notice days, export rights, cancellation method |
| Migration plan | `swap/migration/plan.md` | Final-run steps and the freeze |
| Users | The user and the team | Who switches when; who supports whom |

## Quick Start
1. Draft `swap/cutover.md` with a `Rollback:` line and an `Old tool kept until: YYYY-MM-DD` line (exact labels; the gate reads them; the date must not be in the past). If the forecast was MARGINAL, add `Marginal approved by: <name> on <date>`.
2. Run `python3 -I <skill-folder>/scripts/preflight.py --dir swap --renewal <date> --notice-days <n> --json swap/preflight.json` from the project root (<skill-folder> is this skill's folder).
3. NO-GO: fix what it names, rerun. GO: schedule the window with the user.
4. Run the cutover steps. Re-run the gate before the cancellation.

## Workflow
1. **Gate by script.** Preflight first checks `swap/mode.txt` says `lean` and that each artifact has the fields its script writes (a hand-typed stub fails). It then checks parity is shippable, the migration reconciles (matched by a key), no S1 or S2 bug is unfixed, the swap still pays back, and the rollback and overlap are written down. It prints the last day to cancel without another term. Do not proceed on NO-GO, and do not argue with it in prose; fix the input.
2. **Choose the window.** A quiet period, a day the user can watch it, not a Friday evening. Tell the people affected, and when.
3. **Freeze and final export.** Stop edits in the old tool for the agreed window, take a fresh export, import it into the new system, and rerun the `swap-migrate` check on this final data. It must pass.
4. **Switch.** Move users, integrations and any inbound links or webhooks to the new system. Keep a list so nothing still points at the old one.
5. **Watch.** Check the new system at the end of day 1, day 7 and day 30: errors, support questions, data discrepancies. Log what you see in `cutover.md`.
6. **Rollback.** Write the exact steps to return to the old tool, who decides, and the point after which rollback is no longer possible (usually when the old subscription ends). Keep the old tool running read-only until `Old tool kept until`.
7. **Cancel last, and not by Claude.** Take a complete final export of the old tool for the business's records first. Then draft the cancellation message and show the cancel-by date; the owner sends it. Rerun the gate just before.
8. **After 90 days,** run `swap-roi` in actuals mode.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "The tests pass, go live" | The gate also covers the data, the bug log and the rollback. Run it. |
| "Cancel the old tool today to bank the saving" | Cancelling removes the rollback. Cancel after the watch period and before the deadline, not before. |
| "Notice date unknown, assume it's fine" | A missed notice window charges a full extra term. Find the date or say it is unknown. |
| "I'll send the cancellation email for them" | Sending on the owner's behalf is theirs to do. Draft only. |
| "Rollback is obvious" | Obvious plans fail under stress. Write the steps and the cut-off point. |

## Output Format
EXACT. `swap/cutover.md` headings in order: `## Window and people`, `## Final data run`, `## Switch list`, `## Watch log` (day 1, 7, 30), `## Rollback`, `## Cancellation`. It contains the two exact lines `Rollback: <one-sentence summary>` and `Old tool kept until: YYYY-MM-DD`. `swap/preflight.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
Rollback: re-enable Bookly Pro from the final export; the owner decides within 7 days
Old tool kept until: 2027-01-10

## Cancellation
DRAFT for the owner to send, not sent. Cancel by 2027-01-14 to avoid another term.
```

## Rules
- Never cancel, email the vendor, change billing, or touch production without the owner's explicit yes for that action.
- Never delete the old data or the final export.
- Use only the owner's own accounts; do not log in as anyone else.

## Cross-Skill Routing
Cutover complete and watched -> `swap-roi` (actuals) after 90 days. Preflight NO-GO because of parity -> `swap-build`; because of bugs -> `swap-test`; because of data -> `swap-migrate`.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/preflight.json` has `"go": true`, from a run made on the day of the switch
- [ ] The final data run passed `mapcheck` (quote the pass count)
- [ ] `cutover.md` contains the `Rollback:` and `Old tool kept until:` lines
- [ ] The cancel-by date is stated; if it has passed, the next window is named
- [ ] A final export of the old tool exists and its location is recorded
- [ ] The cancellation is a draft awaiting the owner, not sent

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
