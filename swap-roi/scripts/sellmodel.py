#!/usr/bin/env python3
"""Will a product you build and sell pay back? Unit economics plus a month-by-month cash model.

Standard library only. Never touches the network. Every number is a flag you supply:
nothing is looked up, and no market benchmark is assumed. The inputs are your assumptions,
and the output says so.

Usage:
  sellmodel.py --price 29 --new-per-month 12 --churn 0.04 --cac 90 \
               --cost-per-customer-month 4 --fixed-monthly 300 --build-days 60 --day-rate 500 [options]

Required
  --price                    per customer per month
  --new-per-month            customers you expect to add per month once marketing is running
  --churn                    fraction of customers lost each month (must be above 0)
  --cac                      cost to win one customer (0 is allowed, but you must say it)
  --cost-per-customer-month  hosting, payment fees and support per customer per month
  --fixed-monthly            costs that do not scale: domain, base hosting, tools
  --build-cost, or --build-days with --day-rate
Options
  --launch-cost 0   one-off: legal checks, trademark, brand assets
  --ramp-months 6   months for acquisition to climb linearly from 0 to --new-per-month
  --years 3  --payback-limit 24  --overrun 1.5  --acq-stress 0.5  --min-ltv-cac 3  --json out.json

Model
  Each month: customers = customers x (1 - churn) + new. Cash = customers x (price - variable cost)
  - fixed - new x CAC. Start at minus (build + launch). Payback = first month the total is zero or better.
  Stress case: build cost x overrun AND acquisition x acq-stress.

Verdict
  SELL        pays back inside the limit in the stress case and LTV:CAC >= --min-ltv-cac
  MARGINAL    pays back inside the horizon in the base case, or the stress case fails the limit
  DON'T SELL  does not pay back inside the horizon in the base case, or margin per customer is not positive
  With CAC of 0 the LTV:CAC ratio is undefined, so the verdict cannot be better than MARGINAL.
  The 3x LTV:CAC line is a common rule of thumb, not a law; it is a flag you can change.

Exit codes: 0 SELL or MARGINAL, 1 DON'T SELL, 2 bad input.
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
    """Huge but finite inputs can overflow to infinity; refuse to report that as a verdict."""
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        raise InputError("the inputs are so large that %s overflowed; check the units" % where)
    if isinstance(obj, dict):
        for k, v in obj.items():
            check_finite(v, k)
    elif isinstance(obj, list):
        for v in obj:
            check_finite(v, where)


def num(name, v, lo=0.0, hi=None, strict_gt=False):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
        raise InputError("--%s must be a finite number" % name)
    if (v <= lo) if strict_gt else (v < lo):
        raise InputError("--%s must be %s %g" % (name, "greater than" if strict_gt else "at least", lo))
    if hi is not None and v > hi:
        raise InputError("--%s must be at most %g" % (name, hi))
    return float(v)


def simulate(p, build_total, acq_mult):
    months = p["years"] * 12
    cust, cum = 0.0, -build_total
    low, payback = cum, None
    series = []
    for m in range(1, months + 1):
        ramp = min(1.0, m / float(p["ramp"])) if p["ramp"] > 0 else 1.0
        new = p["new"] * acq_mult * ramp
        cust = cust * (1.0 - p["churn"]) + new
        cash = cust * (p["price"] - p["var"]) - p["fixed"] - new * p["cac"]
        cum += cash
        low = min(low, cum)
        if payback is None and cum >= 0:
            payback = m
        if m % 12 == 0:
            series.append({"year": m // 12, "customers_end": round(cust, 1), "cumulative_cash": round(cum, 2)})
    return {"payback_months": payback, "net_at_horizon": cum, "lowest_point": low,
            "customers_at_horizon": round(cust, 1), "yearly": series}


def run(a):
    try:
        return _run(a)
    except OverflowError:
        raise InputError("the inputs are so large that the arithmetic overflowed; check the units")


def _run(a):
    price = num("price", a["price"], 0.0, strict_gt=True)
    new = num("new-per-month", a["new_per_month"], 0.0, strict_gt=True)
    churn = num("churn", a["churn"], 0.0, 1.0, strict_gt=True)
    cac = num("cac", a["cac"], 0.0)
    var = num("cost-per-customer-month", a["cost_per_customer_month"], 0.0)
    fixed = num("fixed-monthly", a["fixed_monthly"], 0.0)
    for name, v in (("cac", cac), ("cost-per-customer-month", var), ("fixed-monthly", fixed)):
        if v is None:
            raise InputError("--%s is required (say 0 if it really is nothing)" % name)
    if a["build_cost"] is not None:
        if a["build_days"] is not None or a["day_rate"] is not None:
            raise InputError("give --build-cost OR --build-days with --day-rate, not both")
        build = num("build-cost", a["build_cost"], 0.0)
    else:
        if a["build_days"] is None or a["day_rate"] is None:
            raise InputError("give --build-cost, or both --build-days and --day-rate")
        build = num("build-days", a["build_days"], 0.0) * num("day-rate", a["day_rate"], 0.0)
    launch = num("launch-cost", a["launch_cost"], 0.0)
    ramp = num("ramp-months", a["ramp_months"], 0.0)
    years = num("years", a["years"], 1.0, 10.0)
    if years != int(years):
        raise InputError("--years must be a whole number")
    limit = num("payback-limit", a["payback_limit"], 0.0, 1200.0)
    overrun = num("overrun", a["overrun"], 1.0)
    stress = num("acq-stress", a["acq_stress"], 0.0, 1.0, strict_gt=True)
    min_ratio = num("min-ltv-cac", a["min_ltv_cac"], 0.0)

    margin = price - var
    p = {"price": price, "new": new, "churn": churn, "cac": cac, "var": var, "fixed": fixed,
         "ramp": ramp, "years": int(years)}
    warnings = []
    if margin <= 0:
        warnings.append("variable cost per customer is at or above the price: every customer loses money")
    if cac == 0:
        warnings.append("CAC is 0: free acquisition is a claim, so LTV:CAC is undefined and the verdict cannot be SELL")
    if build == 0 or (a["build_cost"] is None and (a["day_rate"] or 0) == 0):
        warnings.append("build labour is priced at 0: your own time is a cost, so payback is flattered")
    ltv = margin / churn if margin > 0 else 0.0
    ratio = (ltv / cac) if cac > 0 else None
    breakeven_customers = (fixed / margin) if margin > 0 else None
    steady = new / churn

    base = simulate(p, build + launch, 1.0)
    hard = simulate(p, (build + launch) * overrun, stress)
    inside = lambda r: r["payback_months"] is not None and r["payback_months"] <= limit
    if margin <= 0 or base["payback_months"] is None:
        verdict = "DON'T SELL"
    elif inside(hard) and ratio is not None and ratio >= min_ratio:
        verdict = "SELL"
    else:
        verdict = "MARGINAL"
    rep = {
        "verdict": verdict, "horizon_months": int(years) * 12, "payback_limit_months": limit,
        "assumptions": {"price_per_customer_month": price, "new_customers_per_month": new, "monthly_churn": churn,
                        "cac": cac, "cost_per_customer_month": var, "fixed_monthly": fixed, "build": round(build, 2),
                        "launch": launch, "ramp_months": ramp, "years": int(years)},
        "assumptions_note": "every figure below is an assumption you supplied; nothing was looked up",
        "unit_economics": {
            "margin_per_customer_month": margin,
            "ltv": round(ltv, 2), "cac": cac,
            "ltv_to_cac": ratio, "min_ltv_to_cac": min_ratio,
            "break_even_customers_for_fixed_costs": None if breakeven_customers is None else round(breakeven_customers, 1),
            "steady_state_customers_at_full_acquisition": round(steady, 1)},
        "inputs": {"build": round(build, 2), "launch": launch, "ramp_months": ramp, "overrun": overrun,
                   "acquisition_in_stress": stress},
        "base": dict(base, label="base"),
        "stress": dict(hard, label="stress (build x%g, acquisition x%g)" % (overrun, stress)),
        "warnings": warnings,
    }
    check_finite(rep)
    return rep


def fmt(r):
    u = r["unit_economics"]
    pm = lambda s: ("month %d" % s["payback_months"]) if s["payback_months"] is not None else \
        "not within %d months" % r["horizon_months"]
    L = ["Verdict: %s" % r["verdict"], "",
         "Margin per customer per month: %.2f. Lifetime value %.0f, cost to win one customer %.0f, LTV:CAC %s (line: %g)." % (
             u["margin_per_customer_month"], u["ltv"], u["cac"],
             "undefined" if u["ltv_to_cac"] is None else "%.1f" % u["ltv_to_cac"], u["min_ltv_to_cac"]),
         "Customers needed just to cover fixed costs: %s. At full acquisition the base settles near %.0f customers." % (
             "never (no margin)" if u["break_even_customers_for_fixed_costs"] is None else "%.0f" % u["break_even_customers_for_fixed_costs"],
             u["steady_state_customers_at_full_acquisition"]), "",
         "| case | payback | lowest cash point | customers at end | net at %d months |" % r["horizon_months"],
         "|---|---|---|---|---|"]
    for s in (r["base"], r["stress"]):
        L.append("| %s | %s | %.0f | %.0f | %.0f |" % (s["label"], pm(s), s["lowest_point"], s["customers_at_horizon"], s["net_at_horizon"]))
    L += ["", "The lowest cash point is the money you need to have, or find, before it turns."]
    for w in r["warnings"]:
        L.append("WARNING: " + w)
    L.append(r["assumptions_note"] + ". Acquisition in particular is a guess until real customers exist.")
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
    f = float
    p.add_argument("--price", type=f, required=True)
    p.add_argument("--new-per-month", type=f, required=True)
    p.add_argument("--churn", type=f, required=True)
    p.add_argument("--cac", type=f, default=None)
    p.add_argument("--cost-per-customer-month", type=f, default=None)
    p.add_argument("--fixed-monthly", type=f, default=None)
    p.add_argument("--build-cost", type=f, default=None)
    p.add_argument("--build-days", type=f, default=None)
    p.add_argument("--day-rate", type=f, default=None)
    p.add_argument("--launch-cost", type=f, default=0.0)
    p.add_argument("--ramp-months", type=f, default=6.0)
    p.add_argument("--years", type=f, default=3.0)
    p.add_argument("--payback-limit", type=f, default=24.0)
    p.add_argument("--overrun", type=f, default=1.5)
    p.add_argument("--acq-stress", type=f, default=0.5)
    p.add_argument("--min-ltv-cac", type=f, default=3.0)
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
    return 1 if rep["verdict"] == "DON'T SELL" else 0


if __name__ == "__main__":
    sys.exit(main())
