---
name: swap-backend
description: >
  Builds the parts a product needs to be sold to other people: sign-up and login, one customer's data kept
  strictly apart from another's, subscription billing through a payment provider's hosted checkout (test
  mode first), transactional email, third-party integrations under their own terms, an admin view, backups
  and privacy basics. Use for "add accounts and payments", "make it multi-tenant", "set up billing", "add
  login", "what does it need to be sold". Full (sell) track of the swap series; not needed for lean swaps
  used inside one business. Do NOT use to plan the architecture, use swap-architect. Do NOT use to build
  the product's main screens, use swap-build. Do NOT use to test the finished product, use swap-test. Do
  NOT use to go live, use swap-deploy.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Backend

## Purpose
Turn a working product into one that strangers can safely sign up to and pay for, without one customer ever seeing another's data and without the product ever touching a card number.

Full (sell) track, step 9. Reads `swap/architecture.md`, `swap/sellmodel.json`; writes code in the product repository and `swap/backend.md`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Architecture | `swap/architecture.md` | Stack, schema, tenancy approach |
| Pricing inputs | `swap/sellmodel.json`, under `assumptions` | `price_per_customer_month`, `cost_per_customer_month`, `fixed_monthly`: the plans must match these |
| Features | `swap/features.csv` | Integrations in scope |
| Provider docs | The payment, email and auth providers' own documentation | Current API behaviour (read it; do not rely on memory) |
| The user | Which providers they have accounts with | What is available |

## Quick Start
1. Confirm mode is full and `swap-build` has the core flows `done`.
2. Add tenancy first, then auth, then billing, then email and integrations.
3. After each, write the isolation or webhook test and log the run in `swap/backend.md`.
4. Everything stays in test mode until the user says go live.

## Workflow
1. **Tenancy.** Every row that belongs to a customer carries a tenant id, enforced in the database (a constraint, and row-level security where the database supports it), not only in the queries. Write the test that logs in as tenant A and tries every endpoint with tenant B's ids. It must fail closed.
2. **Authentication.** Use the platform's maintained auth library or a hosted identity provider; do not write password hashing or session handling by hand. Sign-up, email verification, login, logout, password reset, session expiry. Offer two-factor for admin accounts.
3. **Billing.** Use the provider's hosted checkout and customer portal so card data never reaches your servers. Plans match `sellmodel.json`. Handle the webhook events that change access (payment succeeded, failed, subscription cancelled) and verify every webhook's signature. Make handlers safe to receive twice, and safe to receive out of order: store the provider's event time (or the subscription's version) with the state you applied and ignore any event older than that, so a late "payment failed" can never overwrite a newer "payment succeeded". Test with the provider's test mode and its published test cards.
4. **Entitlements.** Access follows the subscription state, with a grace period decided with the user. A failed payment never deletes data.
5. **Email.** Transactional only at this stage (verification, receipts, password reset) from a verified sending domain. Marketing email needs consent and its own plan.
6. **Integrations.** Use each third party's official API with your own keys under its developer terms. Never use the original product's private endpoints or credentials.
7. **Admin and support.** A view for the owner to find an account, see its plan and state, and export or delete its data on request.
8. **Privacy and records.** Data export and deletion per customer, a privacy policy and terms drafted for a lawyer's review, a list of every third party that sees customer data, and backups with a restore someone has tried.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Filter by tenant in the query layer, that's enough" | One missed query leaks data. Enforce in the database and test cross-tenant access. |
| "I'll store the card briefly to simplify" | Never. Hosted checkout is meant to keep card data off your servers, which removes most of the risk; your remaining card-security obligations depend on the provider and the integration, so confirm them with the provider or an adviser. |
| "Webhooks arrive once, in order" | They repeat and reorder. Verify signatures and make handlers idempotent. |
| "Hash passwords with a quick function" | Use the maintained auth library. Hand-rolled auth is the common breach. |
| "Go live with the test keys swapped in" | The user switches live mode, after the checks. Claude does not enter live credentials. |

## Output Format
EXACT. `swap/backend.md` headings in order: `## Tenancy` (approach, constraint, isolation test and result), `## Authentication`, `## Billing` (plans, events handled, test-mode runs), `## Entitlements`, `## Email`, `## Integrations` (each with the terms checked), `## Admin and privacy`, `## Open items for a lawyer`.

**Reference Output** (invented example, abridged):

```
## Tenancy
tenant_id on every table with a row-level policy. Test: a user from tenant A called 22 endpoints with tenant B's ids:
22 of 22 returned 404.

## Billing
Hosted checkout, test mode. Handled: checkout completed, payment failed, subscription deleted. A bad signature gets
400; a repeated event is applied once. Live mode: the owner's switch, not done.
```

## Rules
- Secrets in environment variables only; never in code, logs or `swap/`. Never enter or request a payment credential, live API key or card number.
- Test mode until the user explicitly switches live; that switch is theirs.
- Never use the original product's private APIs, tokens or data.
- Terms, privacy and refund texts are drafts for a lawyer, not final.

## Cross-Skill Routing
Isolation, auth and billing tests pass -> `swap-test` for the whole product, then `swap-diff`. Provider limits change the unit economics -> rerun `swap-roi` in sell mode.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] A cross-tenant access test exists, ran, and its output is in `backend.md`
- [ ] No card data, live key or secret appears in the repository (`git grep` result quoted)
- [ ] Webhook signature verification is tested with a bad signature (rejected), a repeated event (handled once) and two events delivered in reverse order (the newer state wins)
- [ ] A test-mode subscription was created, changed and cancelled; the run is logged
- [ ] Data export and delete exist for a customer and were run on test data
- [ ] `## Open items for a lawyer` lists terms, privacy policy and refund text as drafts

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
