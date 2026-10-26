---
name: swap-architect
description: >
  Plans how to build the replacement: first checks whether an existing open-source or low-code tool
  already covers the scoped features, then picks the stack, database schema, API and hosting, names every
  rule the old tool enforced that the new data model must enforce, and orders the build so one real
  workflow works first. Use for "plan the stack for this", "design the schema", "how should we build the
  replacement", "architecture for the swap", "what should this run on". Needs a swap-roi forecast that
  says BUILD (lean) or SELL (full). Do NOT use to decide whether to build at all, use swap-roi. Do NOT use
  to scope features, use swap-scope.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Architect

## Purpose
Choose the smallest architecture that delivers the in-scope features, with a schema that enforces the old tool's business rules and a build order that proves value early.

Step 4 or 6 depending on track (after the `roi` forecast). Reads `swap/scope.json`, `swap/data-model.md`, and the gate file (`swap/roi.json` in lean, `swap/sellmodel.json` in full); writes `swap/architecture.md`.

## Mode
Read `swap/mode.txt`. The gate is `swap/roi.json` in lean and `swap/sellmodel.json` in full (SELL, or MARGINAL with the user's recorded choice). In **full**, also plan for many customers: tenancy approach, a billing provider with hosted checkout, per-customer limits, and a plan for the product's own data export. Hand tenancy, auth and billing build-out to `swap-backend`. If adopting open-source in full mode, its licence must permit commercial resale; record the clause (copyleft licences can force you to publish your changes).

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Gate | `swap/roi.json` (lean) or `swap/sellmodel.json` (full) | `verdict` must be BUILD or SELL, or MARGINAL with the user's recorded choice. KEEP SAAS, DON'T SELL or missing = stop |
| Scope | `swap/scope.json`, `swap/features.csv` | In-scope features, first slice, integrations |
| Data model | `swap/data-model.md` | Entities, required fields, relationships, row counts |
| The team | The user | Who will maintain it and in what language; where it will be hosted; data-residency or compliance limits |

## Quick Start
1. Check the gate for the track: `roi.json` (lean) or `sellmodel.json` (full). Missing, or a stopping verdict: stop and run `swap-roi`.
2. Run the adopt-or-build check below. Record the answer first.
3. Draft stack, schema, API, hosting, security, build order.
4. Write `swap/architecture.md`, then send its yearly run cost back to `swap-roi` if it differs from the forecast input.

## Workflow
1. **Adopt, assemble or build (decide first, with reasons).**
   - **Adopt:** an open-source or self-hostable tool already covers most in-scope must and should features. Then the build is configuration plus the gaps. Prefer this when it covers roughly four in five in-scope features and its licence permits the use.
   - **Assemble:** low-code or automation tools cover the workflows and the data is simple. Prefer when the team already runs them and the volume is small.
   - **Build:** custom code, when neither covers the core workflow or the data rules are specific.
   State which, the evidence (the features it covers, by name), and the main cost of the choice.
2. **Pick the stack the maintainer can run.** Prefer the language and hosting the maintainer already knows. A boring, widely used stack beats a clever one: it is cheaper to fix in two years.
3. **Write the schema from `data-model.md`.** For every rule the old tool enforced (no double bookings, unique invoice numbers, required fields, status transitions), write the constraint that enforces it in the database, not only in the UI.
4. **List the API or screens needed per in-scope feature.** Each feature in `features.csv` maps to at least one named endpoint or screen; a feature with none is a gap.
5. **Security and recovery.** Authentication method, who can see what, secrets handling (environment variables only), backups with a tested restore, and how the data leaves again (the new system must be exportable too).
6. **Run cost.** Itemise hosting and services per year from real price pages the user supplies. Update `swap-roi` if the figure changed.
7. **Order the build.** First slice end to end, then the rest by priority. Migration is its own late step; plan it now.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Custom build is the point, skip the adopt check" | Not building is the cheapest swap. If a covered tool exists, the check pays for itself. |
| "The UI validates it, no need for a constraint" | An import script, an API call or a second screen bypasses the UI. Rules belong in the database. |
| "Pick the newest stack" | The maintainer inherits it. Choose what they can run and fix. |
| "Backups later" | A restore nobody has tried is not a backup. Plan the test now. |

## Output Format
EXACT. `swap/architecture.md` headings in order: `## Gate` (roi verdict quoted), `## Adopt, assemble or build` (decision, evidence, cost of the choice), `## Stack`, `## Schema` (tables, keys, constraints, one line per business rule), `## Features to endpoints` (table), `## Security and recovery`, `## Run cost per year`, `## Build order`, `## Risks and gaps`.

**Reference Output** (invented example, abridged):

```
## Adopt, assemble or build
Build. Checked a self-hosted scheduler: it covers 5 of 8 in-scope features, under the four-in-five line, and its
licence bars resale. Cost of the choice: 18.5 days of build.

## Schema
bookings(staff_id, starts_at, ends_at): exclusion constraint on overlapping ranges per staff, so a double booking
is rejected by the database, not just the screen.
```

## Rules
- Design your own schema, names and structure from the business's data. Do not copy the vendor's internal schema, API shapes, code or assets.
- Credentials in environment variables only; none in the repository or in `swap/`.
- If the chosen option needs a licence, read and record its terms.

## Cross-Skill Routing
Architecture written -> `swap-design` for anything with a user interface, then `swap-build`. Run cost differs from the forecast by more than 20 percent -> rerun `swap-roi` first.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] The gate file for the track (`roi.json` or `sellmodel.json`) has an allowed verdict (or MARGINAL with a quoted user choice)
- [ ] The adopt-or-build decision names at least one alternative that was checked
- [ ] Every row of `swap/features.csv` with `in_scope=yes` appears in `## Features to endpoints`
- [ ] Every business rule in `data-model.md` has a constraint line in `## Schema`
- [ ] A restore test is written into `## Security and recovery`
- [ ] `## Run cost per year` is itemised and compared with the roi input

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
