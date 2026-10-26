import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import roi  # noqa: E402

BASE = dict(subscription=12000.0, run_cost=1200.0, build_days=None, day_rate=None, build_cost=6000.0,
            migration_cost=0.0, maintenance_hours_month=0.0, hourly_rate=None, price_growth=0.0,
            overlap_months=1.0, overrun=1.5, years=3.0, payback_limit=18.0)


def args(**kw):
    d = dict(BASE)
    d.update(kw)
    return d


class RoiTests(unittest.TestCase):
    def test_hand_computed_base_case(self):
        # own 100/mo, old 1000/mo. Month 1 overlap: -100. Then +900/mo.
        # -6000 -100 = -6100; 7 more months of 900 = 6300 -> payback month 8.
        r = roi.run(args())
        self.assertEqual(r["base"]["payback_months"], 8)
        self.assertAlmostEqual(r["base"]["net_at_horizon"], -6000 - 100 + 900 * 35)
        self.assertAlmostEqual(r["base"]["yearly"][0]["cumulative_after_build"], 3800)
        self.assertAlmostEqual(r["base"]["yearly"][0]["old_tool_avoided"], 11000)

    def test_hand_computed_overrun_case(self):
        r = roi.run(args())
        self.assertEqual(r["stress"]["build_total"], 9000)
        self.assertEqual(r["stress"]["payback_months"], 12)
        self.assertAlmostEqual(r["stress"]["net_at_horizon"], 22400)
        self.assertEqual(r["verdict"], "BUILD")

    def test_budget_ceiling(self):
        r = roi.run(args())
        self.assertAlmostEqual(r["build_budget_ceiling"], -100 + 17 * 900)

    def test_ceiling_is_consistent_with_payback(self):
        r = roi.run(args())
        at_ceiling = roi.run(args(build_cost=r["build_budget_ceiling"]))
        self.assertEqual(at_ceiling["base"]["payback_months"], 18)
        over = roi.run(args(build_cost=r["build_budget_ceiling"] + 1))
        self.assertGreater(over["base"]["payback_months"], 18)

    def test_budget_ceiling_does_not_depend_on_the_horizon(self):
        # 12 months of horizon but an 18-month payback window: the ceiling must still cover 18 months
        a = args(subscription=1200.0, run_cost=120.0, build_cost=100.0, payback_limit=18.0, years=1.0)
        b = args(subscription=1200.0, run_cost=120.0, build_cost=100.0, payback_limit=18.0, years=2.0)
        self.assertAlmostEqual(roi.run(a)["build_budget_ceiling"], roi.run(b)["build_budget_ceiling"])
        self.assertAlmostEqual(roi.run(a)["build_budget_ceiling"], -10 + 17 * 90)

    def test_extreme_payback_limit_and_growth_are_clean_errors(self):
        with self.assertRaises(roi.InputError):
            roi.run(args(payback_limit=13000.0, price_growth=1.0))
        with self.assertRaises(roi.InputError):
            roi.run(args(payback_limit=1e9))

    def test_huge_finite_inputs_are_refused_not_reported(self):
        with self.assertRaises(roi.InputError):
            roi.run(args(subscription=1e308, run_cost=0.0, build_cost=1e308, price_growth=1.0, years=10.0))

    def test_price_growth_applies_each_year(self):
        r = roi.run(args(price_growth=0.10))
        self.assertAlmostEqual(r["base"]["yearly"][1]["old_tool_avoided"], 13200)
        self.assertAlmostEqual(r["base"]["yearly"][2]["old_tool_avoided"], 14520)

    def test_maintenance_priced_into_own_cost(self):
        r = roi.run(args(maintenance_hours_month=2.0, hourly_rate=80.0))
        self.assertAlmostEqual(r["inputs"]["own_cost_per_year"], 1200 + 2 * 12 * 80)
        self.assertEqual(r["warnings"], [])

    def test_build_days_times_day_rate(self):
        r = roi.run(args(build_cost=None, build_days=10.0, day_rate=600.0, migration_cost=500.0))
        self.assertEqual(r["base"]["build_total"], 6500)

    def test_keep_saas_when_run_cost_exceeds_subscription(self):
        r = roi.run(args(subscription=1000.0, run_cost=1200.0))
        self.assertEqual(r["verdict"], "KEEP SAAS")
        self.assertIsNone(r["base"]["payback_months"])
        self.assertTrue(any("cannot pay back" in w for w in r["warnings"]))

    def test_marginal_when_pays_back_only_beyond_limit(self):
        r = roi.run(args(build_cost=20000.0, payback_limit=12.0))
        self.assertEqual(r["verdict"], "MARGINAL")

    def test_marginal_when_only_base_inside_limit(self):
        # base build 12000 pays back in month 15; x1.5 = 18000 pays back in month 22 > 18
        r = roi.run(args(build_cost=12000.0))
        self.assertLessEqual(r["base"]["payback_months"], 18)
        self.assertGreater(r["stress"]["payback_months"], 18)
        self.assertEqual(r["verdict"], "MARGINAL")

    def test_never_pay_back_warning_only_when_it_is_true(self):
        # flat price: running cost equals the subscription -> the warning is right
        w = roi.run(args(subscription=1200.0, run_cost=1200.0, price_growth=0.0))["warnings"]
        self.assertTrue(any("cannot pay back" in x for x in w))
        # rising price: year-3 price is far above running cost, so no such warning
        r = roi.run(args(subscription=1200.0, run_cost=1300.0, build_cost=100.0, price_growth=0.5))
        self.assertFalse(any("cannot pay back" in x for x in r["warnings"]), r["warnings"])
        self.assertIsNotNone(r["base"]["payback_months"])

    def test_flattery_warnings(self):
        r = roi.run(args())
        self.assertTrue(any("maintenance is 0" in w for w in r["warnings"]))
        r2 = roi.run(args(build_cost=None, build_days=10.0, day_rate=0.0))
        self.assertTrue(any("build labour is priced at 0" in w for w in r2["warnings"]))

    def test_bad_input(self):
        bad = [
            args(subscription=0.0), args(subscription=-5.0), args(subscription=float("nan")),
            args(run_cost=None), args(build_cost=None), args(build_cost=None, build_days=5.0),
            args(build_days=5.0, day_rate=100.0),
            args(maintenance_hours_month=3.0), args(maintenance_hours_month=3.0, hourly_rate=0.0),
            args(price_growth=8.0), args(overlap_months=1.5), args(overlap_months=99.0),
            args(overrun=0.5), args(years=0.0), args(years=2.5), args(years=11.0),
            args(run_cost=float("inf")), args(migration_cost=-1.0),
        ]
        for a in bad:
            with self.assertRaises(roi.InputError, msg=str(a)):
                roi.run(a)

    def test_cli(self):
        out = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        out.close()
        self.addCleanup(os.unlink, out.name)
        cmd = [sys.executable, os.path.join(HERE, "roi.py"), "--subscription", "12000", "--run-cost", "1200",
               "--build-cost", "6000", "--json", out.name]
        r = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("Verdict: BUILD", r.stdout)
        with open(out.name) as fh:
            self.assertEqual(json.load(fh)["verdict"], "BUILD")
        keep = subprocess.run([sys.executable, os.path.join(HERE, "roi.py"), "--subscription", "1000",
                               "--run-cost", "1200", "--build-cost", "6000"], capture_output=True, text=True)
        self.assertEqual(keep.returncode, 1)
        bad = subprocess.run([sys.executable, os.path.join(HERE, "roi.py"), "--subscription", "1000"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_unwritable_json_is_a_clean_error(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "roi.py"), "--subscription", "12000", "--run-cost", "1200",
                            "--build-cost", "6000", "--json", "/no/such/dir/o.json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
