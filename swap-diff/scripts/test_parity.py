import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import parity  # noqa: E402

HEADER = "feature,priority,in_scope,status\n"


def tmp(body, header=HEADER):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    fh.write(header + body)
    fh.close()
    return fh.name


class ParityTests(unittest.TestCase):
    def rep(self, body, th=85):
        p = tmp(body)
        self.addCleanup(os.unlink, p)
        return parity.run(parity.load(p), th)

    def test_all_done_is_100_and_shippable(self):
        r = self.rep("A,must,yes,done\nB,should,yes,done\nC,could,yes,done\n")
        self.assertEqual(r["score"], 100.0)
        self.assertTrue(r["shippable"])

    def test_weighted_score_exact(self):
        # weights 3+2+1 = 6; earned 3 + 1 (partial should) + 0 = 4 -> 66.7
        r = self.rep("A,must,yes,done\nB,should,yes,partial\nC,could,yes,missing\n", th=0)
        self.assertAlmostEqual(r["score"], 66.7, places=1)

    def test_partial_must_blocks_shipping_even_with_high_score(self):
        body = "M,must,yes,partial\n" + "".join("S%d,should,yes,done\n" % i for i in range(30))
        r = self.rep(body)
        self.assertGreater(r["score"], 85)
        self.assertFalse(r["shippable"])
        self.assertEqual(r["must_gaps"], ["M"])

    def test_missing_must_blocks(self):
        r = self.rep("M,must,yes,missing\nS,should,yes,done\n")
        self.assertFalse(r["shippable"])

    def test_todo_counts_as_missing(self):
        r = self.rep("M,must,yes,done\nS,should,yes,todo\n", th=0)
        self.assertIn("S", r["missing"])
        self.assertAlmostEqual(r["score"], 60.0)

    def test_threshold_blocks_when_musts_done(self):
        r = self.rep("M,must,yes,done\nS,should,yes,missing\nS2,should,yes,missing\n")
        self.assertFalse(r["shippable"])
        self.assertTrue(any("threshold" in x for x in r["reasons"]))

    def test_dropped_and_added_are_not_scored(self):
        r = self.rep("A,must,yes,done\nX,should,no,dropped\nY,could,no,added\n")
        self.assertEqual(r["score"], 100.0)
        self.assertEqual(r["deliberately_cut"], ["X"])
        self.assertEqual(r["extras"], ["Y"])
        self.assertEqual(r["in_scope_count"], 1)

    def test_contradictions_block_shipping(self):
        for body in ("A,must,yes,done\nB,should,no,done\n",
                     "A,must,yes,done\nB,should,yes,added\n"):
            r = self.rep(body)
            self.assertTrue(r["contradictions"], body)
            self.assertFalse(r["shippable"], body)

    def test_saved_score_is_exact_so_a_gate_can_compare_it_with_the_threshold(self):
        # two musts done plus one missing could: 9 of 10... exact value is 85.714285...
        r = self.rep("A,must,yes,done\nB,must,yes,done\nC,could,yes,missing\n", th=85.71)
        self.assertTrue(r["shippable"])
        self.assertGreater(r["score"], 85.71)
        self.assertNotEqual(r["score"], round(r["score"], 1))

    def test_in_scope_dropped_counts_missing(self):
        r = self.rep("A,must,yes,done\nB,should,yes,dropped\n", th=0)
        self.assertIn("B", r["missing"])
        self.assertTrue(r["contradictions"])

    def test_empty_scope_is_not_shippable(self):
        r = self.rep("X,should,no,dropped\n")
        self.assertFalse(r["shippable"])
        self.assertEqual(r["score"], 0.0)

    def test_bad_input(self):
        bad = ["A,urgent,yes,done\n", "A,must,maybe,done\n", "A,must,yes,finished\n",
               "A,must,yes,done\nA,must,yes,done\n", ",must,yes,done\n"]
        for body in bad:
            p = tmp(body)
            self.addCleanup(os.unlink, p)
            with self.assertRaises(parity.InputError, msg=body):
                parity.load(p)

    def test_cli_exit_codes(self):
        good, bad, junk = tmp("A,must,yes,done\n"), tmp("A,must,yes,missing\n"), tmp("A,x,yes,done\n")
        for p in (good, bad, junk):
            self.addCleanup(os.unlink, p)
        go = lambda p, *x: subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), p] + list(x),
                                          capture_output=True, text=True)
        self.assertEqual(go(good).returncode, 0)
        self.assertIn("SHIPPABLE", go(good).stdout)
        self.assertEqual(go(bad).returncode, 1)
        self.assertEqual(go(junk).returncode, 2)
        self.assertEqual(go(good, "--ship-threshold", "150").returncode, 2)

    def test_unwritable_outputs_are_clean_errors(self):
        p = tmp("A,must,yes,done\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), p, "--json", "/no/such/dir/o.out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "--json")
        self.assertNotIn("Traceback", r.stderr)

    def test_saved_report_records_the_hash_of_the_list_it_scored(self):
        import hashlib, json as _j
        p = tmp("A,must,yes,done\n")
        out = p + ".json"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), p, "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(p, "rb") as fh:
            want = hashlib.sha256(fh.read()).hexdigest()
        with open(out) as fh:
            self.assertEqual(_j.load(fh)["input_sha256"], want)

    def test_non_utf8_input_is_a_clean_error(self):
        p = tmp("A,must,yes,done\n")
        self.addCleanup(os.unlink, p)
        with open(p, "wb") as fh:
            fh.write(b"tool,annual_cost,feature,priority,in_scope,status\n\xff\xfe,1,x,must,yes,done\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_duplicate_column_names_are_rejected(self):
        import tempfile as _t
        fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
        fh.write("feature,priority,in_scope,status,status\nCore,must,yes,missing,done\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), fh.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("duplicate column", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_row_with_the_wrong_number_of_cells_is_an_error_not_a_blank(self):
        import tempfile as _t
        for body in ("feature,priority,in_scope,status\nBooking,must,yes,done\n,,,,Authentication,must,yes,missing\n", "feature,priority,in_scope,status\nBooking,must,yes,done\n,,,,Authentication,must,yes,missing\n".replace("\\n,,,,", "\\nonly,one\\n,,,,")):
            fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
            fh.write(body.replace("\\n", "\n"))
            fh.close()
            self.addCleanup(os.unlink, fh.name)
            r = subprocess.run([sys.executable, os.path.join(HERE, "parity.py"), fh.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("different number of cells", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
