---
name: swap-brand
description: >
  Gives a product you will sell its own identity, and scans the code for traces of the original. Two
  phases: identity early (name candidates with the trademark and domain checks to run, palette, voice,
  logo brief) and a sweep before launch that searches the code's text files for the original's name,
  domain and colours, including inside identifiers, and blocks deploy until it finds none. The sweep is a
  bounded token scan, not proof that nothing of the original remains: images, fonts, hsl() and named
  colours need a look by hand. Use for "name this product", "rebrand the clone", "check for leftovers of
  the original", "brand sweep", "is it different enough". Full (sell) track of the swap series. Do NOT use
  to build the design tokens, use swap-design. Do NOT use to write the landing page or store listing, use
  swap-launch.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Brand

## Purpose
Make the product plainly its own: a new name, look and voice decided early, and a mechanical sweep before launch that looks for the original's name, domain and colours in the code's text files. It is a bounded check, not proof: anything it cannot read, and anything it does not look for, still needs a person.

Full (sell) track, steps 5 (identity) and 12 (sweep). Reads `swap/market.md`, `swap/recon.md`; writes `swap/brand.md`, `swap/sweep.json`.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Market | `swap/market.md` | Angle, audience, the evidenced gap |
| Recon | `swap/recon.md` | The original's name, domains, brand colours (what to avoid) |
| The user | Their preferences, existing brand, domains they own | Constraints and taste |
| The code | The product repository | What the sweep scans |

## Quick Start
Identity phase: 1) list what to avoid from recon; 2) propose 5 name candidates tied to the angle; 3) give the checks to run for each; 4) set palette, voice and logo brief; 5) write `swap/brand.md`.
Sweep phase: run `python3 -I <skill-folder>/scripts/sweep.py <repo> --avoid "<original name>" --domain <original domain> --color "<original colour>" --exclude swap --json swap/sweep.json` from the project root (<skill-folder> is this skill's folder), fix every hit, rerun until CLEAN.

## Workflow
1. **Avoid list first.** From recon: the original's name and any product names, its domains, its brand colours, its distinctive taglines. Write them into `brand.md` under `## Avoid`; the sweep does not read that file, so pass each item to it explicitly as `--avoid`, `--domain` and `--color` flags.
2. **Name candidates (5).** Each: the name, the idea behind it, and why a customer would not mistake it for the original. No name that contains, abbreviates or sounds like the original's. No "X for Y" built on the original's name.
3. **Checks the user runs before committing** (Claude cannot verify availability): a trademark search in the user's market (national register and the international one), a domain and social-handle check, an app-store name search, and a plain web search for the name plus the category. Record the date and result of each. A conflict removes the candidate.
4. **Identity.** A palette clearly different from the original's (different hue family, not a tint of it), a type pairing from open or licensed fonts, a voice in 5 rules with a do and a don't each, and a logo brief the user or a designer executes. Do not describe a logo that imitates the original's shape or concept.
5. **The sweep (before launch, and again after the last code change).** Run it with the avoid list. It finds names inside identifiers (`OriginalAppEmbed`, `original_app`), domains, colour values in hex and rgb, and file or folder names. Fix by replacing, not by hiding. Use `--allow` only for harmless longer words and list each use in `brand.md`. The sweep prints the matched text, file and line, never the rest of the line.
6. **Beyond the code.** The sweep reads text files only. Images, fonts, archives, files over 2 MB and unreadable files are listed as not scanned, and the run is NOT CLEAN while any exist. Check each by hand (screenshots, sample data, metadata, email templates, alt text), then rerun with `--accept-skipped`, which records in `sweep.json` that you did. `--accept-skipped` never hides a hit.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "It's a clean-room build, no need to rebrand" | Clean-room covers the code. A name or look that confuses customers is a separate problem. |
| "Close enough to the original helps people find us" | Confusing similarity is the trademark risk. Distinct on purpose. |
| "The sweep found only a comment, ignore it" | A comment naming the original ships in the bundle. Remove it. |
| "I checked the name is free" | Only a register search by the user shows that. Record who ran it and when. |
| "Skip images and screenshots" | The sweep cannot read them. Check them by eye and say you did. |

## Output Format
EXACT. `swap/brand.md` headings in order: `## Avoid`, `## Name candidates` (each with idea and checks run, with dates and results), `## Chosen name`, `## Palette and type`, `## Voice`, `## Logo brief`, `## Sweep log` (each run: command, hits, fixes). `swap/sweep.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
## Chosen name
Skyline. Trademark search (UK, EU, US): not yet run. Domain and store-name search: not yet run.

## Sweep log
Run 1: 7 hits (name x4, domain x1, colour x1, path x1). Replaced all.
Run 2: CLEAN, 4 files scanned, 0 not scanned.
```

## Rules
- Original name, palette, logo, words. Never the original's logo, trademarks, copy or assets, in any form.
- Do not claim a name is available or registrable; that is the user's check and a lawyer's call.
- Never edit `sweep.json` by hand.

## Cross-Skill Routing
Identity chosen -> `swap-architect` then `swap-design` (which takes the palette from here). Sweep CLEAN -> `swap-launch`. Sweep never passes because of a vendor-owned asset in the product -> remove the asset; do not allow-list it.

## Exit Checklist
Proof block with evidence; then "could not verify".
Identity phase (before there is code):
- [ ] `## Avoid` lists the original's name, its domain(s) and at least one brand colour
- [ ] Every name candidate has the four checks recorded with a date, or says "not yet run"
- [ ] Palette, voice and logo brief are written and differ from the original's

Sweep phase (before launch, and again after the last code change):
- [ ] `swap/sweep.json` has `"passed": true`, from a run after the last code change
- [ ] The sweep command used `--exclude swap` (or scanned a tree without the notes); every not-scanned file was checked by hand and `skipped_accepted` is true, or the list is empty
- [ ] Every `--allow` use is listed in the sweep log
- [ ] Screenshots, copy and metadata were checked by hand and the user was told the sweep cannot read them

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
