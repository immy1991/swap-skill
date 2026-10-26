---
name: swap-market
description: >
  Decides whether a software product is worth building your own version of to sell, before any building.
  Reads public reviews with a link on every quote, ranks what users complain about, checks the vendor's
  public terms and what the vendor owns (network, content, licences), and gives a clonability verdict and
  a positioning angle. Use for "should we build our own version of X and sell it", "what do users hate
  about X", "is this app worth cloning", "find the gap in the market", "research the competitor's
  reviews". Start of the full (sell) track of the swap series. Do NOT use to cut your own software bill,
  use swap-audit. Do NOT use to map the product's features, use swap-recon. Do NOT use to price and
  forecast the business, use swap-roi.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Market

## Purpose
Answer one question before money is spent: is there a real, evidenced gap in this product that a leaner or better version could fill, and is the product the kind that can legally and practically be rebuilt? The output is a verdict, a positioning angle and a link for every claim.

Full (sell) track, step 1. Writes `swap/mode.txt` with `full`, `swap/reviews.csv`, `swap/market.md`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| The target | The user's choice of product and why | What it is, who buys it, what they want to do differently |
| Public reviews | App stores, review sites, forums and posts anyone can read without logging in | Rating, text, URL, date, source |
| Vendor public pages | Pricing page, terms of service, help centre, status page | Price points, what is included, terms on competing or data use |
| User's own notes | Anything the user already collected | Start here; add, never overwrite |

## Quick Start
1. Write `full` to `swap/mode.txt`. Name the target product and the user's idea of the angle.
2. Collect public reviews into `swap/reviews.csv` (columns `source,url,rating,date,text`). Aim for at least 30 across 2 or more web hosts (the script counts a source by the link's host, not by the label you type); fewer is allowed but flagged.
3. Run `python3 -I <skill-folder>/scripts/reviews.py swap/reviews.csv --json swap/reviews.json` from the project root (<skill-folder> is this skill's folder). Read every quote.
4. Run the clonability questions below. Write `swap/market.md`.

## Workflow
1. **Collect reviews you can lawfully read.** Public pages only. Never log in as someone else, get past a paywall, or scrape against a site's terms. Copy the review text exactly and keep its URL. A review with no link is not evidence and the script drops it.
2. **Run the script and read the output against the raw reviews.** Themes come from keyword matches; open the quotes and decide if the theme is real. Themes marked THIN are leads, not findings.
3. **Clonability questions (answer each with evidence):**
   - Is the value the software, or what the vendor owns: a network of users, a content library, a marketplace, data nobody else has, a licence or regulatory approval? If the latter, the product cannot be cloned; stop.
   - Do the vendor's public terms bar building a competing product or using its materials? Quote the clause.
   - Is the product's core protected by something you cannot design around (patent claims you have seen cited, a standard you must license)? Note it for a lawyer.
   - How large is it: weeks, months or years of work? Be honest. Name what drives the size.
   - Can the user reach the buyers: is there an audience or channel they already have?
4. **Verdict:** CLONE (evidenced gap, buildable, no blocking clause), NARROW (clone only part of it: name the approved features under `## Approved subset`; `swap-scope` carries them forward with `--subset`), or DON'T (vendor-owned core, barring terms, or no evidenced gap). One sentence of reasoning each.
5. **Angle.** One sentence: who it is for and what it does differently, tied to the top evidenced themes. No claim about the market that has no link.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "I know what people say about this app" | Memory is not evidence. Every claim needs a review link the reader can open. |
| "A strong quote is worth paraphrasing" | The script prints verbatim text with its link. Paraphrase is how quotes get invented. |
| "Ten reviews is plenty" | Under 30 is flagged small. Say so; do not present leads as findings. |
| "It's a popular app, so clone it" | Popularity may come from the network or content, which cannot be cloned. Check that first. |
| "Terms of service are boilerplate" | A clause against competing builds ends the project. Read it. |

## Output Format
EXACT. `swap/market.md` headings in order: `## Target and mode`, `## Evidence` (the script's sample line and theme list, pasted), `## Clonability` (each question with evidence), `## Verdict` (CLONE, NARROW or DON'T), `## Approved subset` (NARROW only: the features to build, one per line), `## Angle`, `## Gaps` (every claim lacking a link, every unknown). `swap/reviews.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
## Verdict
NARROW. Clone the booking and reminders software; not the provider marketplace (vendor-owned network).

## Approved subset
Online booking page
Staff availability
Email reminders

## Angle
Flat pricing for solo practitioners. Evidence: 14 of 30 negative reviews cite pricing, across 3 web hosts, e.g.
"Overpriced for what a solo practitioner actually uses." (https://forum.example.test/r/011)

## Gaps
- 5 negative reviews matched no theme: read them for one the keywords missed.
```

## Rules
- Rebuild what the product does, never what the vendor owns: no copied code, assets, logos, trademarks, copy, content or private APIs.
- Public sources and the user's own account only. No fabricated reviews, quotes, ratings or numbers, ever.
- This is not legal advice. Anything legal in `## Clonability` is flagged for a lawyer before launch.

## Cross-Skill Routing
CLONE or NARROW -> `swap-recon` (for NARROW, `swap-scope` will take the approved subset). DON'T -> stop and say why; that is a good result. User only wants to cut their own software bill -> `swap-audit`.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/mode.txt` contains `full`
- [ ] `swap/reviews.json` exists; its `reviews_used` and `dropped_no_link` counts are quoted in `## Evidence`
- [ ] Every quote in `market.md` appears verbatim in `reviews.csv` with its URL
- [ ] Each clonability question has a quoted source or is listed under Gaps
- [ ] The verdict is exactly CLONE, NARROW or DON'T
- [ ] The angle cites at least one theme with at least 3 reviews from 2 web hosts, or says the evidence is thin

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
