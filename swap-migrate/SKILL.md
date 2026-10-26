---
name: swap-migrate
description: >
  Moves a business's data from the old tool into the replacement without losing any, and proves it. Writes
  the field mapping, rehearses the import on a copy, then reconciles source against target by script:
  every column accounted for, row counts, unique keys, required fields filled, values unchanged, totals
  matching. Never prints a customer value. Use for "migrate our data", "move the records to the new
  system", "map the fields", "did everything come across", "reconcile the import". Lean track of the swap
  series. Do NOT use to plan the schema, use swap-architect. Do NOT use to test the app's screens, use
  swap-test. Do NOT use to run the final switch, use swap-cutover.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Migrate

## Purpose
Get every record across, in the right shape, and show the proof. A migration is done when the reconciliation script passes on a rehearsal and again on the final run, not when the import command exits.

Lean track only. Reads `swap/data-model.md`, `swap/architecture.md`; writes `swap/migration/mapping.csv`, `swap/migration/plan.md`, `swap/mapcheck.json`.

## Mode
Read `swap/mode.txt` (`lean` or `full`). Lean track only. In the full (sell) track there is no old data to move, so skip this skill. A customer importing from the original product is a feature of what you sell: scope it as one.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Old tool export | An official export the user makes from their own account (CSV or JSON) | Real columns, row counts |
| Schema | `swap/architecture.md`, `swap/data-model.md` | Target fields, required flags, constraints |
| Contract | `swap/audit.md` | Export rights, formats, any export fee or limit |
| Staging | A copy of the new system, never production | Where rehearsals run |

## Quick Start
1. Confirm `swap/migration/` and any export files are git-ignored. Fix that first.
2. Get the official export and read only its header and row count.
3. Write `swap/migration/mapping.csv` (columns below).
4. Rehearse the import into staging, export the staging data, and run the check.
5. Fix and repeat until it passes. Write `plan.md`.

## Workflow
1. **Mapping file.** One row per source column: `source_field, target_field, action, required, check`.
   - `action`: `map` (value must arrive unchanged), `derive` (transformed on purpose, only loss is checked), or `drop` (deliberately not migrated, with the reason in `plan.md`).
   - Every source column appears, including the ones you drop. Silence is how fields go missing.
   - `required=yes` for target fields the new system needs filled. `check=sum` for money and quantity columns.
2. **Rehearse on staging, never production.** Import the export. Export the result.
3. **Run the check:**
   `python3 -I <skill-folder>/scripts/mapcheck.py swap/migration/mapping.csv --source <old_export.csv> --target <staging_export.csv> --key <source key field> --json swap/mapcheck.json`
   Use `--allow-dropped-rows N` only when N rows are deliberately left behind (archived records), and list which in `plan.md`. **`--key` is required for a pass.** Without a usable unique key the script fails the run and writes `passed: false`, because equal counts do not prove the right data arrived. The report names rows by line number in your files, never by key or value.
4. **Read every FAIL.** Fix the mapping or the import, rerun. The script prints keys and counts, never values.
5. **Plan the final run.** Cutover day needs a fresh export (data changed since the rehearsal), a rerun of this check, and a freeze on edits to the old tool in between. Write the steps and timings in `plan.md`.
6. **Keep the old export** as the record of what existed at the switch, stored where the business keeps its records.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Row counts match, so it's fine" | Counts match while values are blanked or altered. The script checks per row by key. |
| "Skip the key, the IDs may change" | Without a key the script cannot match rows. Pick a stable identifier or create one in the mapping. |
| "Just drop the columns we don't recognise" | Unrecognised columns are the ones nobody remembers needing. List them and ask. |
| "Test it on production, it's quicker" | A bad import in production is a data incident. Rehearse on staging. |
| "Show a few rows so the user can see" | Rows are customer data. Show field names, counts and line numbers only; the user opens those lines in their own system. |

## Output Format
EXACT. `swap/migration/mapping.csv` header: `source_field,target_field,action,required,check`. `swap/migration/plan.md` headings in order: `## Source and counts`, `## Mapping decisions` (every `derive` and `drop` with its reason), `## Rehearsals` (date, result, fixes), `## Final run steps`, `## Records kept`. `swap/mapcheck.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
## Rehearsals
1. 23 of 28 checks pass: 39 of 40 rows arrived (one missing at source line 41), one phone lost (source line 5), one
   email changed (source line 11). Fixed the import mapping.
2. 28 of 28 pass, matched row by row on a key. mapcheck.json: passed true, key_checked true.
```

## Rules
- Only export data the user is entitled to take, through the vendor's own export or the user's own account. Never scrape around an export limit or access anyone else's data.
- Never write a customer value into `swap/` notes, logs or chat.
- Personal data stays within the business's own systems and the jurisdiction's rules; if special-category data is involved, say so and ask before continuing.

## Cross-Skill Routing
Rehearsal passes -> `swap-test` (if not yet run) or `swap-diff`. The final run happens inside `swap-cutover`, which reruns this check.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/mapcheck.json` has `"passed": true` and `"key_checked": true`
- [ ] Every source column in the export header appears in `mapping.csv`
- [ ] Each `drop` and `derive` has a reason in `plan.md`
- [ ] Source and target row counts are quoted, with any allowed drops explained
- [ ] `swap/migration/` and the export files are git-ignored (show the `git check-ignore` output)
- [ ] The rehearsal ran against staging, not production

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
