---
name: swap-deploy
description: >
  Puts a product you will sell live on its own domain, behind a go or no-go gate. Prepares the production
  environment, domain and DNS records, certificates, live billing switch, monitoring, backups and a
  written rollback, then runs the preflight script: parity shippable, no open S1 or S2 bug, the sell
  forecast still holds, the brand sweep clean, the listing lint passed. The owner flips the switches;
  nothing goes live without their yes. Use for "put it live", "deploy the product", "set up the domain",
  "are we ready to launch", "go-live checklist". Full (sell) track of the swap series. Do NOT use to
  switch your own business off an old tool, use swap-cutover. Do NOT use to test the product, use
  swap-test. Do NOT use to write the launch copy, use swap-launch.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Deploy

## Purpose
Take the finished, branded, tested product live safely: production set up from written steps, a gate that checks the evidence, and a way back.

Full (sell) track, step 13. Reads every earlier output in `swap/`; writes `swap/deploy.md` and `swap/preflight.json`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Gate inputs | `swap/parity.json`, `swap/bugs.csv`, `swap/sellmodel.json`, `swap/sweep.json`, `swap/listing.json` | What the script checks |
| Architecture and backend | `swap/architecture.md`, `swap/backend.md` | Hosting, services, webhooks, test-mode state |
| Brand | `swap/brand.md` | The chosen name and domain |
| The user | Registrar, hosting and payment accounts they control | What they will do themselves |

## Quick Start
1. Draft `swap/deploy.md` with the exact lines `Rollback: <one sentence>` and `Domain: <your domain>`. If the sell forecast was MARGINAL, add `Marginal approved by: <name> on <date>`: the gate refuses without it.
2. Run `python3 -I <skill-folder>/scripts/preflight.py --mode full --dir swap --json swap/preflight.json` from the project root (<skill-folder> is this skill's folder).
3. NO-GO: fix what it names and rerun. GO: walk the owner through the production steps, one at a time.
4. After launch, watch day 1, 7 and 30, and run `swap-roi` in actuals mode after 90 days.

## Workflow
1. **Gate by script.** It first checks `swap/mode.txt` says `full` and that each artifact has the fields its script writes (a hand-typed stub fails). It then checks parity is shippable, no S1 or S2 bug is unfixed, the sell forecast is not DON'T SELL, the brand sweep is clean and fully scanned (or its unscanned files accepted), the listing passed lint, and a rollback and domain are written down. Do not proceed on NO-GO and do not argue with it in prose; fix the input.
2. **Production environment.** Separate from staging; secrets set as environment variables by the owner; production database created empty with migrations applied; no test data; error and uptime monitoring on; backups scheduled and one restore tried.
3. **Domain and certificate.** Give the exact DNS records and where to enter them. The owner applies them at their registrar; Claude does not change DNS. Confirm HTTPS works and `www` and the bare domain both resolve.
4. **Billing live mode.** The owner switches the payment provider to live mode and enters live keys themselves. Claude never handles live keys. Make one real purchase with a refund to confirm the webhook path, with the owner's explicit yes.
5. **Email.** Sending domain verified (SPF, DKIM) and a test message received.
6. **Listing and legal pages.** Published only by the owner, after the legal drafts have had their review.
7. **Rollback.** Write the exact steps to take the product down or return to the previous release, who decides, and what happens to customers' data and payments in either case.
8. **Launch watch.** Check errors, sign-ups, payments and support at the end of day 1, day 7 and day 30 and log them in `deploy.md`.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Tests passed, deploy" | The gate also covers the brand sweep, the listing and the economics. Run it. |
| "I'll put the live key in so it works" | Live credentials are the owner's to enter. Claude never handles them. |
| "DNS is quick, I'll change it" | DNS changes take a product down if wrong, and belong to the owner. Give the records. |
| "Skip the restore test, backups run nightly" | An untested backup is a hope. Restore once before launch. |
| "NO-GO is only the listing, launch anyway" | A failed listing is a rejected launch or a policy violation. Fix it first. |

## Output Format
EXACT. `swap/deploy.md` headings in order: `## Gate` (preflight output pasted), `## Production setup` (each step with who did it and when), `## DNS and certificate`, `## Billing live check`, `## Rollback`, `## Launch watch` (day 1, 7, 30). It contains the exact lines `Rollback: <summary>` and `Domain: <domain>`. `swap/preflight.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
Rollback: redeploy the previous release and pause new sign-ups
Domain: skyline.example.test

## Gate
GO: 7 of 7 checks pass (run on launch day).
```

## Rules
- Nothing goes live, is published, changes DNS, switches billing live, or touches production data without the owner's explicit yes for that action.
- Never print, request or store a live credential.
- Use only accounts the owner controls.
- Never delete production data or backups.

## Cross-Skill Routing
GO and launched -> `swap-roi` (actuals) after 90 days. NO-GO from parity or bugs -> `swap-build` or `swap-test`; from the sweep -> `swap-brand`; from the listing -> `swap-launch`; from economics -> `swap-roi`.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/preflight.json` has `"go": true` and `"mode": "full"`, from a run made on launch day
- [ ] `deploy.md` contains non-empty `Rollback:` and `Domain:` lines
- [ ] A backup restore was tried and the result is logged
- [ ] HTTPS and both hostnames were checked and the results quoted
- [ ] The live-mode switch and the first real purchase are recorded as done by the owner
- [ ] No live key or secret appears in the repository (`git grep` result quoted)

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
