#!/usr/bin/env python3
"""Payback maths for replacing a subscription with your own build.

Standard library only. Never touches the network. Every input is a flag, so every
number in the answer can be traced to something you typed.

Usage:
  roi.py --subscription 12000 --build-days 20 --day-rate 600 --run-cost 600 \
         --maintenance-hours-month 3 --hourly-rate 80 [options]

Required
  --subscription            what the current tool costs per year
  --run-cost                what the new build costs per year to host and run (0 is allowed, but you must say it)
  --build-days and --day-rate   build labour,  or  --build-cost for a single figure
Options
  --migration-cost 0        one-off data move
  --maintenance-hours-month 0   your time keeping it alive; needs --hourly-rate
  --price-growth 0          yearly rise in the subscription, as a fraction (0.08 = 8%)
  --overlap-months 1        months you pay the old tool AND run the new one
  --overrun 1.5             build and migration cost multiplier in the stress case
  --years 3                 horizon
  --payback-limit 18        months; the pass line for the verdict
  --json out.json

Model
  Month 0: pay the build and migration. Months 1..overlap: pay both tools, no saving.
  After the overlap: monthly saving = old monthly price - own monthly cost.
  The old price rises by --price-growth at each 12-month boundary. Own costs stay flat.
  Payback = first month the running total is back at zero or better.

Verdict
  BUILD       payback inside the limit even in the overrun case, and positive over the horizon
  MARGINAL    inside the limit in the base case only, or pays back inside the horizon but not the limit
  KEEP SAAS   does not pay back inside the horizon in the base case

Exit codes: 0 BUILD or MARGINAL, 1 KEEP SAAS, 2 bad input.
"""
import argparse
import json
import os
import math
import sys
import tempfile


class InputError(Exception):
    pass


def check_finite(obj, where="result"):
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        raise InputError("the inputs are so large that %s overflowed; check the units" % where)
    if isinstance(obj, dict):
        for k, v in obj.items():
            check_finite(v, k)
    elif isinstance(obj, list):
        for v in obj:
            check_finite(v, where)


def finite_nonneg(name, v):
    if v is None:
        return None
    if not isinstance(v, (int, float)) or isinstance(v, bool) or math.isnan(v) or math.isinf(v) or v < 0:
        raise InputError("--%s must be a finite number >= 0" % name)
    return float(v)


def model(p, build_total):
    """Return (payback_month or None, net_at_horizon, yearly rows, ceiling)."""
    months = int(p["years"] * 12)
    own_m = p["own_annual"] / 12.0
    cum = -build_total
    payback = None
    yearly, y_sub, y_own, savings = [], 0.0, 0.0, []
    for m in range(1, months + 1):
        sub_m = p["subscription"] * (1 + p["price_growth"]) ** ((m - 1) // 12) / 12.0
        if m <= p["overlap_months"]:
            saving = -own_m
            y_sub += 0.0
        else:
            saving = sub_m - own_m
            y_sub += sub_m
        y_own += own_m
        savings.append(saving)
        cum += saving
        if payback is None and cum >= 0:
            payback = m
        if m % 12 == 0:
            yearly.append({"year": m // 12, "old_tool_avoided": round(y_sub, 2), "own_cost": round(y_own, 2),
                           "net_saving": round(y_sub - y_own, 2), "cumulative_after_build": round(cum, 2)})
            y_sub = y_own = 0.0
    return payback, cum, yearly, savings


def run(a):
    try:
        return _run(a)
    except OverflowError:
        raise InputError("the inputs are so large that the arithmetic overflowed; check the units")


def _run(a):
    sub = finite_nonneg("subscription", a["subscription"])
    if not sub or sub <= 0:
        raise InputError("--subscription must be greater than 0: there is nothing to replace")
    run_cost = finite_nonneg("run-cost", a["run_cost"])
    if run_cost is None:
        raise InputError("--run-cost is required (say 0 if it really costs nothing to run)")
    if a["build_cost"] is not None:
        if a["build_days"] is not None or a["day_rate"] is not None:
            raise InputError("give --build-cost OR --build-days with --day-rate, not both")
        build = finite_nonneg("build-cost", a["build_cost"])
    else:
        if a["build_days"] is None or a["day_rate"] is None:
            raise InputError("give --build-cost, or both --build-days and --day-rate")
        build = finite_nonneg("build-days", a["build_days"]) * finite_nonneg("day-rate", a["day_rate"])
    mig = finite_nonneg("migration-cost", a["migration_cost"])
    mh = finite_nonneg("maintenance-hours-month", a["maintenance_hours_month"])
    hr = finite_nonneg("hourly-rate", a["hourly_rate"])
    if mh > 0 and (hr is None or hr == 0):
        raise InputError("--maintenance-hours-month needs a non-zero --hourly-rate: your time is a cost")
    growth = finite_nonneg("price-growth", a["price_growth"])
    if growth > 1.0:
        raise InputError("--price-growth is a fraction (0.08 means 8 percent), got %s" % growth)
    overlap = finite_nonneg("overlap-months", a["overlap_months"])
    if overlap != int(overlap):
        raise InputError("--overlap-months must be a whole number")
    overrun = finite_nonneg("overrun", a["overrun"])
    if overrun < 1.0:
        raise InputError("--overrun must be 1 or more")
    years = finite_nonneg("years", a["years"])
    if years < 1 or years != int(years) or years > 10:
        raise InputError("--years must be a whole number from 1 to 10")
    limit = finite_nonneg("payback-limit", a["payback_limit"])
    if limit > 1200:
        raise InputError("--payback-limit is in months; 1200 (100 years) is the most this model will simulate")
    if overlap > years * 12:
        raise InputError("--overlap-months is longer than the horizon")

    own_annual = run_cost + mh * 12 * (hr or 0.0)
    p = {"subscription": sub, "own_annual": own_annual, "price_growth": growth,
         "overlap_months": int(overlap), "years": int(years)}
    build_total = build + mig
    warnings = []
    if (a["build_cost"] is None and (a["day_rate"] or 0) == 0) or build == 0:
        warnings.append("build labour is priced at 0: your own time is a cost, so payback is flattered")
    if mh == 0:
        warnings.append("maintenance is 0 hours a month: almost all software needs some, so payback is flattered")
    if own_annual >= sub * (1 + growth) ** (int(years) - 1):
        warnings.append("the new build costs as much to run each year as the old tool does even at its highest price "
                        "inside the horizon, so it cannot pay back within it")

    base = model(p, build_total)
    stress = model(p, build_total * overrun)
    horizon = int(years * 12)
    L = int(limit)
    # the ceiling is the money the first L months can repay, however short the simulated horizon is
    if L > 0:
        reach = dict(p, years=max(int(years), (L + 11) // 12))
        ceiling = sum(model(reach, build_total)[3][:L])
    else:
        ceiling = 0.0

    def scen(label, res, cost):
        return {"label": label, "build_total": cost,
                "payback_months": res[0], "net_at_horizon": res[1], "yearly": res[2]}

    sb, ss = scen("base", base, build_total), scen("overrun x%g" % overrun, stress, build_total * overrun)
    in_limit = lambda s: s["payback_months"] is not None and s["payback_months"] <= limit
    if in_limit(ss) and ss["net_at_horizon"] > 0:
        verdict = "BUILD"
    elif sb["payback_months"] is not None:
        verdict = "MARGINAL"
    else:
        verdict = "KEEP SAAS"
    rep = {
        "verdict": verdict, "horizon_months": horizon, "payback_limit_months": limit,
        "inputs": {"subscription_per_year": sub, "build": round(build, 2), "migration": mig,
                   "run_cost_per_year": run_cost, "maintenance_cost_per_year": round(mh * 12 * (hr or 0), 2),
                   "own_cost_per_year": round(own_annual, 2), "price_growth": growth,
                   "overlap_months": int(overlap), "overrun": overrun},
        "base": sb, "stress": ss,
        "build_budget_ceiling": round(max(ceiling, 0.0), 2),
        "warnings": warnings,
    }
    check_finite(rep)
    return rep


def fmt(r):
    pm = lambda s: ("month %d" % s["payback_months"]) if s["payback_months"] is not None else \
        "not within %d months" % r["horizon_months"]
    i = r["inputs"]
    L = ["Verdict: %s" % r["verdict"], "",
         "Old tool: %.0f a year. New build runs at %.0f a year (hosting/services %.0f + maintenance %.0f)." % (
             i["subscription_per_year"], i["own_cost_per_year"], i["run_cost_per_year"], i["maintenance_cost_per_year"]),
         "One-off cost: build %.0f + migration %.0f = %.0f. Old tool kept for %d overlap month(s)." % (
             i["build"], i["migration"], i["build"] + i["migration"], i["overlap_months"]), "",
         "| case | one-off cost | payback | net over %d months |" % r["horizon_months"], "|---|---|---|---|"]
    for s in (r["base"], r["stress"]):
        L.append("| %s | %.0f | %s | %.0f |" % (s["label"], s["build_total"], pm(s), s["net_at_horizon"]))
    L += ["", "Base case by year:", "| year | old tool avoided | own cost | net saving | cumulative after build |",
          "|---|---|---|---|---|"]
    for y in r["base"]["yearly"]:
        L.append("| %d | %.0f | %.0f | %.0f | %.0f |" % (y["year"], y["old_tool_avoided"], y["own_cost"],
                                                          y["net_saving"], y["cumulative_after_build"]))
    L += ["", "Most you can spend on build + migration and still pay back inside %g months: %.0f" % (
        r["payback_limit_months"], r["build_budget_ceiling"])]
    for w in r["warnings"]:
        L.append("WARNING: " + w)
    L.append("These are the inputs you gave. The old price is assumed to rise as stated; nothing is looked up.")
    return "\n".join(L)


def check_destination(path, inputs=()):
    """Refuse to write a report over anything that is not a plain report file of our own: a symlink, a device or
    pipe, or any input file (the same file under another name, including a hard link, counts)."""
    if os.path.islink(path):
        raise OSError("%s is a symlink: refusing to write through it" % path)
    if os.path.exists(path):
        if not os.path.isfile(path):
            raise OSError("%s exists and is not a regular file" % path)
        for i in inputs:
            if i and os.path.exists(i) and os.path.samefile(i, path):
                raise OSError("%s is one of the input files: refusing to overwrite it" % path)


def safe_write(path, text, inputs=()):
    """Write text to path without touching anything that is not ours: validate the destination, stage in the same
    folder, then replace, so a failure leaves any existing file as it was."""
    check_destination(path, inputs)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=folder, prefix=".swap-report-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    f = lambda s: float(s)
    p.add_argument("--subscription", type=f, required=True)
    p.add_argument("--run-cost", type=f, default=None)
    p.add_argument("--build-days", type=f, default=None)
    p.add_argument("--day-rate", type=f, default=None)
    p.add_argument("--build-cost", type=f, default=None)
    p.add_argument("--migration-cost", type=f, default=0.0)
    p.add_argument("--maintenance-hours-month", type=f, default=0.0)
    p.add_argument("--hourly-rate", type=f, default=None)
    p.add_argument("--price-growth", type=f, default=0.0)
    p.add_argument("--overlap-months", type=f, default=1.0)
    p.add_argument("--overrun", type=f, default=1.5)
    p.add_argument("--years", type=f, default=3.0)
    p.add_argument("--payback-limit", type=f, default=18.0)
    p.add_argument("--json", default=None)
    ns = p.parse_args(argv)
    try:
        rep = run(vars(ns))
    except InputError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    print(fmt(rep))
    if ns.json:
        try:
            text = json.dumps(rep, indent=2, allow_nan=False)      # serialise first: a failure leaves no partial file
            safe_write(ns.json, text, [])
        except (OSError, ValueError) as e:
            print("error: cannot write %s: %s" % (ns.json, e), file=sys.stderr)
            return 2
    return 1 if rep["verdict"] == "KEEP SAAS" else 0


if __name__ == "__main__":
    sys.exit(main())
