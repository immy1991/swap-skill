import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sellmodel  # noqa: E402

BASE = dict(price=30.0, new_per_month=10.0, churn=0.05, cac=60.0, cost_per_customer_month=5.0,
            fixed_monthly=200.0, build_cost=10000.0, build_days=None, day_rate=None, launch_cost=0.0,
            ramp_months=1.0, years=3.0, payback_limit=24.0, overrun=1.5, acq_stress=0.5, min_ltv_cac=3.0)


def args(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


class SellModelTests(unittest.TestCase):
    def test_unit_economics_hand_computed(self):
        r = sellmodel.run(args())
        u = r["unit_economics"]
        self.assertAlmostEqual(u["margin_per_customer_month"], 25.0)
        self.assertAlmostEqual(u["ltv"], 25.0 / 0.05)            # 500
        self.assertAlmostEqual(u["ltv_to_cac"], 500.0 / 60.0, places=2)
        self.assertAlmostEqual(u["break_even_customers_for_fixed_costs"], 200.0 / 25.0)
        self.assertAlmostEqual(u["steady_state_customers_at_full_acquisition"], 10.0 / 0.05)

    def test_first_month_cash_hand_computed(self):
        # ramp 1 => month 1 new = 10, customers = 10, cash = 10*25 - 200 - 10*60 = -550
        p = dict(price=30.0, new=10.0, churn=0.05, cac=60.0, var=5.0, fixed=200.0, ramp=1.0, years=1)
        res = sellmodel.simulate(p, 10000.0, 1.0)
        # reconstruct month 1 by running a 1-month horizon difference: lowest point after month 1
        self.assertLessEqual(res["lowest_point"], -10550.0)

    def test_dont_sell_when_margin_not_positive(self):
        r = sellmodel.run(args(cost_per_customer_month=30.0))
        self.assertEqual(r["verdict"], "DON'T SELL")
        self.assertTrue(any("loses money" in w for w in r["warnings"]))

    def test_dont_sell_when_never_pays_back(self):
        r = sellmodel.run(args(build_cost=5_000_000.0))
        self.assertEqual(r["verdict"], "DON'T SELL")
        self.assertIsNone(r["base"]["payback_months"])

    def test_sell_when_robust(self):
        r = sellmodel.run(args(build_cost=3000.0, cac=30.0, new_per_month=20.0, fixed_monthly=100.0))
        self.assertEqual(r["verdict"], "SELL")
        self.assertLessEqual(r["stress"]["payback_months"], 24)

    def test_zero_cac_cannot_be_sell(self):
        r = sellmodel.run(args(build_cost=3000.0, cac=0.0, new_per_month=20.0, fixed_monthly=100.0))
        self.assertEqual(r["verdict"], "MARGINAL")
        self.assertIsNone(r["unit_economics"]["ltv_to_cac"])
        self.assertTrue(any("CAC is 0" in w for w in r["warnings"]))

    def test_marginal_when_ratio_too_low(self):
        r = sellmodel.run(args(build_cost=3000.0, cac=180.0, new_per_month=20.0, fixed_monthly=100.0))
        self.assertLess(r["unit_economics"]["ltv_to_cac"], 3.0)
        self.assertEqual(r["verdict"], "MARGINAL")

    def test_stress_is_never_better_than_base(self):
        r = sellmodel.run(args())
        self.assertLessEqual(r["stress"]["net_at_horizon"], r["base"]["net_at_horizon"])

    def test_assumptions_are_recorded_for_downstream_skills(self):
        a = sellmodel.run(args())["assumptions"]
        self.assertEqual(a["price_per_customer_month"], 30.0)
        self.assertEqual(a["cost_per_customer_month"], 5.0)
        self.assertEqual(a["fixed_monthly"], 200.0)
        self.assertEqual(a["new_customers_per_month"], 10.0)
        self.assertEqual(a["monthly_churn"], 0.05)

    def test_payback_limit_is_bounded(self):
        with self.assertRaises(sellmodel.InputError):
            sellmodel.run(args(payback_limit=5000.0))

    def test_huge_finite_inputs_never_give_a_verdict(self):
        with self.assertRaises(sellmodel.InputError):
            sellmodel.run(args(price=1e308, new_per_month=10.0, cost_per_customer_month=0.0))

    def test_build_days_times_rate(self):
        r = sellmodel.run(args(build_cost=None, build_days=20.0, day_rate=500.0, launch_cost=1000.0))
        self.assertEqual(r["inputs"]["build"], 10000.0)
        self.assertEqual(r["inputs"]["launch"], 1000.0)

    def test_unpriced_labour_warns(self):
        r = sellmodel.run(args(build_cost=None, build_days=20.0, day_rate=0.0))
        self.assertTrue(any("build labour is priced at 0" in w for w in r["warnings"]))

    def test_bad_input(self):
        bad = [args(price=0.0), args(price=-1.0), args(churn=0.0), args(churn=1.5), args(new_per_month=0.0),
               args(cac=None), args(cost_per_customer_month=None), args(fixed_monthly=None),
               args(build_cost=None), args(build_days=5.0), args(years=2.5), args(years=0.0),
               args(overrun=0.5), args(acq_stress=0.0), args(acq_stress=2.0), args(price=float("nan")),
               args(cac=float("inf")), args(launch_cost=-1.0)]
        for a in bad:
            with self.assertRaises(sellmodel.InputError, msg=str(a)):
                sellmodel.run(a)

    def test_cli_exit_codes_and_json(self):
        out = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        out.close()
        self.addCleanup(os.unlink, out.name)
        base = [sys.executable, os.path.join(HERE, "sellmodel.py"), "--price", "30", "--new-per-month", "20",
                "--churn", "0.05", "--cac", "30", "--cost-per-customer-month", "5", "--fixed-monthly", "100",
                "--build-cost", "3000"]
        ok = subprocess.run(base + ["--json", out.name], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("Verdict: SELL", ok.stdout)
        with open(out.name) as fh:
            self.assertEqual(json.load(fh)["verdict"], "SELL")
        no = subprocess.run(base[:-1] + ["5000000"], capture_output=True, text=True)
        self.assertEqual(no.returncode, 1)
        bad = subprocess.run([sys.executable, os.path.join(HERE, "sellmodel.py"), "--price", "30"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_unwritable_json_is_a_clean_error(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "sellmodel.py"), "--price", "30", "--new-per-month", "20",
                            "--churn", "0.05", "--cac", "30", "--cost-per-customer-month", "5", "--fixed-monthly", "100",
                            "--build-cost", "3000", "--json", "/no/such/dir/o.json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
