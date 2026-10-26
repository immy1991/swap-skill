import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scope  # noqa: E402

HEADER = "feature,priority,usage,kind,effort_days,confirmed\n"


def write(body, header=HEADER):
    fh = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False)
    fh.write(header + body)
    fh.close()
    return fh.name


class ScopeTests(unittest.TestCase):
    def run_rows(self, body, contingency=1.5):
        p = write(body)
        self.addCleanup(os.unlink, p)
        return scope.run(scope.load(p), contingency)

    def decisions(self, body):
        r = self.run_rows(body)
        d = {}
        for k in ("in_scope", "out_of_scope", "hold"):
            for x in r[k]:
                d[x["feature"]] = x["decision"]
        return d

    def test_core_rules(self):
        d = self.decisions(
            "Book,must,daily,feature,5,yes\n"
            "Remind,should,weekly,feature,2,yes\n"
            "Report,should,rarely,feature,3,yes\n"
            "Theme,could,monthly,feature,1,yes\n"
            "Pin,could,daily,feature,1,yes\n"
            "Fax,must,never,feature,9,yes\n"
            "Mystery,must,unknown,feature,,no\n")
        self.assertEqual(d, {"Book": "IN", "Remind": "IN", "Report": "OUT", "Theme": "OUT",
                             "Pin": "IN", "Fax": "OUT", "Mystery": "HOLD"})

    def test_vendor_owned_is_always_out_even_if_must_and_daily(self):
        d = self.decisions("Marketplace,must,daily,network,10,yes\nCatalogue,must,daily,content,10,yes\nLic,must,daily,licence,1,yes\n")
        self.assertEqual(set(d.values()), {"OUT"})

    def test_integration_rules(self):
        d = self.decisions("Sync,should,monthly,integration,2,yes\nOld,should,rarely,integration,2,yes\nMustInt,must,rarely,integration,2,yes\n")
        self.assertEqual(d, {"Sync": "IN", "Old": "OUT", "MustInt": "IN"})

    def test_effort_math_and_contingency(self):
        r = self.run_rows("A,must,daily,feature,4,yes\nB,must,weekly,feature,6,yes\nC,could,rarely,feature,50,yes\n", 2.0)
        self.assertEqual(r["effort_days_raw"], 10)
        self.assertEqual(r["effort_days_with_contingency"], 20)
        self.assertTrue(r["estimate_complete"])

    def test_missing_effort_makes_estimate_incomplete_and_is_not_guessed(self):
        r = self.run_rows("A,must,daily,feature,4,yes\nB,must,weekly,feature,,yes\n")
        self.assertEqual(r["effort_days_raw"], 4)
        self.assertFalse(r["estimate_complete"])
        self.assertEqual(r["unestimated_in_scope"], ["B"])

    def test_hold_makes_estimate_incomplete(self):
        r = self.run_rows("A,must,daily,feature,4,yes\nB,should,unknown,feature,2,no\n")
        self.assertFalse(r["estimate_complete"])

    def test_unconfirmed_listed(self):
        r = self.run_rows("A,must,daily,feature,4,no\n")
        self.assertEqual(r["unconfirmed_in_scope"], ["A"])

    def test_order_is_priority_then_usage(self):
        r = self.run_rows("S,should,daily,feature,1,yes\nM2,must,monthly,feature,1,yes\nM1,must,daily,feature,1,yes\n")
        self.assertEqual([x["feature"] for x in r["in_scope"]], ["M1", "M2", "S"])

    def test_kind_defaults_to_feature_when_column_absent(self):
        p = write("A,must,daily\n", header="feature,priority,usage\n")
        self.addCleanup(os.unlink, p)
        self.assertEqual(scope.load(p)[0]["kind"], "feature")

    def test_rejects_bad_input(self):
        bad = [
            "A,urgent,daily,feature,1,yes\n",
            "A,must,often,feature,1,yes\n",
            "A,must,daily,widget,1,yes\n",
            "A,must,daily,feature,-1,yes\n",
            "A,must,daily,feature,abc,yes\n",
            "A,must,daily,feature,nan,yes\n",
            "A,must,daily,feature,1,maybe\n",
            "A,must,daily,feature,1,yes\nA,must,daily,feature,1,yes\n",
            ",must,daily,feature,1,yes\n",
        ]
        for body in bad:
            p = write(body)
            self.addCleanup(os.unlink, p)
            with self.assertRaises(scope.InputError, msg=body):
                scope.load(p)

    def test_cli(self):
        p = write("A,must,daily,feature,4,yes\n")
        self.addCleanup(os.unlink, p)
        ok = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stderr)
        self.assertIn("IN SCOPE (1)", ok.stdout)
        no = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--contingency", "0.5"],
                            capture_output=True, text=True)
        self.assertEqual(no.returncode, 2)

    def test_annotate_writes_master_that_parity_accepts(self):
        p = write("A,must,daily,feature,4,yes\nB,could,rarely,feature,2,yes\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--annotate", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        with open(out) as fh:
            lines = fh.read().strip().splitlines()
        self.assertEqual(lines[0], "feature,priority,usage,kind,effort_days,confirmed,in_scope,status")
        self.assertIn("A,must,daily,feature,4,yes,yes,todo", lines)
        self.assertIn("B,could,rarely,feature,2,yes,no,dropped", lines)

    def test_annotate_refuses_while_hold_rows_exist(self):
        p = write("A,must,unknown,feature,4,no\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--annotate", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("HOLD", r.stderr)
        self.assertFalse(os.path.exists(out))

    def _run(self, *args):
        return subprocess.run([sys.executable, os.path.join(HERE, "scope.py")] + list(args), capture_output=True, text=True)

    def test_annotate_refuses_to_overwrite_an_existing_master(self):
        p = write("A,must,daily,feature,4,yes\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        self.assertEqual(self._run(p, "--annotate", out).returncode, 0)
        with open(out) as fh:
            first = fh.read()
        r = self._run(p, "--annotate", out)
        self.assertEqual(r.returncode, 2)
        self.assertIn("--rescope", r.stderr)
        with open(out) as fh:
            self.assertEqual(fh.read(), first)

    def test_json_pointing_at_the_master_cannot_destroy_it(self):
        p = write("A,must,daily,feature,4,yes\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        self.assertEqual(self._run(p, "--annotate", out).returncode, 0)
        with open(out) as fh:
            before = fh.read()
        for args in (("--json", out, "--annotate", out), ("--json", out, "--annotate", out, "--rescope"),
                     ("--json", p), ("--annotate", p), ("--annotate", p, "--rescope")):
            r = self._run(p, *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("same file", r.stderr, args)
        with open(out) as fh:
            self.assertEqual(fh.read(), before)
        with open(p) as fh:
            self.assertTrue(fh.read().startswith("feature,priority,usage,kind,effort_days,confirmed"))
        link = p + ".link"
        os.symlink(out, link)
        self.addCleanup(os.unlink, link)
        r = self._run(p, "--json", link, "--annotate", out)
        self.assertEqual(r.returncode, 2)                  # a symlink alias is caught by the real path

    def test_a_corrupt_existing_master_stops_a_rescope_and_is_left_alone(self):
        p = write("A,must,daily,feature,4,yes\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        hdr = "feature,priority,usage,kind,effort_days,confirmed,in_scope,status\n"
        for label, body in (("duplicate feature rows", hdr + "A,must,daily,feature,4,yes,yes,done\nA,must,daily,feature,4,yes,yes,todo\n"),
                            ("blank feature name", hdr + ",must,daily,feature,4,yes,yes,done\n"),
                            ("invalid status", hdr + "A,must,daily,feature,4,yes,yes,finished\n"),
                            ("duplicate status header", "feature,priority,usage,kind,effort_days,confirmed,in_scope,status,status\nA,must,daily,feature,4,yes,yes,done,todo\n"),
                            ("ragged row", "feature,priority,usage,kind,effort_days,confirmed,in_scope,status\nA,must,daily\n"),
                            ("no status column", "feature,priority\nA,must\n"),
                            ("empty", "")):
            with open(out, "w") as fh:
                fh.write(body)
            r = self._run(p, "--annotate", out, "--rescope")
            self.assertEqual(r.returncode, 2, label)
            self.assertNotIn("Traceback", r.stderr, label)
            with open(out) as fh:
                self.assertEqual(fh.read(), body, label)

    def test_nothing_is_written_when_a_precondition_fails(self):
        p = write("A,must,unknown,feature,4,no\n")
        js = p + ".json"
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        r = self._run(p, "--json", js, "--annotate", out)          # HOLD refuses the annotate: no JSON either
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(js))
        self.assertFalse(os.path.exists(out))

    def test_rescope_keeps_status_extra_columns_and_precision(self):
        p = write("A,must,daily,feature,1.123456789,yes\nB,should,weekly,feature,2,yes\nC,could,rarely,feature,3,yes\n")
        out = p + ".master.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        self.assertEqual(self._run(p, "--annotate", out).returncode, 0)
        with open(out) as fh:
            self.assertIn("A,must,daily,feature,1.123456789,yes,yes,todo", fh.read())
        # build work happens: A done with evidence, B partial, an approved extra X
        with open(out, "w") as fh:
            fh.write("feature,priority,usage,kind,effort_days,confirmed,in_scope,status,evidence\n"
                     "A,must,daily,feature,1.123456789,yes,yes,done,build-log#A\n"
                     "B,should,weekly,feature,2,yes,yes,partial,build-log#B\n"
                     "C,could,rarely,feature,3,yes,no,dropped,\n"
                     "X,could,rarely,feature,1,yes,no,added,approved\n")
        # rescope: B's usage changes to never -> out; D is new
        p2 = write("A,must,daily,feature,1.123456789,yes\nB,should,never,feature,2,yes\nC,could,rarely,feature,3,yes\nD,must,daily,feature,5,yes\n")
        self.addCleanup(os.unlink, p2)
        r = self._run(p2, "--annotate", out, "--rescope")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("B was 'partial' but is now out of scope", r.stdout)
        with open(out) as fh:
            body = fh.read()
        self.assertIn("feature,priority,usage,kind,effort_days,confirmed,in_scope,status,evidence", body)
        self.assertIn("A,must,daily,feature,1.123456789,yes,yes,done,build-log#A", body)
        self.assertIn("B,should,never,feature,2,yes,no,dropped,build-log#B", body)
        self.assertIn("D,must,daily,feature,5,yes,yes,todo,", body)
        self.assertIn("X,could,rarely,feature,1,yes,no,added,approved", body)

    def test_subset_carries_a_narrow_verdict_into_full_scope(self):
        p = write("A,must,daily,feature,4,yes\nB,should,weekly,feature,2,yes\nC,could,unknown,feature,1,no\n")
        sub = p + ".subset.txt"
        with open(sub, "w") as fh:
            fh.write("# approved in swap/market.md\nA\nc\n")
        self.addCleanup(os.unlink, p)
        self.addCleanup(os.unlink, sub)
        rows = scope.load(p)
        r = scope.run(rows, 1.5, "full", False, scope.load_subset(sub))
        got = {x["feature"]: x["decision"] for k in ("in_scope", "out_of_scope") for x in r[k]}
        self.assertEqual(got, {"A": "IN", "B": "OUT", "C": "IN"})
        self.assertIn("NARROW subset", [x for x in r["out_of_scope"] if x["feature"] == "B"][0]["reason"])
        self.assertEqual(r["subset"], ["a", "c"])
        self.assertEqual(self._run(p, "--mode", "full", "--subset", sub).returncode, 0)
        self.assertEqual(self._run(p, "--mode", "lean", "--subset", sub).returncode, 2)       # subset is full-only
        with open(sub, "w") as fh:
            fh.write("A\nNoSuchFeature\n")
        bad = self._run(p, "--mode", "full", "--subset", sub)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("NoSuchFeature".lower(), bad.stderr.lower())

    def test_backlog_unknown_leaves_usage_unknown_and_unblocks_annotate(self):
        p = write("A,must,daily,feature,4,yes\nB,should,unknown,feature,2,no\n")
        out = p + ".m.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = scope.run(scope.load(p), 1.5, "lean", True)
        self.assertEqual([x["feature"] for x in r["out_of_scope"]], ["B"])
        self.assertIn("nobody could say", r["out_of_scope"][0]["reason"])
        self.assertEqual(r["out_of_scope"][0]["usage"], "unknown")
        self.assertEqual(r["counts"]["hold"], 0)
        run = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--backlog-unknown", "--annotate", out],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        with open(out) as fh:
            self.assertIn("B,should,unknown,feature,2,no,no,dropped", fh.read())

    def test_overflowing_effort_is_a_clean_error(self):
        p = write("A,must,daily,feature,1e308,yes\nB,must,daily,feature,1e308,yes\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_non_utf8_csv_is_a_clean_error(self):
        p = write("A,must,daily,feature,4,yes\n")
        self.addCleanup(os.unlink, p)
        with open(p, "wb") as fh:
            fh.write(b"feature,priority,usage\n\xff\xfe,must,daily\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_full_mode_takes_everything_not_vendor_owned_or_dead(self):
        p = write("A,must,daily,feature,4,yes\nB,could,rarely,feature,2,yes\nC,should,unknown,feature,3,no\n"
                  "D,could,never,feature,9,yes\nE,must,daily,network,0,yes\nF,could,monthly,integration,1,yes\n")
        self.addCleanup(os.unlink, p)
        r = scope.run(scope.load(p), 1.5, "full")
        got = {x["feature"]: x["decision"] for k in ("in_scope", "out_of_scope", "hold") for x in r[k]}
        self.assertEqual(got, {"A": "IN", "B": "IN", "C": "IN", "D": "OUT", "E": "OUT", "F": "IN"})
        self.assertEqual(r["mode"], "full")
        self.assertEqual(r["counts"]["hold"], 0)
        self.assertEqual(r["effort_days_raw"], 10)

    def test_lean_is_still_the_default(self):
        p = write("B,could,rarely,feature,2,yes\n")
        self.addCleanup(os.unlink, p)
        self.assertEqual(scope.run(scope.load(p), 1.5)["out_of_scope"][0]["feature"], "B")

    def test_full_mode_annotate_works_with_unknown_usage(self):
        p = write("A,must,unknown,feature,4,no\n")
        out = p + ".m.csv"
        self.addCleanup(os.unlink, p)
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--mode", "full", "--annotate", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("MODE: full", r.stdout)
        with open(out) as fh:
            self.assertIn("A,must,unknown,feature,4,no,yes,todo", fh.read())

    def test_unwritable_outputs_are_clean_errors(self):
        p = write("A,must,daily,feature,4,yes\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--json", "/no/such/dir/o.out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "--json")
        self.assertNotIn("Traceback", r.stderr)
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), p, "--annotate", "/no/such/dir/o.out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "--annotate")
        self.assertNotIn("Traceback", r.stderr)

    def test_duplicate_column_names_are_rejected(self):
        import tempfile as _t
        fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
        fh.write("feature,priority,usage,kind,kind\nVendorContent,must,daily,content,feature\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), fh.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("duplicate column", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_row_with_the_wrong_number_of_cells_is_an_error_not_a_blank(self):
        import tempfile as _t
        for body in ("feature,priority,usage\nA,must,daily\n,,,,B,must,never,extra\n", "feature,priority,usage\nA,must,daily\n,,,,B,must,never,extra\n".replace("\\n,,,,", "\\nonly,one\\n,,,,")):
            fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
            fh.write(body.replace("\\n", "\n"))
            fh.close()
            self.addCleanup(os.unlink, fh.name)
            r = subprocess.run([sys.executable, os.path.join(HERE, "scope.py"), fh.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("different number of cells", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
