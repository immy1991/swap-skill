import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import listing  # noqa: E402

GOOD = {"store": "apple", "original_names": ["Timeloop"], "title": "Skyline Booking",
        "subtitle": "Appointments made easy", "description": "Share a link, let people book a time.",
        "keywords": "scheduling,calendar,reminders"}


def doc(**kw):
    d = dict(GOOD)
    d.update(kw)
    return d


def fails(d):
    return listing.lint(listing.load(tmp(d)))["fails"]


def warns(d):
    return listing.lint(listing.load(tmp(d)))["warns"]


def tmp(obj):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(obj, fh)
    fh.close()
    _cleanup.append(fh.name)
    return fh.name


_cleanup = []


class ListingTests(unittest.TestCase):
    def tearDown(self):
        while _cleanup:
            os.unlink(_cleanup.pop())

    def test_clean_listing_passes(self):
        rep = listing.lint(listing.load(tmp(GOOD)))
        self.assertTrue(rep["passed"])
        self.assertEqual(rep["fails"], [])

    def test_apple_limits_exact_boundaries(self):
        self.assertEqual(fails(doc(title="a" * 30, subtitle="b" * 30, keywords="k" * 100, promo_text="p" * 170)), [])
        f = fails(doc(title="a" * 31))
        self.assertTrue(any("title is 31" in x for x in f))
        self.assertTrue(any("keywords is 101" in x for x in fails(doc(keywords="k" * 101))))
        self.assertTrue(any("subtitle is 31" in x for x in fails(doc(subtitle="b" * 31))))

    def test_google_short_description_and_requirement(self):
        g = {"store": "google", "original_names": ["Timeloop"], "title": "Skyline", "description": "x"}
        self.assertTrue(any("short_description" in x and "missing" in x for x in fails(g)))
        g["short_description"] = "s" * 81
        self.assertTrue(any("short_description is 81" in x for x in fails(g)))
        g["short_description"] = "s" * 80
        self.assertEqual(fails(g), [])

    def test_web_limits_only_warn(self):
        w = {"store": "web", "original_names": ["Timeloop"], "title": "a" * 70, "description": "ok"}
        self.assertEqual(fails(w), [])
        self.assertTrue(any("title is 70" in x for x in warns(w)))

    def test_original_name_in_any_field_and_inside_words(self):
        for field in ("title", "subtitle", "description", "keywords"):
            self.assertTrue(any("original name" in x for x in fails(doc(**{field: "an alternative to Timeloop"}))), field)
        self.assertTrue(any("original name" in x for x in fails(doc(description="TimeloopSync compatible"))))
        self.assertTrue(any("original name" in x for x in fails(doc(keywords="time loop,booking"))))

    def test_ranking_claims_in_title_subtitle_short(self):
        for claim in ("#1 Booking", "Best Booking", "Top Rated Booking", "Number One Booking", "Leading Booking", "No. 1 Booking"):
            self.assertTrue(any("ranking" in x for x in fails(doc(title=claim))), claim)
        self.assertEqual(fails(doc(description="Rated best by some of our customers.")), [])

    def test_price_words_in_title_subtitle_on_stores_only(self):
        self.assertTrue(any("price or promotion" in x for x in fails(doc(title="Booking Free"))))
        self.assertTrue(any("price or promotion" in x for x in fails(doc(subtitle="50% off today"))))
        self.assertEqual(fails({"store": "web", "original_names": ["Timeloop"], "title": "Free booking page", "description": "ok"}), [])

    def test_apple_keywords_are_measured_in_utf8_bytes(self):
        ok = "k" * 100
        self.assertEqual(fails(doc(keywords=ok)), [])
        cjk = "\u5546" * 40                         # 40 characters, 120 bytes
        f = fails(doc(keywords=cjk))
        self.assertTrue(any("keywords is 120 bytes" in x for x in f), f)
        self.assertEqual(fails(doc(keywords="\u5546" * 33)), [])      # 99 bytes
        self.assertTrue(any("keywords is 102 bytes" in x for x in fails(doc(keywords="\u5546" * 34))))

    def test_google_description_fields_carry_the_same_ranking_and_price_rules(self):
        g = {"store": "google", "original_names": ["Timeloop"], "title": "Skyline", "description": "Plain text.",
             "short_description": "Simple scheduling."}
        self.assertEqual(fails(g), [])
        self.assertTrue(any("price or promotion" in x for x in fails(dict(g, short_description="Free for a limited time only, 50% off"))))
        self.assertTrue(any("ranking" in x for x in fails(dict(g, description="The #1 scheduler."))))
        self.assertTrue(any("price or promotion" in x for x in fails(dict(g, description="Now 10% off for everyone."))))
        # apple's description is not covered by these rules
        self.assertEqual(fails(doc(description="Now 10% off.")), [])

    def test_diagnostics_never_echo_text_around_the_match(self):
        p = tmp({"store": "apple", "original_names": ["Original"], "title": "Skyline", "description": "ok",
                 "subtitle": "Original API_KEY=SECRETX more"})
        out = p + ".out.json"
        r = subprocess.run([sys.executable, os.path.join(HERE, "listing.py"), p, "--json", out], capture_output=True, text=True)
        _cleanup.append(out)
        self.assertEqual(r.returncode, 1)
        with open(out) as fh:
            blob = r.stdout + r.stderr + fh.read()
        self.assertNotIn("SECRETX", blob)
        self.assertNotIn("API_KEY", blob)
        self.assertIn("at character 1", r.stdout)

    def test_a_lone_surrogate_in_keywords_is_not_a_crash(self):
        p = tmp({"store": "apple", "original_names": ["Timeloop"], "title": "Skyline", "description": "ok",
                 "keywords": "a\ud800b"})
        r = subprocess.run([sys.executable, os.path.join(HERE, "listing.py"), p], capture_output=True, text=True)
        self.assertNotIn("Traceback", r.stderr)
        self.assertIn(r.returncode, (0, 1))

    def test_percent_off_is_reported_whole(self):
        f = fails(doc(subtitle="50% off today"))
        self.assertTrue(any("'50% off'" in x for x in f), f)

    def test_official_blocks_everywhere(self):
        self.assertTrue(any("official" in x for x in fails(doc(description="The official way to book."))))

    def test_soft_warnings(self):
        self.assertTrue(any("clone" in x for x in warns(doc(description="A clone for small teams."))))

    def test_keyword_waste_warnings(self):
        w = warns(doc(keywords="scheduling, calendar,calendar,booking"))
        self.assertTrue(any("spaces around commas" in x for x in w))
        self.assertTrue(any("repeated keywords: calendar" in x for x in w))
        w2 = warns(doc(keywords="booking,calendar"))
        self.assertTrue(any("already in title" in x and "booking" in x for x in w2))

    def test_bad_input(self):
        for bad in ([], {"store": "amazon"}, {"store": "apple"}, {"store": "apple", "original_names": []},
                    {"store": "apple", "original_names": [""]}, {"store": "apple", "original_names": ["---"], "title": "x", "description": "y"},
                    {"store": "apple", "original_names": ["X"], "title": 5}, {"store": [], "original_names": ["X"]}, {"store": {"a": 1}, "original_names": ["X"]}):
            with self.assertRaises(listing.InputError, msg=str(bad)):
                listing.lint(listing.load(tmp(bad)))

    def test_cli_exit_codes(self):
        run = lambda p: subprocess.run([sys.executable, os.path.join(HERE, "listing.py"), p], capture_output=True, text=True)
        self.assertEqual(run(tmp(GOOD)).returncode, 0)
        r = run(tmp(doc(title="#1 Timeloop alternative")))
        self.assertEqual(r.returncode, 1)
        self.assertIn("FAIL", r.stdout)
        self.assertEqual(run(tmp({"store": "x"})).returncode, 2)

    def test_unwritable_outputs_are_clean_errors(self):
        p = tmp(GOOD)
        r = subprocess.run([sys.executable, os.path.join(HERE, "listing.py"), p, "--json", "/no/such/dir/o.out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "--json")
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
