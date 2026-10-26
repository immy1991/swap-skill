---
name: swap-recon
description: >
  Maps what one software tool does for one business so it can be rebuilt: screens, flows, features with
  how often each is used, integrations, and the data model inferred from the user's own account and
  exports. Marks what the vendor owns and cannot be rebuilt (networks, content, licences). Use for "map
  this tool", "what does this app actually do for us", "document the features we use", "recon the software
  we want to replace", "which features do we depend on". Step 2 of both tracks of the swap series. Do NOT
  use to pick which tool to replace, use swap-audit. Do NOT use to cut the list down and estimate effort,
  use swap-scope.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Recon

## Purpose
Produce an honest map of one tool as this business uses it: a feature list with real usage, the flows people follow, the integrations, and the data model. It is the only input the scope step trusts, so unknown beats guessed.

Step 2 of both tracks. Reads `swap/audit.md` (lean) or `swap/market.md` (full); writes `swap/recon.md`, `swap/features.csv`, `swap/data-model.md`.

## Mode
Read `swap/mode.txt`. If it is missing, ask which track (lean: replace software the business pays for; full: build a product to sell) and write the answer.
- **Lean:** the team uses the tool, so `usage` and `confirmed` come from them.
- **Full:** nobody here is the tool's user. `usage` comes from public evidence (help pages, pricing tiers, reviews, the user's own trial account) and may be `unknown`; `confirmed=yes` means you saw it yourself in a source the user may lawfully use. Also record the original's name, product names, domains and brand colours under `## Original identity`: `swap-brand` and its sweep need them. Data-model work uses only the user's own trial data and public documentation.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Audit (lean) or Market (full) | `swap/audit.md` in lean, `swap/market.md` in full | Which tool, who uses it, what the contract or public terms allow |
| The user's own account | Walkthrough with the user, their screenshots, their admin screens | Screens, flows, settings in real use |
| Data exports | CSV or JSON the user exports from the tool | Real field names, row counts, relationships. Treat as private; read, never copy values into notes |
| Public pages | Help centre, pricing page, public walkthroughs, store listing | What exists vs what the team uses |
| Integrations | The user's list of connected tools and automations | Dependencies that must survive the swap |

## Quick Start
1. Read `swap/audit.md` (lean) or `swap/market.md` (full). Confirm the single tool and the account you are allowed to look at.
2. Walk the tool with the user, screen by screen, and ask how often each thing is used.
3. Get one export of each data type. Read the headers and counts.
4. Write the three files. Mark every unknown.

## Workflow
1. **Terms first.** Re-read the contract clause on replacement and on data. If it bars building a substitute, stop and tell the user.
2. **List features as the user's team experiences them,** not as the vendor markets them. One row per feature in `swap/features.csv`:
   `feature, priority, usage, kind, effort_days, confirmed`.
   - `priority`: must / should / could, from the user (ask; do not assign by feel).
   - `usage`: daily / weekly / monthly / rarely / never / unknown.
   - `kind`: `feature`, `integration`, or one of `network`, `content`, `licence` for things the vendor owns (a marketplace, a content library, a regulated licence).
   - `effort_days`: leave blank. Scope fills it.
   - `confirmed`: lean: `yes` only when a real user at the business said how often they use it. Full: `yes` only when you saw the feature yourself in a public source or the user's own trial account (record which).
3. **Map flows.** For each of the top flows (the ones tied to daily or weekly features) write the steps from the user's point of view and where data is created, changed and read.
4. **Infer the data model from real exports:** entities, key fields, relationships, which fields are required, row counts. Names and counts only; no customer values in the notes.
5. **List integrations and who depends on them** (a webhook, a calendar sync, an accounting export).
6. **Size it honestly.** One paragraph: roughly how many features, how many entities, and whether this is days, weeks or months of work, with what drives the size.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "The vendor's feature list is the feature list" | It lists everything on offer. The team uses a fraction. Rebuild the fraction. |
| "I can guess usage from how the feature looks" | A guessed usage becomes a built feature nobody opens. Mark unknown and ask. |
| "The marketplace is a feature" | A network of other people's listings belongs to the vendor. Mark `network`, out of scope. |
| "Paste a sample row to show the data model" | Rows are customer data. Record field names and counts only. |

## Output Format
EXACT. `swap/recon.md` headings in order: `## Tool and terms`, `## Flows`, `## Integrations`, `## Size`, `## Unknowns`, then `## Original identity` (full mode only). `swap/data-model.md`: one section per entity with fields (name, type, required, example of format not value) and relationships. `swap/features.csv` with the exact header above.

**Reference Output** (invented example, abridged):

```
feature,priority,usage,kind,effort_days,confirmed
Online booking page,must,daily,feature,,yes
Group classes,should,unknown,feature,,no
Partner marketplace,must,daily,network,,yes

## Unknowns
- Group classes: usage unknown; front desk asked, no answer yet.
```

## Rules
- Rebuild what software does for this business, never what the vendor owns: no code, assets, logos, trademarks, copy, content or private APIs.
- Read only what the user is entitled to see: public pages and their own account. Never log in as anyone else, bypass a paywall, or work against the vendor's terms.
- Never write a credential, token or customer value into `swap/`.

## Cross-Skill Routing
Map complete -> `swap-scope`. A feature turns out to be vendor-owned -> mark it and keep going; do not try to rebuild it.

## Exit Checklist
Proof block: one line per item, PASS or FAIL plus evidence, then a "could not verify" list.
- [ ] `swap/features.csv` header is exactly `feature,priority,usage,kind,effort_days,confirmed`
- [ ] Every row's `usage` is one of the six allowed words
- [ ] Lean: every row marked `confirmed=yes` names a person in recon.md. Full: every one names the public source or trial-account screen
- [ ] Every vendor-owned item is `kind` network, content or licence
- [ ] `swap/data-model.md` lists every entity seen in the exports, with counts and no values
- [ ] `## Unknowns` lists every `usage=unknown` feature
- [ ] Full mode: `## Original identity` lists the name, domain(s) and at least one brand colour

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
