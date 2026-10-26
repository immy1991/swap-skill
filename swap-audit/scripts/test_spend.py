import datetime
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import spend  # noqa: E402

TODAY = datetime.date(2026, 10, 26)
HEADER = "tool,category,pricing,annual_cost,seats,active_users,features_used,features_total,renewal_date,notice_days\n"


def write(body, header=HEADER):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    fh.write(header + body)
    fh.close()
    return fh.name


class SpendTests(unittest.TestCase):
    def run_rows(self, body, **kw):
        path = write(body)
        self.addCleanup(os.unlink, path)
        rows = spend.load(path)
        return spend.run(rows, kw.get("min_cost", 1000), 0.35, 0.60, TODAY)

    def test_candidate_when_expensive_and_barely_used(self):
        r = self.run_rows("Bookly,scheduling,per_seat,6000,10,4,3,20,,\n")
        t = r["tools"][0]
        self.assertEqual(t["verdict"], "CANDIDATE")
        self.assertAlmostEqual(t["utilisation"], 0.15)
        self.assertAlmostEqual(t["unused_value"], 6000 * 0.85)
        self.assertAlmostEqual(t["idle_seat_share"], 0.6)
        self.assertAlmostEqual(t["cost_per_active_user"], 1500)

    def test_regulated_never_candidate_even_if_unused(self):
        r = self.run_rows("PayrollCo,payroll,flat,9000,,,1,50,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "REGULATED")

    def test_a_tool_with_no_category_is_never_a_candidate_even_if_named_like_a_regulated_one(self):
        r = self.run_rows("Payroll,,flat,9000,,,1,50,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "NEEDS-CATEGORY")
        self.assertNotEqual(r["tools"][0]["verdict"], "CANDIDATE")
        r = self.run_rows("Plain,,flat,9000,,,1,50,,\nBookly,scheduling,flat,9000,,,1,50,,\n")
        self.assertEqual({t["tool"]: t["verdict"] for t in r["tools"]}, {"Plain": "NEEDS-CATEGORY", "Bookly": "CANDIDATE"})

    def test_no_data_is_not_judged(self):
        r = self.run_rows("Mystery,crm,flat,9000,,,,,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "NO-DATA")
        self.assertEqual(r["no_data_count"], 1)

    def test_under_min_cost_is_keep(self):
        r = self.run_rows("Tiny,notes,flat,300,1,1,1,20,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "KEEP")

    def test_look_band_by_idle_seats(self):
        r = self.run_rows("Mid,crm,per_seat,5000,10,5,14,20,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "LOOK")

    def test_boundary_is_inclusive(self):
        r = self.run_rows("Edge,crm,flat,2000,,,7,20,,\n")
        self.assertEqual(r["tools"][0]["verdict"], "CANDIDATE")

    def test_sorted_candidates_first_by_unused_value(self):
        r = self.run_rows(
            "Keepy,crm,flat,8000,,,19,20,,\n"
            "SmallWaste,crm,flat,2000,,,2,20,,\n"
            "BigWaste,crm,flat,9000,,,2,20,,\n")
        self.assertEqual([t["tool"] for t in r["tools"]], ["BigWaste", "SmallWaste", "Keepy"])

    def test_notice_deadline_missed(self):
        r = self.run_rows("Late,crm,flat,5000,,,2,20,2026-11-30,60\n")
        t = r["tools"][0]
        self.assertEqual(t["notice_deadline"], "2026-10-01")
        self.assertLess(t["days_to_notice_deadline"], 0)
        self.assertIn("missed", t["flag"])

    def test_notice_deadline_soon(self):
        r = self.run_rows("Soon,crm,flat,5000,,,2,20,2027-01-15,30\n")
        self.assertIn("within 90 days", r["tools"][0]["flag"])

    def test_counts_must_be_whole_numbers_and_notice_days_too(self):
        for body in ("A,crm,flat,1000,,1e-320,,,,\n", "A,crm,flat,1000,10,2.5,,,,\n", "A,crm,flat,1000,,,3.5,20,,\n",
                     "A,crm,flat,1000,,,,,2027-03-01,30.9\n", "A,crm,flat,1000,1e12,5,,,,\n"):
            p = write(body)
            self.addCleanup(os.unlink, p)
            r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p, "--today", "2026-10-26"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, body)
            self.assertIn("whole number" if "1e12" not in body else "implausibly", r.stderr, body)
            self.assertNotIn("Traceback", r.stderr, body)

    def test_a_failed_json_serialisation_leaves_no_partial_file(self):
        p = write("A,crm,flat,1e308,,,2,20,,\nB,crm,flat,1e308,,,2,20,,\n")
        self.addCleanup(os.unlink, p)
        out = p + ".json"
        r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p, "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertFalse(os.path.exists(out))

    def test_overflowing_totals_are_a_clean_error(self):
        p = write("A,crm,flat,1e308,,,2,20,,\nB,crm,flat,1e308,,,2,20,,\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)
        self.assertNotIn("Infinity", r.stdout)

    def test_currency_is_never_assumed(self):
        r = self.run_rows("A,crm,flat,4000,,,2,20,,\n")
        self.assertEqual(r["currency"], "not stated")
        self.assertNotIn("USD", r["currency_note"])
        rr = spend.run(spend.load(write("A,crm,flat,4000,,,2,20,,\n")), 1000, 0.35, 0.60, TODAY, "GBP")
        self.assertEqual(rr["currency"], "GBP")

    def test_totals(self):
        r = self.run_rows("A,crm,flat,4000,,,2,20,,\nB,crm,flat,1000,,,19,20,,\n")
        self.assertEqual(r["total_annual_spend"], 5000)
        self.assertEqual(r["candidate_spend"], 4000)

    def test_dollar_and_comma_amounts_parse(self):
        r = self.run_rows('A,crm,flat,"$4,000",,,2,20,,\n')
        self.assertEqual(r["tools"][0]["annual_cost"], 4000)

    def test_rejects_bad_input(self):
        bad = [
            "A,crm,flat,-5,,,,,,\n",
            "A,crm,flat,abc,,,,,,\n",
            "A,crm,flat,nan,,,,,,\n",
            "A,crm,flat,100,,,25,20,,\n",
            "A,crm,flat,100,,,1,0,,\n",
            "A,crm,flat,100,2,5,,,,\n",
            "A,crm,weekly,100,,,,,,\n",
            "A,crm,flat,100,,,,,not-a-date,\n",
            "A,crm,flat,100,,,,,,\nA,crm,flat,100,,,,,,\n",
            ",crm,flat,100,,,,,,\n",
        ]
        for body in bad:
            path = write(body)
            self.addCleanup(os.unlink, path)
            with self.assertRaises(spend.InputError, msg=body):
                spend.load(path)

    def test_missing_required_column(self):
        path = write("A,5\n", header="tool,cost\n")
        self.addCleanup(os.unlink, path)
        with self.assertRaises(spend.InputError):
            spend.load(path)

    def test_cli_exit_codes(self):
        good = write("Bookly,scheduling,per_seat,6000,10,4,3,20,,\n")
        bad = write("A,crm,flat,-1,,,,,,\n")
        self.addCleanup(os.unlink, good)
        self.addCleanup(os.unlink, bad)
        ok = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), good, "--today", "2026-10-26"],
                            capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("CANDIDATE", ok.stdout)
        no = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), bad], capture_output=True, text=True)
        self.assertEqual(no.returncode, 2)
        self.assertIn("negative", no.stderr)

    def test_infinite_or_out_of_range_thresholds_are_rejected(self):
        good = write("Bookly,scheduling,flat,6000,,,18,20,,\n")
        self.addCleanup(os.unlink, good)
        run = lambda *x: subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), good, "--today", "2026-10-26"] + list(x),
                                        capture_output=True, text=True)
        for args in (["--cand-util", "inf", "--look-util", "inf"], ["--min-cost", "inf"], ["--cand-util", "nan"],
                     ["--look-util", "1.5"], ["--cand-util", "-0.1"]):
            r = run(*args)
            self.assertEqual(r.returncode, 2, args)
            self.assertNotIn("Traceback", r.stderr, args)

    def test_hostile_notice_days_are_clean_errors(self):
        for body in ("A,crm,flat,100,,,,,2027-03-01,99999999999\n", "A,crm,flat,100,,,,,0001-01-05,3650\n",
                     "A,crm,flat,100,,,,,2027-03-01,3651\n"):
            p = write(body)
            self.addCleanup(os.unlink, p)
            r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p, "--today", "2026-10-26"],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, body)
            self.assertNotIn("Traceback", r.stderr, body)

    def test_unwritable_json_is_a_clean_error(self):
        p = write("A,crm,flat,100,,,,,,\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p, "--json", "/no/such/dir/o.json"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_non_utf8_input_is_a_clean_error(self):
        p = write("A,crm,flat,100,,,,,,\n")
        self.addCleanup(os.unlink, p)
        with open(p, "wb") as fh:
            fh.write(b"tool,annual_cost,feature,priority,in_scope,status\n\xff\xfe,1,x,must,yes,done\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_duplicate_column_names_are_rejected(self):
        import tempfile as _t
        fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
        fh.write("tool,annual_cost,annual_cost\nA,100,1\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), fh.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("duplicate column", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_row_with_the_wrong_number_of_cells_is_an_error_not_a_blank(self):
        import tempfile as _t
        for body in ("tool,annual_cost\nA,100\n,,,,B,5000\n", "tool,annual_cost\nA,100\n,,,,B,5000\n".replace("\\n,,,,", "\\nonly,one\\n,,,,")):
            fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
            fh.write(body.replace("\\n", "\n"))
            fh.close()
            self.addCleanup(os.unlink, fh.name)
            r = subprocess.run([sys.executable, os.path.join(HERE, "spend.py"), fh.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("different number of cells", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
