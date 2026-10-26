---
name: swap-test
description: >
  Tests the replacement by walking every in-scope flow, writing automated specs for the happy paths and
  the edge cases that bite (time zones, two people at once, double submit, empty and error states,
  permissions), and logging each bug by severity until no S1 or S2 remains open. Use for "test the
  replacement", "find the bugs before we switch", "write the test plan", "click through every flow", "is
  it safe to cut over". Both tracks of the swap series. Do NOT use to score completeness against the
  scope, use swap-diff.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Test

## Purpose
Find what is broken before the business depends on the new system, and leave a bug log the cutover gate can read.

Step 9 or 10 depending on track. Reads `swap/recon.md` (flows), `swap/features.csv`, `swap/architecture.md`; writes `swap/test-plan.md`, specs in the project's test folder, and `swap/bugs.csv`.

## Mode
Read `swap/mode.txt` (`lean` or `full`). In **full**, also test what strangers will do: sign-up and login paths, one customer trying to reach another's data (the isolation tests from `swap-backend` run again here), billing flows in the provider's test mode, and the empty first-run experience with no data.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Flows | `swap/recon.md` | The flows people really follow |
| Scope | `swap/features.csv` | In-scope features to cover |
| Rules | `swap/architecture.md` | Business rules and constraints that must hold |
| The running build | A local or staging URL | What to drive |
| Real users | The people who use the old tool | The mistakes they make and the odd cases they hit |

## Quick Start
1. Write `swap/test-plan.md`: one row per flow and per business rule.
2. Create `swap/bugs.csv` with the header below, even before any bug exists (the cutover gate needs the file).
3. Write and run specs for the happy path of each flow, then the edge cases.
4. Log every defect. Fix S1 and S2, rerun, repeat.

## Workflow
1. **Plan from the flows and the rules,** not from the screens. Each in-scope flow gets a happy-path test; each business rule (from the schema constraints) gets a test that tries to break it.
2. **Cover the edge cases that real use finds:** the same record edited by two people, a double click on submit, a slot or stock item taken mid-action, time zones and daylight saving, empty lists, very long text, missing optional data, a user without permission, a failed external call, a refresh in the middle of a flow.
3. **Severity is fixed:** S1 data loss, security hole, or a core flow cannot be completed. S2 a core flow breaks for some users or shows wrong numbers. S3 a minor flow or wording problem with a workaround. S4 cosmetic. Argue severity in `bugs.csv`, never by quietly relabelling.
4. **Log every bug as it is found,** with steps to reproduce. `status` is `open`, `fixed` or `accepted`. S1 and S2 can never be `accepted`.
5. **A fix is `fixed` only after the failing test passes** and the earlier suite still passes.
6. **Stop when** no S1 or S2 is open and every in-scope flow has a passing happy-path spec. S3 and S4 may stay open if the user accepts them in writing in the log.
7. **Security pass.** Check that anything private requires login, that one user cannot read another's data by changing an id, and that secrets are not in the repository.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "The happy path passes, ship it" | The old tool's users find the edge cases on day one. Test them first. |
| "That's only S3" | Check it against the fixed definitions. Wrong numbers are S2, not S3. |
| "No bugs found, skip the log file" | The cutover gate needs `bugs.csv`. An empty log with a header is a result. |
| "Mark it accepted and move on" | S1 and S2 cannot be accepted. Fix them. |
| "I fixed it, mark fixed" | Only after the test that failed now passes. Show the output. |

## Output Format
EXACT. `swap/bugs.csv` header: `id,severity,status,feature,summary,steps,found,fixed`. `swap/test-plan.md` headings in order: `## Flows`, `## Business rules`, `## Edge cases`, `## Security checks`, `## Results` (pass/fail counts per run with the command used).

**Reference Output** (invented example, abridged):

```
bugs.csv
id,severity,status,feature,summary,steps,found,fixed
1,S2,fixed,Payments at booking,Refund total wrong,refund a part-paid booking,2026-10-24,2026-10-25

## Results
62 passed, 0 failed (full suite, 2026-10-25). Cross-tenant spec included.
```

## Rules
- Test with invented data, never customer records.
- Run only against local or staging environments. Production writes wait for the user's yes.
- Never record a credential in a bug report.

## Cross-Skill Routing
No S1 or S2 open -> `swap-diff`. Many S1 bugs in one feature -> send that feature back to `swap-build` with the log.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/bugs.csv` exists and its header is exactly `id,severity,status,feature,summary,steps,found,fixed`
- [ ] No row has severity S1 or S2 with status other than `fixed`
- [ ] Every in-scope flow in `swap/recon.md` has a passing happy-path spec (test command and result quoted)
- [ ] Every business rule in the schema has a test that tries to break it
- [ ] The last full-suite run is quoted with date, command and pass/fail counts

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
