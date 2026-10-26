# Swap

Sixteen Claude skills in two tracks that work from the same `swap/` folder:

- **Lean: stop renting software.** Find the subscriptions worth replacing, build only the part your team uses,
  move your data across and prove nothing was lost, switch over with a way back, and cancel the old tool
  before its notice deadline.
- **Full: clone an app and sell it.** Check the market with real, linked reviews, rebuild the whole product
  to parity, give it a name and look of its own, add accounts and billing, write the launch copy, and put it
  live behind a go or no-go gate.

You choose the track once, in `swap/mode.txt` (`lean` or `full`), and every skill adapts.

**It rebuilds what software does, never what the vendor owns.** No copied code, assets, logos, trademarks,
copy or private APIs, and whatever the vendor owns (a marketplace, a content library, a licence) is left
out. The fine print is below and the skills follow it.

Free, MIT. Installing the skills and running the eleven helper scripts needs no signup and no API key; the scripts use
only the Python standard library (3.9 or newer) and never touch the network. Doing a real swap or launch does involve
your own accounts (the tool you are replacing, hosting, a payment provider, a domain), which the skills never create
or log in to for you.

## Install

As a plugin, in Claude Code:

```
/plugin marketplace add immy1991/swap-skill
/plugin install swap-skill@swap-skill
```

Or copy the folders for plain `/swap-audit` style commands:

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/immy1991/swap-skill.git
cp -r swap-skill/swap-* ~/.claude/skills/
```

Project-local instead: copy the same folders into your repo's `.claude/skills/`.

## The sixteen

| command | track | what it does |
| --- | --- | --- |
| `/swap-audit` | lean | Ranks your subscriptions by money paid for features nobody uses. Flags tools too regulated to own. Finds each cancel-by date. |
| `/swap-market` | full | Reads public reviews (a link on every quote), ranks what users hate, checks what the vendor owns and what its terms allow, and gives a clonability verdict. |
| `/swap-recon` | both | Maps what the tool does: features with usage, flows, integrations, data model. In full mode it also records what must not be copied. |
| `/swap-scope` | both | Lean: cut to what is used, hold back anything undecided. Full: everything the vendor does not own, to parity. Adds up the effort. |
| `/swap-roi` | both | Does it pay back? Lean: payback and the most you can spend. Full: unit economics and cash needed. Run as a forecast, then with real numbers later. |
| `/swap-brand` | full | A name, look and voice of your own, the trademark and domain checks to run, and a sweep that looks for the original's name, domain and colours in your code's text files (a bounded check; images and other colour forms need a look by hand). |
| `/swap-architect` | both | Checks whether open-source or low-code already does the job, then plans stack, schema and build order. |
| `/swap-design` | both | A design system that is yours, light and dark, checked for contrast. |
| `/swap-build` | both | Builds feature by feature. A feature is done only when a logged run proves it. |
| `/swap-backend` | full | Accounts, one customer's data kept apart from another's, subscription billing through a hosted checkout, email, admin, privacy basics. |
| `/swap-migrate` | lean | Maps fields, rehearses the move, and reconciles old against new row by row. |
| `/swap-test` | both | Walks every flow, tries to break every business rule, logs bugs by severity. |
| `/swap-diff` | both | Scores the build against the scope. A partial must-have blocks shipping at any score. |
| `/swap-launch` | full | Landing page, pricing and store listing, with a lint for store rules and the original's name. No invented testimonials. |
| `/swap-cutover` | lean | Go or no-go gate, parallel run, final data move, rollback, then cancellation before the notice deadline. |
| `/swap-deploy` | full | Production setup, domain, live billing switch by the owner, and a go or no-go gate. |

## How to use it

Run them in order. Each reads what the last wrote.

```
lean:  audit -> recon -> scope -> roi -> architect -> design -> build -> migrate -> test -> diff -> cutover -> roi
full:  market -> recon -> scope -> roi -> brand -> architect -> design -> build -> backend -> test -> diff -> launch -> deploy -> roi
```

`roi` appears twice on purpose. The first run is the gate: if it does not pay back on paper, the chain
stops there, and that counts as a good result. The second run, about 90 days after switching or launching,
uses real numbers.

Start with one tool. Swapping five at once is how these projects stall.

## See it work

`example/run_example.py` runs the helper scripts across both tracks on an invented company and an invented
product, with real files passed from step to step. It includes the failures on purpose: a migration that
loses data, a grey that fails contrast, an open S2 bug, a sweep that finds the original's name in the
code, a listing that breaks store rules, and a forecast that says keep paying.

```bash
python3 example/run_example.py
```

It exits 0 only if every gate stopped what it should stop and passed what it should pass. It does not build
an app: build, backend and test are represented by the files those steps would write. The reviews in the full
track are invented for the demonstration and use a reserved example domain.

## The scripts

All standard-library Python. None touch the network.

```bash
python3 swap-audit/scripts/spend.py swap/spend.csv                 # rank subscriptions, flag regulated tools, find cancel-by dates
python3 swap-market/scripts/reviews.py swap/reviews.csv            # ranked complaints, a link on every verbatim quote
python3 swap-scope/scripts/scope.py swap/features.csv --mode full  # scope rules, effort with contingency, writes the master list
python3 swap-roi/scripts/roi.py --subscription 14400 ...           # lean: payback, overrun case, build budget ceiling
python3 swap-roi/scripts/sellmodel.py --price 29 ...               # full: unit economics, stress case, lowest cash point
python3 swap-brand/scripts/sweep.py product --avoid "Original"     # anything of the original left in your code
python3 swap-design/scripts/contrast.py swap/design/tokens.json    # WCAG contrast across light and dark themes
python3 swap-migrate/scripts/mapcheck.py mapping.csv --source a.csv --target b.csv --key id
python3 swap-diff/scripts/parity.py swap/features.csv              # weighted parity score and ship verdict
python3 swap-launch/scripts/listing.py listing-input.json          # store-rule lint for your listing
python3 swap-cutover/scripts/preflight.py --dir swap               # lean go or no-go, last day to cancel
python3 swap-deploy/scripts/preflight.py --mode full --dir swap    # full go or no-go (the same file as the cutover one)
```

**`spend.py`** never offers a tool as a swap if you classified it as payroll, payments, identity, tax, banking or
compliance. A tool with no category is NEEDS-CATEGORY and is never offered either: the script does not guess a
category from a name. A tool without a feature count is NO-DATA, not a guess.

**`reviews.py`** drops any review without a link, prints only verbatim text with its link, and marks thin
themes and small samples.

**`scope.py`** rules out anything the vendor owns, and in lean mode anything nobody uses; it holds anything
with unknown usage and never fills in an estimate you did not make.

**`roi.py` and `sellmodel.py`** take every number as a flag, warn when your own time is priced at zero, and
show a stress case beside the base case. `sellmodel.py` treats churn and acquisition as your assumptions.

**`sweep.py`** finds the original's name, domain and colours in your code, including inside identifiers and
split by spaces or separators, and lists every file it could not read.

**`mapcheck.py`** is written so that it does not print values from your data: its report holds counts, line numbers and
whether totals agree, not field values, keys or amounts, and it never prints your export's column names (a file
without a header row would expose its first line). Check the output yourself before sharing it.

**`parity.py`** does not count features you cut on purpose against the score, and lists extras separately.

**`listing.py`** checks the limits it knows, the original's name, ranking claims, price words and wasted
keywords. Store rules change, so confirm against the store's current documentation.

**`preflight.py`** will not say GO unless the evidence files agree with each other and with themselves, and the parity
score was computed from the features list that is there now. It cannot know whether the other evidence (tests,
sweep, listing, forecast) is current: re-run those right before the gate.

```bash
bash tests/run-all.sh
```

## Status

Version 1.0.0. The scripts have unit tests, the whole pack has an end-to-end example, and `bash tests/run-all.sh`
runs them. The pack was also reviewed by an independent AI auditor over several rounds, and each round found real
defects that were then fixed; no round graded it fully clean, and the last round's fixes were checked by tests, not by
a further independent review. The evals in each skill are synthetic. Treat it as a careful early release: read what the
scripts do before relying on a gate, and expect to find rough edges. The gates reject stubs and self-contradicting
evidence; they cannot tell real evidence from a consistent fake.

## Fine print

**It rebuilds functionality, not property.** It studies what a product does and writes everything fresh.
It never copies the vendor's code, proprietary assets, logos, trademarks, copy or private APIs, and it
leaves out whatever the vendor owns: a marketplace, a content library, a licence, a network of users.

**It only reads what you are allowed to read.** Public pages, your own account and your own exports. It never
logs in as someone else, gets past a paywall or access control, or scrapes against a site's terms. If the
terms bar building a replacement or taking your data out, the skills say so and stop.

**Selling a clone means rebranding it, properly.** The full track gives the product its own name, look and
words, and will not launch until a sweep of the code is clean. A name that could be confused with the
original, or listing copy that uses its trademark, is a legal risk the skills refuse to create. They cannot
check that a name is free: you run the trademark and domain searches, and a lawyer decides what they mean.

**It does not cancel, publish, deploy or charge anyone for you.** The cutover drafts the cancellation and
shows the deadline. The deploy gives you DNS records and waits for you to switch billing live and enter live
keys yourself. Nothing goes live without your yes.

**Some software is not worth owning.** Payroll, payments, identity, tax, banking and compliance tools are
never offered as swaps: owning them adds legal liability. Your product never touches a card number; it uses
a payment provider's hosted checkout.

**Numbers come from you.** The skills do not look up prices or invent feature counts, usage, reviews,
testimonials, user counts or estimates. Unknowns are listed, and the scripts mark an estimate incomplete
rather than fill the gap. Acquisition and churn in a sell forecast are guesses until customers exist.

**No guarantee of savings or sales.** Results depend on the product, your team and what you can maintain.
The forecast gives a payback figure with a stress case beside it, and sometimes the answer is to keep
paying, or not to build.

**This is not legal advice.** Read the terms of anything you used, and talk to a lawyer before you launch
anything you will sell.

## Files

```
swap-audit/      SKILL.md, scripts/spend.py
swap-market/     SKILL.md, scripts/reviews.py
swap-recon/      SKILL.md
swap-scope/      SKILL.md, scripts/scope.py
swap-roi/        SKILL.md, scripts/roi.py, scripts/sellmodel.py
swap-brand/      SKILL.md, scripts/sweep.py
swap-architect/  SKILL.md
swap-design/     SKILL.md, scripts/contrast.py
swap-build/      SKILL.md
swap-backend/    SKILL.md
swap-migrate/    SKILL.md, scripts/mapcheck.py
swap-test/       SKILL.md
swap-diff/       SKILL.md, scripts/parity.py
swap-launch/     SKILL.md, scripts/listing.py
swap-cutover/    SKILL.md, scripts/preflight.py
swap-deploy/     SKILL.md, scripts/preflight.py
example/         run_example.py
tests/           run-all.sh, check.py
```

Each skill folder also holds its `evals/evals.json`, and each script has its unit tests beside it.
