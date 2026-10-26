---
name: swap-audit
description: >
  Finds which software subscriptions a business should replace with its own build. Reads the spend list,
  counts how much of each tool is actually used, ranks by money paid for features nobody touches, flags
  tools too regulated to own (payroll, payments, identity, tax), and finds each notice deadline so no term
  auto-renews unnoticed. Use for "what software are we overpaying for", "audit our subscriptions", "which
  tools could we replace", "we pay too much for X", "SaaS spend review", "stop renting software". Start of
  the lean track of the swap series. Do NOT use to study one app you have already chosen, use swap-recon.
  Do NOT use to price a build against a subscription, use swap-roi.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Audit

## Purpose
Turn a company's software spend into a ranked shortlist of subscriptions worth replacing, with the evidence for each and the date by which a cancellation must be given. Output is one tool to swap first, not a list of ten.

The swap series has two tracks, set by `swap/mode.txt` (`lean` or `full`). **Lean** replaces software your own business pays for, and this skill starts it: `audit -> recon -> scope -> roi (forecast) -> architect -> design -> build -> migrate -> test -> diff -> cutover -> roi (actuals)`. **Full** builds a product to sell and starts at `swap-market`. Every skill reads and writes the shared `swap/` folder in the project.

## Context Routing Table
Read before asking anything. Trust order: the user's own files, then connected tools, then your own knowledge (wording only).

| Source | Where | What to extract |
|---|---|---|
| Spend list | `swap/spend.csv` if it exists; otherwise a card statement, accounting export or invoice folder the user gives you | Tool, annual cost, renewal date, seats |
| Admin panels | Screenshots or exports the user pastes | Active users in the last 30 days, plan name |
| Contracts | Order forms or terms the user supplies | Renewal date, notice period, data-export rights |
| Prior work | `swap/audit.md` | What was already decided; extend, never overwrite |

State the currency (pass it as `--currency`). Never infer it.

## Quick Start
0. Write `lean` to `swap/mode.txt`. (Selling a clone of an app is the full track: start at `swap-market` instead.)
1. Name the company and confirm whose spend this is.
2. Build `swap/spend.csv` with the columns in `scripts/spend.py` (`tool, annual_cost` are required. `category` is needed before a tool can be offered at all: a tool with none is NEEDS-CATEGORY, because the regulated-tool rule only works on a category you state. `pricing, seats, active_users, features_used, features_total, renewal_date, notice_days` make the answer sharper). Pull what the files give you; ask only for the gaps, in one batched message.
3. Run `python3 -I <skill-folder>/scripts/spend.py swap/spend.csv --json swap/audit.json` from the project root (<skill-folder> is this skill's folder). Print the table.
4. For each CANDIDATE and LOOK row, ask the three questions below and record the answers.
5. Pick one tool to swap first. Write `swap/audit.md`.

## Workflow
1. **Feature use comes from people, not from the vendor's website.** `features_used` is the count of features someone at the company really uses this month; `features_total` is what the plan offers. Ask the people who use the tool. A tool with no count is NO-DATA and stays out of the shortlist.
2. **Run the script before forming a view.** Its thresholds are flags (`--min-cost`, `--cand-util`, `--look-util`). Changing one is allowed; say which and why.
3. **Ask the three questions for every CANDIDATE and LOOK row:** who uses it and for what; what stops working if it disappears next week; can all the company's data be exported, in what format?
4. **Read the contract for each one you keep on the list.** Notice period, renewal date, export rights, and any clause that bars building a replacement. A bar means stop on that tool and say so.
5. **Choose the first swap.** Prefer: high unused value, a clean data export, few integrations, a small group of users. Say why it beat the others.
6. **Hand over.** Name the tool, the cancel-by date, and the next skill.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "It costs a lot, so it's a candidate" | A costly tool the team fully uses is a KEEP. The script ranks by unused share, not price. |
| "The pricing page shows the feature count" | That is the vendor's count of what exists, not what this team uses. Ask them. |
| "Payroll is the biggest line, include it" | REGULATED categories are never offered: owning them adds legal liability. |
| "Give them the top five to swap" | Five parallel swaps stall. One tool, finished, then the next. |
| "Renewal is months away, skip the dates" | Notice windows are often 30 to 90 days. A missed one costs a full extra term. |

## Output Format
EXACT. Write `swap/audit.md` with these headings in this order:
1. `## Company and currency`
2. `## Spend table` (the script's table, pasted)
3. `## Shortlist` (each tool: verdict, the three answers, contract findings, data-export finding)
4. `## First swap` (tool, why it won, cancel-by date from the script)
5. `## Not offered` (REGULATED and NO-DATA tools, each with its reason)
6. `## Gaps` (every number that is an estimate or unknown)

Do not invent a feature count, user count or date. Unknown goes in Gaps.

**Reference Output** (invented example, abridged):

```
## First swap
Bookly Pro: 14,400 a year, uses 4 of 22 features, 5 of 12 seats active. Cancel-by 2027-01-14 (renews 2027-03-15, 60 days' notice).
Why it won: the most unused value (11,782), a CSV export exists, two integrations.

## Not offered
- Paylane Payroll: REGULATED (payroll).
- CloudNotes: NO-DATA until someone counts the features used.

## Gaps
- Active users for FormForge: unknown.
```

## Rules
- Rebuild what software does for this business, never what the vendor owns. No copied code, assets, logos, trademarks, copy or private APIs.
- Use only the user's own account and data, and public pages. Never log in as someone else or get past an access control.
- Check the vendor's terms before recommending a replacement; a clause against it ends the swap for that tool.
- Never print or store a credential. Do not paste customer data into this folder.

## Cross-Skill Routing
First swap chosen -> run `swap-recon` on that one tool. Nothing worth swapping -> say so and stop; that is a result.

## Exit Checklist
Report as a proof block: one line per item, PASS or FAIL plus the evidence, then a "could not verify" list.
- [ ] `swap/audit.json` exists and its `total_annual_spend` equals the sum of the CSV's `annual_cost` column
- [ ] Every shortlisted tool has feature counts from a named person
- [ ] Exactly one tool is named under `## First swap`
- [ ] Cancel-by date is copied from the script, or Gaps says it is unknown
- [ ] No REGULATED tool appears in the shortlist
- [ ] Currency is stated
- [ ] `swap/mode.txt` contains `lean`

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: a pattern is drafted, shown, and appended to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. Run after the first run: name the bundled files used and anything built from scratch that the job will need again, and offer to save it (gated the same way).
