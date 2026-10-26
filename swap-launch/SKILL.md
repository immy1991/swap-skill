---
name: swap-launch
description: >
  Writes what a product needs in order to be found and bought: a landing page built on the evidenced
  angle, a pricing page set from the unit economics, a store or web listing checked by script (character
  limits, the original's name anywhere, ranking claims, price words, wasted keywords), and draft legal
  pages. Never invents testimonials, numbers or logos. Use for "write the landing page", "set the
  pricing", "store listing", "launch copy for the product", "lint the app store listing". Full (sell)
  track of the swap series. Do NOT use for the brand name and identity, use swap-brand. Do NOT use to put
  the product live, use swap-deploy.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Launch

## Purpose
Produce launch copy and a listing that are honest, specific to the evidenced angle, free of the original's name, and mechanically checked against store rules.

Full (sell) track, step 12. Reads `swap/market.md`, `swap/brand.md`, `swap/sellmodel.json`; writes `swap/launch/landing.md`, `swap/launch/pricing.md`, `swap/launch/listing-input.json`, `swap/launch/legal-drafts.md`; the lint result is `swap/listing.json`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Angle and evidence | `swap/market.md`, `swap/reviews.json` | The gap, and quotes with links you may cite |
| Identity | `swap/brand.md` | Name, voice, avoid list |
| Economics | `swap/sellmodel.json`, under `assumptions` | `price_per_customer_month`, `cost_per_customer_month`: the price must cover the cost and leave the margin the model used |
| Competitor pricing | The vendor's public pricing page, supplied by the user | Anchors for a fair comparison |
| Features | `swap/features.csv` | What actually exists (`status=done`) |

## Quick Start
1. Take the angle and the top evidenced themes from `market.md`; take the name and voice from `brand.md`.
2. Write the landing page around one reader and one promise. Then pricing. Then the listing JSON.
3. Run `python3 -I <skill-folder>/scripts/listing.py swap/launch/listing-input.json --json swap/listing.json` from the project root (<skill-folder> is this skill's folder); fix every FAIL.
4. Draft the legal pages for a lawyer.

## Workflow
1. **One reader, one promise.** The headline says what the reader gets, in their words from the evidence. The next screen shows it working. Proof comes only from real things: a real feature that is `done`, a quote with its link that you have permission to use, a measured result you can show. No invented testimonials, customer counts, logos, ratings or statistics.
2. **Only describe what exists.** Every claim maps to a `done` row in `features.csv`. Planned features are labelled as planned or left out.
3. **Pricing.** Start from `sellmodel.json`: the price must cover the variable cost and leave the margin the model used. Compare with the vendor's public pricing in plain, current, sourced terms. State the plan limits clearly and the cancellation and refund terms. Do not hide what a plan lacks.
4. **Comparisons.** Do not use the original's name in the listing, keywords or ad copy. On a web page, a factual comparison naming a competitor is a legal question; default to describing the problem ("per-seat pricing that rises with your team") and ask a lawyer before naming.
5. **Listing.** Write `listing-input.json` with the store and the original name(s) under `original_names`. The script checks the limits it knows, the original's name (also with spaces or punctuation inserted), ranking claims, price words, "official", and wasted keywords. Fix FAILs; read WARNs; confirm limits against the store's current documentation, because they change.
6. **Draft legal pages** (terms, privacy, refunds, cookies if used) as drafts, listing every place a lawyer must decide something.
7. **Tracking and consent.** Decline non-essential cookies by default; state what is tracked.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "A few testimonials will help it convert" | Invented social proof is deception and in many places unlawful. Real ones only, with permission. |
| "Name the competitor, people search for it" | Using their trademark in a listing is a store-policy and legal risk. Describe the problem. |
| "Say it's the best, it's a launch" | Superlatives are rejected by stores and unprovable. Say what it does. |
| "Mention the planned features, it looks fuller" | Customers buy what exists. Label plans or omit them. |
| "The limits haven't changed" | They change. Run the script, then check the store's current rules. |

## Output Format
EXACT. `landing.md` headings in order: `## Headline and promise`, `## How it works`, `## Proof` (each item with its source), `## Pricing summary`, `## FAQ`, `## Call to action`. `pricing.md`: plan table, what each includes, limits, cancellation and refund, and a `## Margin check` line quoting `sellmodel.json`. `listing-input.json` in the script's schema; `swap/listing.json` is the lint result, unedited. `legal-drafts.md`: each page with `LAWYER TO DECIDE:` lines.

**Reference Output** (invented example, abridged):

```
## Headline and promise
One price however big your team gets.

## Proof
None yet: there are no customers. This section stays empty until there are real quotes with permission.

listing.py: PASS (apple; title 15 of 30, subtitle 21 of 30).
```

## Rules
- Original copy, original structure, original name. Never the vendor's words, screenshots, logos or trademarks.
- No fabricated testimonials, statistics, logos, awards, reviews or user counts.
- Nothing is published or submitted to a store without the user's explicit yes.

## Cross-Skill Routing
Before starting: `swap/sweep.json` must exist, say `"passed": true`, and be from a run after the last code change; if it is missing or stale, go to `swap-brand` (sweep phase) first. Listing lint passes and the sweep is CLEAN -> `swap-deploy`. Lint cannot pass because the product is genuinely too close to the original -> back to `swap-brand`.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/listing.json` has `"passed": true` and the script's output is pasted
- [ ] Every claim on the landing page maps to a `done` feature or a sourced fact (table of claim -> source)
- [ ] Every Proof item has a source the reader could verify, or the section says none yet
- [ ] The original's name does not appear in any launch file except `original_names` inside `listing-input.json`, which the lint needs (`grep -ri` excluding that one file; result quoted)
- [ ] The price covers `assumptions.cost_per_customer_month` in `sellmodel.json` (numbers quoted)
- [ ] `legal-drafts.md` is labelled as drafts and lists lawyer decisions

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
