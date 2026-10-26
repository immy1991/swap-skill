---
name: swap-design
description: >
  Builds the replacement's design system as the business's own: colour roles, type scale, spacing and
  component specs written as tokens, with light and dark themes, checked for WCAG contrast by script.
  Starts from the business's own brand and assets, never the old vendor's look. Use for "design system for
  the replacement", "tokens for this app", "make the swap look like our company", "check the colours pass
  accessibility", "contrast check". Both tracks of the swap series. Do NOT use to rebuild the vendor's
  visual identity or copy it. Do NOT use to build the screens, use swap-build.
license: MIT
metadata:
  author: immy1991
  version: 1.0.0
---

# Swap Design

## Purpose
Give the replacement a coherent visual system that belongs to the business, passes contrast, and gives the build step exact values to use.

Step 5 or 7 depending on track. Reads `swap/architecture.md`, `swap/scope.md`; writes `swap/design/tokens.json`, `swap/design/contrast.json`, `swap/design/components.md`.

## Mode
Read `swap/mode.txt` (`lean` or `full`). In **lean**, start from the business's own brand. In **full**, start from `swap/brand.md` (palette, type, voice); if it does not exist yet, run `swap-brand`'s identity phase first, so the design is never based on the original's look.

## Context Routing Table
| Source | Where | What to extract |
|---|---|---|
| Brand | The business's logo, colours, fonts, website, style guide the user supplies | Primary colour, type, tone |
| Scope | `swap/scope.md`, `swap/features.csv` | Which screens and components are needed |
| Users | The user and the people who will use it | Device mix, accessibility needs, light or dark use |
| Existing system | Any design tokens the business already has | Reuse before inventing |

## Quick Start
1. Ask for the brand source. No brand? Use a neutral system and say so.
2. List the components the in-scope screens need (button, input, table, form, modal, date picker...).
3. Write `swap/design/tokens.json` with `themes.light` and `themes.dark`, each with `colors` and `pairs`.
4. Run `python3 -I <skill-folder>/scripts/contrast.py swap/design/tokens.json --json swap/design/contrast.json` from the project root (<skill-folder> is this skill's folder). Fix every FAIL and rerun.
5. Write `swap/design/components.md`.

## Workflow
1. **Start from the business, not the vendor.** The old tool's palette, logo, icons, fonts (if licensed) and wording are not used. If the business's brand happens to resemble the vendor's, change enough that no one would mistake the two.
2. **Define colour roles, not colour lists:** `text`, `muted`, `bg`, `surface`, `border`, `primary`, `on-primary`, `danger`, `on-danger`, `focus`. Each theme has its own values.
3. **List the pairs that actually appear** (text on bg, muted on surface, on-primary on primary...). Large text and UI parts may use a 3.0 minimum, stated per pair. Everything else is 4.5.
4. **Type and spacing:** one type scale (sizes, weights, line heights) with an open or properly licensed font; one spacing scale on a fixed base unit; radii and shadows as named tokens.
5. **Component specs:** for each component, the states it needs (default, hover, focus, disabled, error, loading, empty) and the tokens it uses. Focus must be visible.
6. **Run the contrast script and show the output.** A FAIL is fixed by changing the colour, not by lowering the minimum.

## Anti-Rationalization
| What Claude might think | Why it's wrong |
|---|---|
| "Match the old tool so users feel at home" | Familiar function, not their look. Copying a vendor's design invites a trademark or trade-dress claim. |
| "The brand grey is fine, skip the check" | Brand greys often fail on white. The script takes seconds. |
| "Dark mode later" | Retrofitting means redoing every pair. Define both themes now. |
| "Lower the minimum for this pair" | 4.5 is the normal-text AA line. Only large text and UI parts earn 3.0, per pair. |

## Output Format
EXACT. `tokens.json` shape: `{"themes": {"light": {"colors": {...}, "pairs": [[fg, bg, min?]]}, "dark": {...}}, "type": {...}, "space": {...}, "radius": {...}}`. `components.md`: one section per component with states and tokens. `contrast.json` is the script's output unedited.

**Reference Output** (invented example, abridged):

```
tokens.json: themes.light and themes.dark, each with colors and pairs.
contrast.py: 6 of 6 pairs pass (light: muted on bg 5.88:1, needs 4.5).

components.md
### Button
States: default, hover, focus (2px ring in primary), disabled, loading. Tokens: primary, on-primary, radius.md.
Font: an open-licence sans, licence recorded.
```

## Rules
- Original design: your own palette, icons, illustration and words. No vendor logos, trademarks, copy or proprietary assets.
- Fonts and icons must be open or properly licensed; record the licence in `components.md`.
- Never edit `contrast.json` by hand.

## Cross-Skill Routing
Contrast passes in every theme -> `swap-build`. No UI in the project (a pure back-end swap) -> skip this skill and say so.

## Exit Checklist
Proof block with evidence; then "could not verify".
- [ ] `swap/design/contrast.json` has `"passed": true`
- [ ] Both light and dark themes are present and each has at least 5 pairs
- [ ] Every component in `components.md` lists default, focus, disabled and error states
- [ ] No vendor name, logo or colour value taken from the vendor appears in the files
- [ ] Font and icon licences are recorded

## Self-Improvement
After each run, ask once: "Any feedback to capture for this skill?" Silence or no means nothing changes. If yes: draft the pattern, show it, append to `references/learnings.md` only after a yes; "update the skill" shows the exact edit, confirms, writes, bumps `metadata.version` and logs one line. Never promote a logged pattern into this file in the same session it was captured. After the first run, name the bundled files used and anything built from scratch that will be needed again, and offer to save it (gated the same way).
