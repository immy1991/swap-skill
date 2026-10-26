import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import mapcheck  # noqa: E402

MAPPING = (
    "source_field,target_field,action,required,check\n"
    "id,id,map,yes,\n"
    "Email,email,map,yes,\n"
    "Phone,phone,map,no,\n"
    "Full Name,name,derive,yes,\n"
    "Amount,amount,map,no,sum\n"
    "Legacy Flag,,drop,no,\n"
)
SRC = (
    "id,Email,Phone,Full Name,Amount,Legacy Flag\n"
    "1,a@example.test,111,Ann Lee,10.50,x\n"
    "2,b@example.test,,Bob Ray,20.00,\n"
    "3,c@example.test,333,Cy Poe,5.25,y\n"
)
TGT = (
    "id,email,phone,name,amount\n"
    "1,a@example.test,111,Ann Lee,10.50\n"
    "2,b@example.test,,Bob Ray,20.00\n"
    "3,c@example.test,333,Cy Poe,5.25\n"
)


def tmp(text, suffix=".csv"):
    fh = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, newline="")
    fh.write(text)
    fh.close()
    return fh.name


class MapcheckTests(unittest.TestCase):
    def go(self, mapping=MAPPING, src=SRC, tgt=TGT, key="id", allow=0):
        paths = [tmp(mapping), tmp(src), tmp(tgt)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        m = mapcheck.load_mapping(paths[0])
        sh, sr, sl = mapcheck.read_csv(paths[1], "source")
        th, tr, tl = mapcheck.read_csv(paths[2], "target")
        checks, ran = mapcheck.run(m, sh, sr, th, tr, key, allow, sl, tl)
        return checks, ran

    def failed(self, checks):
        return [c["check"] for c in checks if not c["pass"]]

    def test_clean_migration_passes_everything(self):
        checks, ran = self.go()
        self.assertTrue(ran)
        self.assertEqual(self.failed(checks), [])

    def test_lost_row_detected(self):
        tgt = TGT.replace("3,c@example.test,333,Cy Poe,5.25\n", "")
        f = self.failed(self.go(tgt=tgt)[0])
        self.assertIn("row count", f)
        self.assertIn("no source key lost", f)
        self.assertIn("total matches: Amount -> amount", f)

    def test_value_silently_changed_detected(self):
        f = self.failed(self.go(tgt=TGT.replace("a@example.test", "z@example.test"))[0])
        self.assertIn("values unchanged: Email -> email", f)
        self.assertNotIn("no value lost: Email -> email", f)

    def test_value_lost_detected(self):
        f = self.failed(self.go(tgt=TGT.replace("3,c@example.test,333", "3,c@example.test,"))[0])
        self.assertIn("no value lost: Phone -> phone", f)

    def test_derive_allows_change_but_not_loss(self):
        ok = self.failed(self.go(tgt=TGT.replace("Ann Lee", '"Lee, Ann"'))[0])
        self.assertEqual(ok, [])
        lost = self.failed(self.go(tgt=TGT.replace("Cy Poe", ""))[0])
        self.assertIn("no value lost: Full Name -> name", lost)
        self.assertIn("required field filled: name", lost)

    def test_text_identifiers_are_compared_as_text_by_default(self):
        mapping = MAPPING + "Postcode,postcode,map,no,\n"
        src = ("id,Email,Phone,Full Name,Amount,Legacy Flag,Postcode\n"
               "1,a@example.test,111,Ann Lee,10.50,x,01234\n2,b@example.test,,Bob Ray,20.00,,00501\n")
        tgt_bad = ("id,email,phone,name,amount,postcode\n"
                   "1,a@example.test,111,Ann Lee,10.50,1234\n2,b@example.test,,Bob Ray,20.00,00501\n")
        checks, _ = self.go(mapping=mapping, src=src, tgt=tgt_bad)
        self.assertIn("values unchanged: Postcode -> postcode", self.failed(checks))
        # an explicit compare=number opts the column in to numeric equality
        mapping_num = mapping.replace("Postcode,postcode,map,no,\n", "Postcode,postcode,map,no,,number\n").replace(
            "source_field,target_field,action,required,check\n", "source_field,target_field,action,required,check,compare\n")
        mapping_num = "\n".join(ln if i == 0 or ln.count(",") >= 5 else ln + "," for i, ln in enumerate(mapping_num.splitlines())) + "\n"
        checks, _ = self.go(mapping=mapping_num, src=src, tgt=tgt_bad)
        self.assertNotIn("values unchanged: Postcode -> postcode", self.failed(checks))

    def test_bad_compare_value_is_rejected(self):
        p = tmp("source_field,target_field,action,compare\na,x,map,fuzzy\n")
        self.addCleanup(os.unlink, p)
        with self.assertRaises(mapcheck.InputError):
            mapcheck.load_mapping(p)

    def test_large_numbers_are_compared_exactly(self):
        src = SRC.replace("10.50", "9007199254740992")
        tgt = TGT.replace("10.50", "9007199254740993")
        f = self.failed(self.go(src=src, tgt=tgt)[0])
        self.assertIn("values unchanged: Amount -> amount", f)
        self.assertIn("total matches: Amount -> amount", f)
        same = self.failed(self.go(src=src, tgt=TGT.replace("10.50", "9007199254740992"))[0])
        self.assertEqual(same, [])

    def test_sums_are_exact_beyond_decimal_default_precision(self):
        src = SRC.replace("10.50", "10000000000000000000000000000").replace("20.00", "1").replace("5.25", "0")
        tgt = TGT.replace("10.50", "10000000000000000000000000000").replace("20.00", "2").replace("5.25", "0")
        f = self.failed(self.go(src=src, tgt=tgt)[0])
        self.assertIn("total matches: Amount -> amount", f)

    def test_absurd_exponents_are_not_numbers_and_do_not_crash(self):
        src = SRC.replace("10.50", "1e1000000")
        tgt = TGT.replace("10.50", "1e1000000")
        checks, _ = self.go(src=src, tgt=tgt)                  # identical text still matches as text
        self.assertNotIn("values unchanged: Amount -> amount", self.failed(checks))
        checks, _ = self.go(src=src, tgt=TGT.replace("10.50", "2e1000000"))
        self.assertIn("values unchanged: Amount -> amount", self.failed(checks))

    def test_amounts_are_never_printed(self):
        paths = [tmp(MAPPING), tmp("id,Email,Phone,Full Name,Amount,Legacy Flag\n1,a@example.test,,X,987654.32,\n"),
                 tmp("id,email,phone,name,amount\n1,a@example.test,,X,987654.32\n")]
        for p in paths:
            self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id", "--json", paths[0] + ".j"], capture_output=True, text=True)
        self.addCleanup(lambda: os.path.exists(paths[0] + ".j") and os.unlink(paths[0] + ".j"))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("987654", r.stdout)
        with open(paths[0] + ".j") as fh:
            self.assertNotIn("987654", fh.read())
        self.assertIn("totals agree", r.stdout)

    def test_non_finite_numbers_never_compare_equal_by_value(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            f = self.failed(self.go(src=SRC.replace("10.50", token), tgt=TGT.replace("10.50", "10.50"))[0])
            self.assertIn("values unchanged: Amount -> amount", f, token)

    def test_numbers_compare_as_numbers(self):
        self.assertEqual(self.failed(self.go(tgt=TGT.replace("10.50", "10.5"))[0]), [])

    def test_a_headerless_export_never_prints_its_first_row(self):
        src = "CUST-8841,jane.invented@example.test,07700 900123,Jane Invented,99.50,x\n2,b@example.test,,Bob Ray,20.00,\n"
        tgt = "id,email,phone,name,amount\n2,b@example.test,,Bob Ray,20.00\n"
        paths = [tmp(MAPPING), tmp(src), tmp(tgt)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        out = paths[0] + ".j"
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id", "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        with open(out) as fh:
            blob = r.stdout + r.stderr + fh.read()
        for secret in ("CUST-8841", "jane.invented", "07700", "Jane Invented", "99.50"):
            self.assertNotIn(secret, blob)
        self.assertIn("position(s)", r.stdout)

    def test_a_wrong_file_given_as_the_mapping_never_echoes_its_cells(self):
        secret = "CUSTOMER-SECRET-77@example.test"
        for body in ("source_field,target_field,action\n%s,x,teleport\n" % secret,
                     "source_field,target_field,action\na,%s,drop\n" % secret,
                     "source_field,target_field,action\n%s,t,map\n%s,t2,map\n" % (secret, secret),
                     "source_field,target_field,action\na,%s,map\nb,%s,map\n" % (secret, secret),
                     "source_field,target_field,action,required\na,x,map,%s\n" % secret,
                     "source_field,target_field,action,compare\na,x,map,%s\n" % secret,
                     "source_field,target_field,action,check\na,x,map,%s\n" % secret):
            p = tmp(body)
            self.addCleanup(os.unlink, p)
            r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), p, "--source", p, "--target", p],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, body)
            self.assertNotIn("SECRET", r.stdout + r.stderr, body)
            self.assertIn("mapping line", r.stderr, body)

    def test_line_numbers_are_physical_lines_even_after_multiline_records(self):
        src = ('id,Email,Phone,Full Name,Amount,Legacy Flag\n'
               '1,a@example.test,111,"Ann\nLee",10.50,x\n'
               '2,b@example.test,,Bob Ray,20.00,\n'
               '3,c@example.test,333,Cy Poe,5.25,y\n')
        tgt = TGT.replace("2,b@example.test,,Bob Ray,20.00\n", "2,zz@example.test,,Bob Ray,20.00\n").replace("Ann Lee", "Ann\nLee").replace(
            "1,a@example.test,111,Ann\nLee,10.50", '1,a@example.test,111,"Ann\nLee",10.50')
        paths = [tmp(MAPPING), tmp(src), tmp(tgt)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1], "--target", paths[2],
                            "--key", "id"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stdout)
        # record 2 begins on physical line 4 of the source (the first record spans lines 2-3)
        self.assertIn("first at source lines: 4", r.stdout)

    def test_empty_exports_do_not_pass(self):
        checks, _ = self.go(src="id,Email,Phone,Full Name,Amount,Legacy Flag\n", tgt="id,email,phone,name,amount\n")
        self.assertIn("the exports contain rows", self.failed(checks))
        paths = [tmp(MAPPING), tmp("id,Email,Phone,Full Name,Amount,Legacy Flag\n"), tmp("id,email,phone,name,amount\n")]
        for p in paths:
            self.addCleanup(os.unlink, p)
        out = paths[0] + ".j"
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id", "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        import json as _j
        with open(out) as fh:
            self.assertFalse(_j.load(fh)["passed"])

    def test_unmapped_column_is_reported(self):
        src = "id,Email,Phone,Full Name,Amount,Legacy Flag,Surprise\n1,a@example.test,111,Ann Lee,10.50,x,q\n"
        tgt = "id,email,phone,name,amount\n1,a@example.test,111,Ann Lee,10.50\n"
        checks, ran = self.go(src=src, tgt=tgt)
        self.assertFalse(ran)
        self.assertIn("every source column is in the mapping", self.failed(checks))
        self.assertNotIn("Surprise", " ".join(c["detail"] for c in checks))

    def test_missing_target_column(self):
        tgt = "id,email,name,amount\n1,a@example.test,Ann Lee,10.50\n2,b@example.test,Bob Ray,20.00\n3,c@example.test,Cy Poe,5.25\n"
        checks, ran = self.go(tgt=tgt)
        self.assertFalse(ran)
        self.assertIn("every target field exists in the new export", self.failed(checks))

    def test_duplicate_and_extra_keys(self):
        tgt = TGT + "3,c@example.test,333,Cy Poe,0\n9,q@example.test,,Q Q,0\n"
        f = self.failed(self.go(tgt=tgt)[0])
        self.assertIn("keys are unique", f)
        self.assertIn("no unexpected keys in target", f)
        self.assertIn("row count", f)

    def test_allowed_drops_do_not_fail_counts_or_sums(self):
        tgt = "id,email,phone,name,amount\n1,a@example.test,111,Ann Lee,10.50\n2,b@example.test,,Bob Ray,20.00\n"
        checks, _ = self.go(tgt=tgt, allow=1)
        self.assertEqual(self.failed(checks), [])

    def test_more_drops_than_allowed_fails(self):
        tgt = "id,email,phone,name,amount\n1,a@example.test,111,Ann Lee,10.50\n"
        f = self.failed(self.go(tgt=tgt, allow=1)[0])
        self.assertIn("row count", f)
        self.assertIn("no source key lost beyond the allowed drops", f)

    def test_no_key_is_a_failure_not_a_skip(self):
        checks, _ = self.go(key=None)
        self.assertIn("rows can be matched by a unique key", self.failed(checks))

    def test_no_key_cannot_certify_completely_different_data(self):
        # same counts, same blanks, but every id, email and name is different
        other = TGT.replace("a@example.test", "zz1@example.test").replace("b@example.test", "zz2@example.test") \
                   .replace("c@example.test", "zz3@example.test").replace("Ann Lee", "Q").replace("Bob Ray", "R").replace("Cy Poe", "S")
        other = other.replace("1,zz1", "91,zz1").replace("2,zz2", "92,zz2").replace("3,zz3", "93,zz3")
        for key in (None, "id"):
            checks, _ = self.go(tgt=other, key=key)
            self.assertTrue(self.failed(checks), key)

    def test_cli_json_never_passes_without_a_key(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        out = paths[0] + ".json"
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        import json as _j
        with open(out) as fh:
            d = _j.load(fh)
        self.assertFalse(d["passed"])
        self.assertFalse(d["key_checked"])

    def test_cli_json_with_key_records_key_checked(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        out = paths[0] + ".json"
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id", "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        import json as _j
        with open(out) as fh:
            d = _j.load(fh)
        self.assertTrue(d["passed"] and d["key_checked"])

    def test_unwritable_json_path_is_a_clean_error(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id", "--json", "/no/such/dir/out.json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_keys_and_values_are_never_printed_only_line_numbers(self):
        src = SRC.replace("1,a@example.test", "CUSTOMER-SECRET-1,a@example.test")
        tgt = TGT.replace("1,a@example.test", "CUSTOMER-SECRET-9,q@example.test")
        paths = [tmp(MAPPING), tmp(src), tmp(tgt)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        for secret in ("CUSTOMER-SECRET-1", "CUSTOMER-SECRET-9", "a@example.test", "q@example.test"):
            self.assertNotIn(secret, r.stdout + r.stderr)
        self.assertIn("source lines: 2", r.stdout)
        self.assertIn("target lines: 2", r.stdout)

    def test_output_never_contains_field_values(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT.replace("a@example.test", "z@example.test"))]
        for p in paths:
            self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        for secret in ("a@example.test", "z@example.test", "Ann Lee"):
            self.assertNotIn(secret, r.stdout)

    def test_bad_mapping_rejected(self):
        bad = [
            "source_field,target_field,action\nid,id,copy\n",
            "source_field,target_field,action\nid,id,map\nid,id2,map\n",
            "source_field,target_field,action\na,x,map\nb,x,map\n",
            "source_field,target_field,action\na,,map\n",
            "source_field,target_field,action\na,x,drop\n",
            "source_field,target_field,action,required\na,x,map,maybe\n",
            "source_field,target_field,action,check\na,,drop,sum\n",
            "source_field,target_field,action\n",
            "target_field,action\nx,map\n",
        ]
        for body in bad:
            p = tmp(body)
            self.addCleanup(os.unlink, p)
            with self.assertRaises(mapcheck.InputError, msg=body):
                mapcheck.load_mapping(p)

    def test_non_utf8_input_is_a_clean_error(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        with open(paths[1], "wb") as fh:
            fh.write(b"id,Email\n\xff\xfe,a\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1],
                            "--target", paths[2], "--key", "id"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_ragged_and_duplicate_header_rejected(self):
        for body in ("a,b\n1\n", "a,a\n1,2\n", ""):
            p = tmp(body)
            self.addCleanup(os.unlink, p)
            with self.assertRaises(mapcheck.InputError, msg=body):
                mapcheck.read_csv(p, "source")

    def test_cli_exit_codes(self):
        paths = [tmp(MAPPING), tmp(SRC), tmp(TGT)]
        for p in paths:
            self.addCleanup(os.unlink, p)
        base = [sys.executable, os.path.join(HERE, "mapcheck.py"), paths[0], "--source", paths[1], "--target", paths[2]]
        self.assertEqual(subprocess.run(base + ["--key", "id"], capture_output=True, text=True).returncode, 0)
        self.assertEqual(subprocess.run(base, capture_output=True, text=True).returncode, 1)
        self.assertEqual(subprocess.run(base + ["--allow-dropped-rows", "-1"], capture_output=True, text=True).returncode, 2)
        self.assertEqual(subprocess.run([sys.executable, os.path.join(HERE, "mapcheck.py"), "/none.csv",
                                         "--source", paths[1], "--target", paths[2]], capture_output=True, text=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
