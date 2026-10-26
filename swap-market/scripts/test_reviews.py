import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import reviews  # noqa: E402

HEADER = "source,url,rating,date,text\n"


def tmp(body, header=HEADER, suffix=".csv"):
    fh = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False)
    fh.write(header + body)
    fh.close()
    return fh.name


def rows(body):
    p = tmp(body)
    try:
        return reviews.load(p)
    finally:
        os.unlink(p)


class ReviewTests(unittest.TestCase):
    def run_body(self, body, max_rating=2.0, themes=None):
        return reviews.run(rows(body), max_rating, themes or reviews.DEFAULT_THEMES)

    def test_rows_without_a_link_are_dropped_and_counted(self):
        rep = self.run_body("A,,1,,Way too expensive for what it does.\nA,not-a-url,1,,Too expensive.\n"
                            "A,https://example.test/r/1,1,,Way too expensive.\n")
        self.assertEqual(rep["dropped_no_link"], 2)
        self.assertEqual(rep["reviews_used"], 1)

    def test_three_labels_on_one_site_are_one_source(self):
        body = "".join("%s,https://reviews.example.test/%d,1,,Too expensive for us number %d.\n" % (lab, i, i)
                       for i, lab in enumerate(["Site A", "Site B", "Site C"]))
        rep = self.run_body(body)
        self.assertEqual(rep["themes"][0]["sources"], 1)
        self.assertTrue(rep["themes"][0]["thin"])
        self.assertEqual(list(rep["by_source"]), ["reviews.example.test"])

    def test_distinct_hosts_count_as_distinct_sources(self):
        body = ("A,https://one.example.test/1,1,,Too expensive for us.\nB,https://www.two.example.test/2,1,,Way too expensive for us.\n"
                "C,https://three.example.test/3,1,,Far too expensive for us.\n")
        rep = self.run_body(body)
        self.assertEqual(rep["themes"][0]["sources"], 3)
        self.assertFalse(rep["themes"][0]["thin"])
        self.assertIn("two.example.test", rep["by_source"])

    def test_identical_text_under_different_links_counts_once(self):
        body = ("A,https://one.example.test/1,1,,Too expensive for us.\nB,https://two.example.test/2,1,,  too   EXPENSIVE for us. \n")
        rep = self.run_body(body)
        self.assertEqual(rep["reviews_used"], 1)
        self.assertEqual(rep["dropped_duplicates"], 1)

    def test_duplicates_dropped(self):
        rep = self.run_body("A,https://example.test/1,1,,Too expensive.\nA,https://example.test/1,1,,Too expensive.\n")
        self.assertEqual(rep["dropped_duplicates"], 1)
        self.assertEqual(rep["reviews_used"], 1)

    def test_only_negative_reviews_are_themed(self):
        rep = self.run_body("A,https://example.test/1,5,,\"Great value, not expensive.\"\n"
                            "A,https://example.test/2,1,,Far too expensive per seat.\n")
        self.assertEqual(rep["negative_reviews"], 1)
        self.assertEqual(rep["themes"][0]["theme"], "pricing")
        self.assertEqual(rep["themes"][0]["reviews"], 1)

    def test_every_quote_is_verbatim_and_linked(self):
        body = ("G2,https://example.test/a,1,,I love the layout. But the price is far too high for a small team! Support is fine.\n"
                "Store,https://example.test/b,2,,Switched away. It is expensive and the invoices are confusing.\n")
        rs = rows(body)
        rep = reviews.run(rs, 2.0, reviews.DEFAULT_THEMES)
        texts = {r["url"]: r["text"] for r in rs}
        n = 0
        for t in rep["themes"]:
            for q in t["quotes"]:
                n += 1
                self.assertIn(q["quote"], texts[q["url"]])
                self.assertTrue(q["url"].startswith("https://"))
        self.assertGreater(n, 0)

    def test_long_sentence_excerpt_keeps_the_complaint_and_marks_the_cut(self):
        text = ("Helpful " * 60) + "but expensive" + (" and helpful" * 40) + "."
        rs = rows("A,https://one.example.test/1,1,,%s\n" % text)
        rep = reviews.run(rs, 2.0, reviews.DEFAULT_THEMES)
        q = rep["themes"][0]["quotes"][0]
        self.assertIn("expensive", q["quote"])
        self.assertIn(q["quote"], text)
        self.assertTrue(q["cut"])
        self.assertLessEqual(len(q["quote"]), 260)
        out = reviews.fmt(rep)
        self.assertIn('... "', out)

    def test_short_quote_is_not_marked_cut(self):
        rep = self.run_body("A,https://one.example.test/1,1,,Too expensive.\n")
        self.assertFalse(rep["themes"][0]["quotes"][0]["cut"])

    def test_malformed_link_is_dropped_not_a_crash(self):
        rep = self.run_body("A,https://[broken.com/review,1,,Too expensive.\nB,https://ok.example.test/1,1,,Way too expensive.\n")
        self.assertEqual(rep["dropped_no_link"], 1)
        self.assertEqual(rep["reviews_used"], 1)

    def test_non_utf8_reviews_file_is_a_clean_error(self):
        p = tmp("")
        self.addCleanup(os.unlink, p)
        with open(p, "wb") as fh:
            fh.write(b"source,url,rating,text\nA,https://x.example.test/1,1,\xff\xfe bad\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_quote_is_the_matching_sentence_not_the_whole_review(self):
        rep = self.run_body("A,https://example.test/a,1,,Nice team. The price is far too high. Bye.\n")
        q = rep["themes"][0]["quotes"][0]["quote"]
        self.assertEqual(q, "The price is far too high.")

    def test_thin_flag_by_count_and_by_source(self):
        body = "".join("A,https://example.test/%d,1,,Too expensive for us %d.\n" % (i, i) for i in range(5))
        rep = self.run_body(body)
        self.assertTrue(rep["themes"][0]["thin"])            # one source only
        body += "B,https://other.example.test/x,1,,Too expensive for us too.\n"
        rep = self.run_body(body)
        self.assertFalse([t for t in rep["themes"] if t["theme"] == "pricing"][0]["thin"])
        rep2 = self.run_body("A,https://one.example.test/1,1,,Too expensive.\nB,https://two.example.test/2,1,,Way too expensive.\n")
        self.assertTrue(rep2["themes"][0]["thin"])           # fewer than 3

    def test_ranking_by_count(self):
        body = ("A,https://example.test/1,1,,Too expensive.\nB,https://example.test/2,1,,Too expensive.\n"
                "A,https://example.test/3,1,,The app keeps crashing.\n")
        rep = self.run_body(body)
        self.assertEqual([t["theme"] for t in rep["themes"]], ["pricing", "reliability"])

    def test_whole_word_matching(self):
        rep = self.run_body("A,https://example.test/1,1,,The pricelessness of it.\n")
        self.assertEqual(rep["themes"], [])
        self.assertEqual(rep["unthemed_negative"], 1)

    def test_small_sample_flag(self):
        self.assertTrue(self.run_body("A,https://example.test/1,1,,Too expensive.\n")["small_sample"])

    def test_custom_themes(self):
        p = tmp(json.dumps({"fax": ["fax machine"]}), header="", suffix=".json")
        self.addCleanup(os.unlink, p)
        th = reviews.load_themes(p)
        rep = self.run_body("A,https://example.test/1,1,,Still needs a fax machine.\n", themes=th)
        self.assertEqual(rep["themes"][0]["theme"], "fax")

    def test_bad_input(self):
        for body in ("A,https://example.test/1,six,,text\n", "A,https://example.test/1,9,,text\n",
                     "A,https://example.test/1,1,,\n"):
            p = tmp(body)
            self.addCleanup(os.unlink, p)
            with self.assertRaises(reviews.InputError, msg=body):
                reviews.load(p)
        p = tmp("A,https://example.test/1,1,text\n", header="source,url,rating,body\n")
        self.addCleanup(os.unlink, p)
        with self.assertRaises(reviews.InputError):
            reviews.load(p)
        for obj in ([], {}, {"x": []}, {"x": [""]}):
            tp = tmp(json.dumps(obj), header="", suffix=".json")
            self.addCleanup(os.unlink, tp)
            with self.assertRaises(reviews.InputError, msg=str(obj)):
                reviews.load_themes(tp)

    def test_cli(self):
        p = tmp("A,https://example.test/1,1,,Too expensive.\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), p], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("SMALL SAMPLE", r.stdout)
        self.assertIn("https://example.test/1", r.stdout)
        bad = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), p, "--max-rating", "9"],
                             capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)

    def test_unwritable_outputs_are_clean_errors(self):
        p = tmp("A,https://example.test/1,1,,Too expensive.\n")
        self.addCleanup(os.unlink, p)
        r = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), p, "--json", "/no/such/dir/o.out"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, "--json")
        self.assertNotIn("Traceback", r.stderr)

    def test_duplicate_column_names_are_rejected(self):
        import tempfile as _t
        fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
        fh.write("source,url,rating,text,text\nA,https://x.example.test/1,1,Too expensive,fine\n")
        fh.close()
        self.addCleanup(os.unlink, fh.name)
        r = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), fh.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("duplicate column", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_row_with_the_wrong_number_of_cells_is_an_error_not_a_blank(self):
        import tempfile as _t
        for body in ("source,url,rating,text\nA,https://x.example.test/1,1,Too expensive\n,,,,B,https://y.example.test/2,1,Bad\n", "source,url,rating,text\nA,https://x.example.test/1,1,Too expensive\n,,,,B,https://y.example.test/2,1,Bad\n".replace("\\n,,,,", "\\nonly,one\\n,,,,")):
            fh = _t.NamedTemporaryFile("w", suffix=".csv", delete=False)
            fh.write(body.replace("\\n", "\n"))
            fh.close()
            self.addCleanup(os.unlink, fh.name)
            r = subprocess.run([sys.executable, os.path.join(HERE, "reviews.py"), fh.name], capture_output=True, text=True)
            self.assertEqual(r.returncode, 2, r.stdout)
            self.assertIn("different number of cells", r.stderr)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
