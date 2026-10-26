import copy
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "preflight.py")
TODAY = "2026-10-26"
FEATURES_CSV = "feature,priority,in_scope,status\nA,must,yes,done\n"
FEATURES_SHA = hashlib.sha256(FEATURES_CSV.encode()).hexdigest()


def parity():
    grp = lambda n, d, p=0, g=0: {"total": n, "done": d, "partial": p, "gaps": g}
    return {"score": 100.0, "threshold": 85.0, "shippable": True, "reasons": [], "in_scope_count": 8,
            "must_gaps": [], "contradictions": [], "input_sha256": FEATURES_SHA,
            "by_priority": {"must": grp(3, 3), "should": grp(5, 5), "could": grp(0, 0)}}


def mapcheck():
    return {"passed": True, "source_rows": 10, "target_rows": 10, "key_checked": True,
            "checks": [{"check": "row count", "pass": True,
                        "detail": "source 10, deliberately not migrated 0, expected 10, target 10"}]
                      + [{"check": n, "pass": True, "detail": "ok"}
                         for n in ("keys are unique", "keys are never blank", "no source key lost", "no unexpected keys in target")]}


def roi(verdict="BUILD"):
    if verdict == "BUILD":
        base, stress = (8, 25000.0), (12, 22000.0)
    elif verdict == "MARGINAL":
        base, stress = (20, 9000.0), (30, 4000.0)
    else:
        base, stress = (None, -7000.0), (None, -12000.0)
    return {"verdict": verdict, "payback_limit_months": 18.0,
            "base": {"payback_months": base[0], "net_at_horizon": base[1], "build_total": 6000.0},
            "stress": {"payback_months": stress[0], "net_at_horizon": stress[1], "build_total": 9000.0}}


def sellmodel(verdict="SELL"):
    if verdict == "SELL":
        ue, base, stress = (25.0, 6.9), 10, 20
    elif verdict == "MARGINAL":
        ue, base, stress = (25.0, 6.9), 24, None
    else:
        ue, base, stress = (25.0, 6.9), None, None
    return {"verdict": verdict, "payback_limit_months": 24.0, "assumptions": {"price": 29.0},
            "unit_economics": {"margin_per_customer_month": ue[0], "ltv_to_cac": ue[1], "min_ltv_to_cac": 3.0},
            "base": {"payback_months": base, "net_at_horizon": 1000.0},
            "stress": {"payback_months": stress, "net_at_horizon": 500.0}}


SWEEP = {"passed": True, "files_scanned": 5, "hits": [], "skipped": []}
LISTING = {"passed": True, "store": "apple", "fails": []}
CONTRAST = {"passed": True, "results": [{"fg": "t", "bg": "b", "ratio": 16.3, "min": 4.5, "pass": True}]}
BUGS = "id,severity,status\n1,S1,fixed\n2,S2,fixed\n3,S3,open\n4,S4,accepted\n"
CUTOVER = "# Cutover\nRollback: re-enable the old tool from the kept export\nOld tool kept until: 2026-12-31\n"
DEPLOY = "Rollback: redeploy the previous release\nDomain: skyline.example.test\n"


class Base(unittest.TestCase):
    MODE = "lean"
    PLAN = ("cutover.md", CUTOVER)

    def files(self):
        raise NotImplementedError

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def build(self, skip=(), overrides=None, bugs=BUGS, plan=None, mode=None):
        files = self.files()
        files.update(overrides or {})
        for name, obj in files.items():
            if name not in skip:
                with open(os.path.join(self.d, name), "w") as fh:
                    json.dump(obj, fh)
        if "features.csv" not in skip:
            with open(os.path.join(self.d, "features.csv"), "w") as fh:
                fh.write(FEATURES_CSV)
        if "bugs.csv" not in skip:
            mode_b = "wb" if isinstance(bugs, bytes) else "w"
            with open(os.path.join(self.d, "bugs.csv"), mode_b) as fh:
                fh.write(bugs)
        pname, pbody = self.PLAN
        if pname not in skip:
            with open(os.path.join(self.d, pname), "w") as fh:
                fh.write(pbody if plan is None else plan)
        if "mode.txt" not in skip:
            with open(os.path.join(self.d, "mode.txt"), "w") as fh:
                fh.write((mode or self.MODE) + "\n")

    def go(self, *extra):
        args = [sys.executable, SCRIPT, "--dir", self.d, "--today", TODAY]
        if self.MODE != "lean":
            args += ["--mode", self.MODE]
        r = subprocess.run(args + list(extra), capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr, r.stderr)
        return r

    def assertBlocked(self, msg=None, **kw):
        self.build(**kw)
        r = self.go()
        self.assertEqual(r.returncode, 1, (msg or "") + "\n" + r.stdout)
        self.assertIn("NO-GO", r.stdout)
        return r


class PreflightLeanTests(Base):
    def files(self):
        return {"parity.json": parity(), "mapcheck.json": mapcheck(), "roi.json": roi()}

    def test_all_good_is_go(self):
        self.build()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertTrue(r.stdout.strip().endswith("GO"))

    def test_each_missing_file_is_no_go(self):
        for name in ("parity.json", "mapcheck.json", "bugs.csv", "roi.json", "cutover.md", "mode.txt", "features.csv"):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            self.assertBlocked(name, skip=(name,))

    # ---- parity
    def test_parity_contradictions_block(self):
        for label, bad in (("score 0 but shippable", dict(parity(), score=0.0)),
                           ("contradictions listed", dict(parity(), contradictions=["B: in scope but dropped"])),
                           ("eight missing must-haves but no must_gaps",
                            dict(parity(), by_priority={"must": {"total": 8, "done": 0, "partial": 0, "gaps": 8},
                                                        "should": {"total": 0, "done": 0, "partial": 0, "gaps": 0},
                                                        "could": {"total": 0, "done": 0, "partial": 0, "gaps": 0}}, in_scope_count=8)),
                           ("breakdown missing", dict(parity(), by_priority={})),
                           ("breakdown does not add up", dict(parity(), by_priority={"must": {"total": 3, "done": 1, "partial": 0, "gaps": 0},
                                                                                  "should": {"total": 5, "done": 5, "partial": 0, "gaps": 0},
                                                                                  "could": {"total": 0, "done": 0, "partial": 0, "gaps": 0}})),
                           ("in_scope_count disagrees with the breakdown", dict(parity(), in_scope_count=99)),
                           ("under its own threshold", dict(parity(), score=80.0)),
                           ("nothing in scope", dict(parity(), in_scope_count=0)),
                           ("must-have gaps listed", dict(parity(), must_gaps=["X"])),
                           ("reasons listed", dict(parity(), reasons=["contradiction"])),
                           ("score out of range", dict(parity(), score=250.0)),
                           ("score a string", dict(parity(), score="high")),
                           ("score 100 but the breakdown is worth 47.4",
                            dict(parity(), by_priority={"must": {"total": 3, "done": 3, "partial": 0, "gaps": 0},
                                                        "should": {"total": 5, "done": 0, "partial": 0, "gaps": 5},
                                                        "could": {"total": 0, "done": 0, "partial": 0, "gaps": 0}})),
                           ("not shippable", dict(parity(), shippable=False, reasons=["must-have not done: X"]))):
            self.assertBlocked(label, overrides={"parity.json": bad})

    def test_stale_parity_is_a_no_go_even_though_the_old_report_was_genuine(self):
        self.build()
        self.assertEqual(self.go().returncode, 0)
        with open(os.path.join(self.d, "features.csv"), "w") as fh:
            fh.write("feature,priority,in_scope,status\nA,must,yes,missing\n")       # the work was undone after parity ran
        r = self.go()
        self.assertEqual(r.returncode, 1)
        self.assertIn("features.csv has changed since parity was run", r.stdout)
        os.remove(os.path.join(self.d, "features.csv"))
        r = self.go()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no way to tell", r.stdout)

    def test_a_parity_report_with_no_input_hash_is_refused(self):
        bad = parity()
        del bad["input_sha256"]
        self.assertBlocked(overrides={"parity.json": bad})

    def test_truthy_strings_do_not_count_as_true(self):
        self.assertBlocked(overrides={"parity.json": dict(parity(), shippable="yes")})
        self.assertBlocked(overrides={"mapcheck.json": dict(mapcheck(), passed="true")})

    # ---- migration
    def test_migration_contradictions_block(self):
        failed_inside = mapcheck()
        failed_inside["checks"][2]["pass"] = False
        for label, bad in (("no key", dict(mapcheck(), key_checked=False)),
                           ("zero target rows", dict(mapcheck(), target_rows=0)),
                           ("zero source rows", dict(mapcheck(), source_rows=0, target_rows=0)),
                           ("failed check inside a passed run", failed_inside),
                           ("no checks at all", dict(mapcheck(), checks=[])),
                           ("row totals disagree with the row-count check", dict(mapcheck(), source_rows=100, target_rows=1)),
                           ("row-count check says pass with target 1 of expected 10",
                            dict(mapcheck(), target_rows=1, checks=[{"check": "row count", "pass": True,
                                 "detail": "source 10, deliberately not migrated 0, expected 10, target 1"}])),
                           ("expected is not source minus drops",
                            dict(mapcheck(), checks=[{"check": "row count", "pass": True,
                                 "detail": "source 10, deliberately not migrated 0, expected 3, target 3"}], target_rows=3)),
                           ("no row-count check", dict(mapcheck(), checks=[c for c in mapcheck()["checks"] if c["check"] != "row count"])),
                           ("only the row count: no key checks at all",
                            dict(mapcheck(), checks=[mapcheck()["checks"][0]])),
                           ("key-lost check missing", dict(mapcheck(), checks=[c for c in mapcheck()["checks"] if c["check"] != "no source key lost"])),
                           ("malformed checks", dict(mapcheck(), checks=["ok"])),
                           ("not passed", dict(mapcheck(), passed=False))):
            self.assertBlocked(label, overrides={"mapcheck.json": bad})

    # ---- stubs and types
    def test_hand_typed_stubs_do_not_pass(self):
        r = self.assertBlocked(overrides={"parity.json": {"shippable": True}, "mapcheck.json": {"passed": True},
                                          "roi.json": {"verdict": "BUILD"}})
        self.assertIn("missing field", r.stdout)

    def test_empty_financial_scenarios_do_not_pass(self):
        self.assertBlocked(overrides={"roi.json": {"verdict": "BUILD", "base": {}, "stress": {}, "payback_limit_months": 18.0}})

    # ---- economics
    def test_roi_verdict_must_follow_its_numbers(self):
        liar = roi("KEEP SAAS")
        liar["verdict"] = "BUILD"                     # numbers say KEEP SAAS
        self.assertBlocked("BUILD with no payback", overrides={"roi.json": liar})
        under = roi("BUILD")
        under["verdict"] = "KEEP SAAS"                # numbers say BUILD
        self.assertBlocked("KEEP SAAS despite numbers", overrides={"roi.json": under})

    def test_roi_nonsense_numbers_block_without_a_traceback(self):
        for label, mut in (("negative payback", lambda r: r["base"].update(payback_months=-12)),
                           ("boolean payback", lambda r: r["stress"].update(payback_months=True)),
                           ("string payback", lambda r: r["stress"].update(payback_months="8")),
                           ("payback beyond 100 years", lambda r: r["base"].update(payback_months=99999)),
                           ("zero limit", lambda r: r.update(payback_limit_months=0.0)),
                           ("negative build", lambda r: r["base"].update(build_total=-5.0))):
            bad = roi()
            mut(bad)
            self.assertBlocked(label, overrides={"roi.json": bad})

    def test_huge_integers_are_a_clean_no_go(self):
        bad = sellmodel()
        bad["unit_economics"]["ltv_to_cac"] = 10 ** 400
        self.assertBlocked("huge int", overrides={"roi.json": dict(roi(), payback_limit_months=10 ** 400)})

    def test_roi_keep_saas_blocks(self):
        self.assertBlocked(overrides={"roi.json": roi("KEEP SAAS")})

    def test_marginal_needs_the_owners_recorded_choice(self):
        r = self.assertBlocked(overrides={"roi.json": roi("MARGINAL")})
        self.assertIn("Marginal approved by", r.stdout)
        self.build(overrides={"roi.json": roi("MARGINAL")}, plan=CUTOVER + "Marginal approved by: A. Owner on 2026-10-25\n")
        self.assertEqual(self.go().returncode, 0)
        self.assertBlocked(overrides={"roi.json": roi("MARGINAL")}, plan=CUTOVER + "Marginal approved by:\n")

    # ---- bug log
    def test_open_s2_blocks_and_accepted_s1_cannot_pass(self):
        r = self.assertBlocked(bugs="id,severity,status\n7,S2,open\n")
        self.assertIn("7 (S2, open)", r.stdout)
        self.assertBlocked(bugs="id,severity,status\n8,S1,accepted\n")

    def test_empty_bug_log_with_header_is_fine(self):
        self.build(bugs="id,severity,status\n")
        self.assertEqual(self.go().returncode, 0)

    def test_malformed_bug_logs_block(self):
        for label, body in (("bad severity", "id,severity,status\n1,S9,open\n"),
                            ("bad status", "id,severity,status\n1,S3,pending\n"),
                            ("missing column", "id,sev,status\n1,S3,open\n"),
                            ("duplicate header hides an open S1", "id,severity,status,status\nB1,S1,open,fixed\n"),
                            ("ragged row", "id,severity,status\nB1,S1\n"),
                            ("extra cells", "id,severity,status\nB1,S1,fixed,extra\n"),
                            ("not utf-8", b"id,severity,status\n\xff\xfe,S1,fixed\n"),
                            ("empty file", "")):
            self.assertBlocked(label, bugs=body)

    # ---- plan file
    def test_cutover_needs_rollback_and_a_future_date(self):
        for label, body in (("empty rollback", "Rollback:\nOld tool kept until: 2026-12-31\n"),
                            ("no date", "Rollback: yes\n"), ("not a date", "Rollback: yes\nOld tool kept until: soon\n"),
                            ("impossible date", "Rollback: yes\nOld tool kept until: 2026-13-45\n"),
                            ("date in 2000", "Rollback: yes\nOld tool kept until: 2000-01-01\n"),
                            ("date yesterday", "Rollback: yes\nOld tool kept until: 2026-10-25\n")):
            self.assertBlocked(label, plan=body)
        self.build(plan="Rollback: yes\nOld tool kept until: %s\n" % TODAY)       # today is allowed
        self.assertEqual(self.go().returncode, 0)

    # ---- contrast
    def test_contrast_checked_only_when_present_and_consistent(self):
        self.build()
        os.makedirs(os.path.join(self.d, "design"))
        ok = {"fg": "t", "bg": "b", "ratio": 16.3, "min": 4.5, "pass": True}
        bad = {"fg": "t", "bg": "b", "ratio": 2.0, "min": 4.5, "pass": False}
        for label, obj in (("failed", {"passed": False, "results": [bad]}),
                           ("passed with a failing pair", {"passed": True, "results": [ok, bad]}),
                           ("ratio 1 against minimum 4.5 but pass true", {"passed": True, "results": [dict(ok, ratio=1.0)]}),
                           ("impossible ratio", {"passed": True, "results": [dict(ok, ratio=500.0)]}),
                           ("passed with no results", {"passed": True, "results": []}),
                           ("missing ratio", {"passed": True, "results": [{"pass": True}]})):
            with open(os.path.join(self.d, "design", "contrast.json"), "w") as fh:
                json.dump(obj, fh)
            self.assertEqual(self.go().returncode, 1, label)

    def test_malformed_json_is_no_go_not_crash(self):
        self.build()
        for payload in (b"{not json", b"\xff\xfe\x00", b"[]", b""):
            with open(os.path.join(self.d, "parity.json"), "wb") as fh:
                fh.write(payload)
            r = self.go()
            self.assertEqual(r.returncode, 1, payload)

    def test_non_utf8_mode_and_plan_files_are_clean_failures(self):
        self.build()
        with open(os.path.join(self.d, "mode.txt"), "wb") as fh:
            fh.write(b"\xff\xfe")
        self.assertEqual(self.go().returncode, 1)
        self.build()
        with open(os.path.join(self.d, "cutover.md"), "wb") as fh:
            fh.write(b"\xff\xfe\x00")
        self.assertEqual(self.go().returncode, 1)

    def test_mode_must_match_the_track(self):
        r = self.assertBlocked(mode="full")
        self.assertIn("mode.txt says 'full'", r.stdout)

    def test_renewal_guard(self):
        self.build()
        r = self.go("--renewal", "2027-03-01", "--notice-days", "60")
        self.assertIn("Last day to cancel without another term: 2026-12-31", r.stdout)
        self.assertNotIn("WARN", r.stdout)
        r = self.go("--renewal", "2026-11-30", "--notice-days", "60")
        self.assertIn("has passed", r.stdout)
        self.assertEqual(r.returncode, 0)
        r = self.go("--renewal", "2026-12-10", "--notice-days", "30")
        self.assertIn("day(s) away", r.stdout)
        self.assertIn("cancel-by date unknown", self.go().stdout)

    def test_bad_args_including_hostile_notice_periods(self):
        self.build()
        for args in (["--renewal", "2027-03-01"], ["--renewal", "nope", "--notice-days", "5"],
                     ["--renewal", "2027-03-01", "--notice-days", "-5"],
                     ["--renewal", "2027-03-01", "--notice-days", "99999999999"],
                     ["--renewal", "2027-03-01", "--notice-days", "3651"],
                     ["--renewal", "0001-01-05", "--notice-days", "3650"]):
            self.assertEqual(self.go(*args).returncode, 2, args)
        r = subprocess.run([sys.executable, SCRIPT, "--dir", "/no/such/dir"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)

    def test_unwritable_json_path_is_a_clean_error(self):
        self.build()
        self.assertEqual(self.go("--json", "/no/such/dir/pf.json").returncode, 2)

    def test_json_output_keeps_cancel_by(self):
        self.build()
        out = os.path.join(self.d, "pf.json")
        self.go("--renewal", "2027-03-01", "--notice-days", "60", "--json", out)
        with open(out) as fh:
            d = json.load(fh)
        self.assertTrue(d["go"])
        self.assertEqual(d["cancel_by"], "2026-12-31")
        self.assertEqual(d["mode"], "lean")


class PreflightFullTests(Base):
    MODE = "full"
    PLAN = ("deploy.md", DEPLOY)

    def files(self):
        return {"parity.json": parity(), "sellmodel.json": sellmodel(), "sweep.json": copy.deepcopy(SWEEP),
                "listing.json": copy.deepcopy(LISTING)}

    def test_all_good_is_go_with_no_migration_or_renewal_checks(self):
        self.build()
        r = self.go()
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertNotIn("migration", r.stdout)
        self.assertNotIn("cancel", r.stdout.lower())

    def test_each_missing_file_blocks(self):
        for name in ("parity.json", "bugs.csv", "sellmodel.json", "sweep.json", "listing.json", "deploy.md", "mode.txt", "features.csv"):
            shutil.rmtree(self.d)
            os.makedirs(self.d)
            self.assertBlocked(name, skip=(name,))

    def test_sweep_contradictions_block(self):
        for label, bad in (("hits", dict(SWEEP, passed=False, hits=[{"file": "a.js"}])),
                           ("passed with hits", dict(SWEEP, hits=[{"file": "a.js"}])),
                           ("nothing scanned", dict(SWEEP, files_scanned=0)),
                           ("unscanned and not accepted", dict(SWEEP, skipped=["logo.png (binary)"])),
                           ("unscanned, passed, not accepted", dict(SWEEP, passed=True, skipped=["x (binary)"], skipped_accepted=False))):
            self.assertBlocked(label, overrides={"sweep.json": bad})
        self.build(overrides={"sweep.json": dict(SWEEP, skipped=["logo.png (binary)"], skipped_accepted=True)})
        self.assertEqual(self.go().returncode, 0)

    def test_listing_contradictions_block(self):
        for label, bad in (("failed", dict(LISTING, passed=False, fails=["x"])),
                           ("passed with fails", dict(LISTING, fails=["x"])),
                           ("invented store", dict(LISTING, store="amazon")),
                           ("store a list", dict(LISTING, store=[]))):
            self.assertBlocked(label, overrides={"listing.json": bad})

    def test_sell_verdict_must_follow_its_numbers(self):
        liar = sellmodel("DON'T SELL")
        liar["verdict"] = "SELL"
        self.assertBlocked("SELL with no payback", overrides={"sellmodel.json": liar})
        no_margin = sellmodel("SELL")
        no_margin["unit_economics"]["margin_per_customer_month"] = -2.0
        self.assertBlocked("SELL with no margin", overrides={"sellmodel.json": no_margin})
        self.assertBlocked("empty scenarios", overrides={"sellmodel.json": {"verdict": "SELL", "unit_economics": {}, "base": {},
                                                                              "stress": {}, "payback_limit_months": 24.0,
                                                                              "assumptions": {"price": 1}}})
        self.assertBlocked("no assumptions", overrides={"sellmodel.json": dict(sellmodel(), assumptions={})})

    def test_sell_nonsense_numbers_block_without_a_traceback(self):
        for label, mut in (("negative payback", lambda r: r["base"].update(payback_months=-12)),
                           ("boolean payback", lambda r: r["base"].update(payback_months=True)),
                           ("infinite ltv:cac", lambda r: r["unit_economics"].update(ltv_to_cac=float("inf"))),
                           ("string ltv:cac", lambda r: r["unit_economics"].update(ltv_to_cac="high")),
                           ("negative ltv:cac", lambda r: r["unit_economics"].update(ltv_to_cac=-3.0)),
                           ("limit out of range", lambda r: r.update(payback_limit_months=99999.0))):
            bad = sellmodel()
            mut(bad)
            self.assertBlocked(label, overrides={"sellmodel.json": bad})

    def test_huge_integer_ltv_is_a_clean_no_go(self):
        bad = sellmodel()
        bad["unit_economics"]["ltv_to_cac"] = 10 ** 400
        self.assertBlocked("huge int", overrides={"sellmodel.json": bad})

    def test_ltv_to_cac_just_under_the_line_is_not_sell(self):
        bad = sellmodel("SELL")
        bad["unit_economics"]["ltv_to_cac"] = 2.999
        self.assertBlocked("2.999 against a line of 3", overrides={"sellmodel.json": bad})
        ok = sellmodel("SELL")
        ok["unit_economics"]["ltv_to_cac"] = 3.0
        self.build(overrides={"sellmodel.json": ok})
        self.assertEqual(self.go().returncode, 0)

    def test_dont_sell_blocks(self):
        self.assertBlocked(overrides={"sellmodel.json": sellmodel("DON'T SELL")})

    def test_marginal_needs_the_owners_recorded_choice(self):
        r = self.assertBlocked(overrides={"sellmodel.json": sellmodel("MARGINAL")})
        self.assertIn("Marginal approved by", r.stdout)
        self.build(overrides={"sellmodel.json": sellmodel("MARGINAL")}, plan=DEPLOY + "Marginal approved by: A. Owner\n")
        self.assertEqual(self.go().returncode, 0)

    def test_stubs_do_not_pass(self):
        r = self.assertBlocked(overrides={"sweep.json": {"passed": True}, "listing.json": {"passed": True},
                                          "sellmodel.json": {"verdict": "SELL"}, "parity.json": {"shippable": True}})
        self.assertIn("missing field", r.stdout)

    def test_open_s2_blocks(self):
        self.assertBlocked(bugs="id,severity,status\n1,S2,open\n")

    def test_deploy_plan_needs_rollback_and_domain(self):
        for body in ("Rollback:\nDomain: a.example.test\n", "Rollback: yes\nDomain:\n", "Rollback: yes\n", "Domain: a.example.test\n"):
            self.assertBlocked(body, plan=body)

    def test_lean_evidence_does_not_satisfy_full_mode(self):
        self.assertBlocked(skip=("sellmodel.json",), overrides={"roi.json": roi()})

    def test_mode_must_match_the_track(self):
        r = self.assertBlocked(mode="lean")
        self.assertIn("mode.txt says 'lean'", r.stdout)

    def test_full_json_marks_mode(self):
        self.build()
        out = os.path.join(self.d, "pf.json")
        self.go("--json", out)
        with open(out) as fh:
            self.assertEqual(json.load(fh)["mode"], "full")

    def test_unwritable_json_path_is_a_clean_error(self):
        self.build()
        self.assertEqual(self.go("--json", "/no/such/dir/pf.json").returncode, 2)


if __name__ == "__main__":
    unittest.main()
