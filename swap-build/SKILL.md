---
name: swap-build
description: >
  Builds the replacement one feature at a time from the scoped feature list and the architecture, first
  slice first, and marks a feature done only when it has been run and the evidence is logged. Keeps the
  master feature list's status column honest (todo, partial, done). Use for "build the replacement",
  "start building from the scope", "build the first slice", "implement the swap", "build the next
  feature". Both tracks of the swap series. Do NOT use to plan the stack or schema, use swap-architect. Do
  NOT use to hunt for bugs across the finished build, use swap-test. Do NOT use to score the build against
  the scope, use swap-diff.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Build

## Purpose
Turn the architecture and the scoped feature list into working software, with proof for every feature marked done. Speed comes from the scope being small; honesty comes from the evidence log.

Step 7 or 8 depending on track. Reads `swap/architecture.md`, `swap/features.csv`, `swap/design/`; writes code in the project's own repository, `swap/build-log.md`, and updates the `status` column.

## Mode
Read `swap/mode.txt` (`lean` or `full`). Same method in both tracks. In **full**, the in-scope list is much longer, so keep slices small and the first-slice checkpoint firm; tenancy, sign-up and billing are built by `swap-backend` after the core flows work.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Architecture | `swap/architecture.md` | Stack, schema and constraints, build order, security rules |
| Master list | `swap/features.csv` | In-scope rows and their `status` |
| Design | `swap/design/tokens.json`, `components.md` | Exact tokens and component states |
| Data model | `swap/data-model.md` | Required fields and rules |
| The repository | The project's own code and tests | Conventions to match |

## Quick Start
1. Check `swap/architecture.md` exists and its gate passed. If not, stop.
2. Take the first slice from `swap/scope.md`. Build it end to end before anything else.
3. For each feature: write the failing check, build it, run it, log the evidence, set `status`.
4. Commit after each finished feature. Do not push without the user's yes.

## Workflow
1. **Schema first.** Create the tables and the constraints that enforce the old tool's business rules. Run a check that violating each rule is rejected.
2. **One feature at a time, in `features.csv` order** (must before should before could; the first slice before all of them). A feature is a vertical slice: data, logic, screen, error and empty states.
3. **Evidence before `done`.** For each feature, append to `swap/build-log.md`: the feature name, the command or steps run, and what was observed (test output, screenshot path, API response). No log line, no `done`. A feature that works for the happy path only is `partial`.
4. **Match the design tokens exactly.** Use values from `tokens.json`; do not invent colours or spacing.
5. **Keep scope honest.** If you want to build something not in the list, stop and ask. If the user approves, add a row with `in_scope=no` and `status=added`, so the parity report shows it as an extra rather than hiding it.
6. **Secrets and data.** Credentials come from environment variables. Test data is invented, never a copy of customer records.
7. **Stop at the first-slice checkpoint** and show the user the working flow before building the rest.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "It compiles, mark it done" | Compiles is not works. `done` needs a logged run. |
| "I'll add that handy extra while I'm here" | Every extra is code to test and maintain, and it hides in the parity score. Ask first. |
| "Constraint in the app code is enough" | A second path (import, API, script) bypasses it. The database enforces the rule. |
| "Use a real customer record for the test" | Customer data does not belong in tests or logs. Invent it. |
| "Build all the screens, then test" | Bugs found late cost most. Slice, run, log, repeat. |

## Output Format
EXACT. `swap/build-log.md`: one block per feature, headings `### <feature>`, then `Run:`, `Observed:`, `Status:` (partial or done), `Commit:`. The `status` column in `swap/features.csv` is the only file column you change here, and only for rows with `in_scope=yes`.

**Reference Output** (invented example, abridged):

```
### Online booking page
Run: opened /book as a guest and booked Tuesday 10:00; ran the booking spec.
Observed: 14 tests pass; the slot left the list; the confirmation email arrived in the test inbox.
Status: done
Commit: a1b2c3d
```

## Rules
- Write original code, names and structure. Do not copy the vendor's code, assets, copy, logos or private API shapes.
- Never print or commit a credential; confirm `.env` and any data exports are git-ignored.
- Push, deploy and any production write wait for the user's yes.

## Cross-Skill Routing
All in-scope must-haves `done`. **Lean:** `swap-migrate` for the data and `swap-test` for the bugs (either order). **Full:** `swap-backend` (accounts, isolation, billing) first, then `swap-test`; the product is not ready for the gate until backend is done. A feature turns out to be larger than scoped -> tell the user, update the effort, rerun `swap-roi` forecast.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] Every in-scope row marked `done` has a matching block in `swap/build-log.md` with a `Run:` and `Observed:`
- [ ] The test or check command for the schema constraints was run and its output is in the log
- [ ] No feature outside `in_scope=yes` was built, or each extra is listed and approved
- [ ] `git status` shows no secrets, exports or `.env` staged
- [ ] The first-slice flow was shown to the user before the rest was built

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
