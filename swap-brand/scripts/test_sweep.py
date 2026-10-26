import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import sweep  # noqa: E402


class SweepTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d)

    def put(self, rel, text, mode="w"):
        p = os.path.join(self.d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, mode) as fh:
            fh.write(text)
        return p

    def hits(self, names=(), domains=(), colours=(), allow=(), excludes=()):
        return sweep.sweep(self.d, list(names), list(domains), list(colours), list(allow), list(excludes))

    def test_name_variants_and_identifiers(self):
        self.put("a.js", "const OriginalAppEmbed = 1;\n// original_app\nlet x = 'original-app';\nORIGINAL.APP\nOriginal App\n")
        h, _, _ = self.hits(names=["Original App"])
        self.assertEqual(sorted(x["line"] for x in h), [1, 2, 3, 4, 5])

    def test_single_word_name_split_by_a_separator_is_caught(self):
        self.put("a.py", "def time_loop_client():\n    pass\n")
        h, _, _ = self.hits(names=["Timeloop"])
        self.assertEqual([x["line"] for x in h], [1])

    def test_clean_tree_is_clean(self):
        self.put("a.js", "const Skyline = 1;\n")
        h, _, scanned = self.hits(names=["Original App"], domains=["originalapp.com"], colours=["#112233"])
        self.assertEqual(h, [])
        self.assertEqual(scanned, 1)

    def test_domain_with_and_without_www(self):
        self.put("a.html", '<a href="https://www.originalapp.com/x">a</a>\nOriginalApp.com\n')
        h, _, _ = self.hits(domains=["originalapp.com"])
        self.assertEqual(len(h), 2)

    def test_colour_hex_short_long_and_rgb(self):
        self.put("a.css", "a{color:#112233}\nb{color:#123}\nc{color:rgb(17, 34, 51)}\nd{color:rgba(17,34,51,.5)}\ne{color:#11223344}\n")
        h, _, _ = self.hits(colours=["#112233"])
        self.assertEqual(sorted(x["line"] for x in h), [1, 2, 3, 4, 5])  # #123 is #112233; #11223344 is it with alpha
        h2, _, _ = self.hits(colours=["#aabbcc"])
        self.assertEqual(h2, [])
        self.put("b.css", "x{color:#ABC}\ny{color:#aabbcc}\nz{color:#aabbcd}\n")
        h3, _, _ = self.hits(colours=["#aabbcc"])
        self.assertEqual(sorted((x["file"], x["line"]) for x in h3), [("b.css", 1), ("b.css", 2)])

    def test_path_names_found(self):
        self.put("src/OriginalApp/index.js", "ok\n")
        h, _, _ = self.hits(names=["Original App"])
        self.assertTrue(any(x["kind"] == "path" for x in h))

    def test_skips_git_node_modules_binary_and_excluded(self):
        self.put(".git/config", "Original App\n")
        self.put("node_modules/x/index.js", "Original App\n")
        self.put("swap/notes.md", "Original App\n")
        self.put("img.png", b"\0\0Original App".decode("latin1"), mode="w")
        with open(os.path.join(self.d, "bin.dat"), "wb") as fh:
            fh.write(b"\x00\x01Original App")
        h, skipped, _ = self.hits(names=["Original App"], excludes=["swap"])
        self.assertEqual([x for x in h if x["kind"] != "path"], [])
        self.assertTrue(any("binary" in s for s in skipped))

    def test_without_exclude_the_notes_are_found(self):
        self.put("swap/notes.md", "Original App\n")
        h, _, _ = self.hits(names=["Original App"])
        self.assertTrue(h)

    def test_allow_removes_harmless_longer_words(self):
        self.put("a.js", "notional value; also Notion here\n")
        h, _, _ = self.hits(names=["Notion"])
        self.assertEqual(len(h), 2)
        h, _, _ = self.hits(names=["Notion"], allow=["notional"])
        self.assertEqual(len(h), 1)

    def test_output_never_shows_the_rest_of_the_line(self):
        self.put("a.py", "API_TOKEN = 'sk-live-SECRET123'  # copied from OriginalApp docs\n")
        out = os.path.join(self.d, "..", "so-%d.json" % os.getpid())
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App", "--json", out],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("SECRET123", r.stdout)
        self.assertNotIn("API_TOKEN", r.stdout)
        with open(out) as fh:
            self.assertNotIn("SECRET123", fh.read())

    def test_unscanned_files_stop_a_clean_verdict_until_accepted(self):
        self.put("a.js", "Skyline\n")
        with open(os.path.join(self.d, "logo.png"), "wb") as fh:
            fh.write(b"\x89PNG\x00\x00")
        run = lambda *x: subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App"] + list(x),
                                        capture_output=True, text=True)
        r = run()
        self.assertEqual(r.returncode, 1)
        self.assertIn("not scanned", r.stdout)
        self.assertNotIn("CLEAN\n", r.stdout.replace("NOT CLEAN", ""))
        out = os.path.join(self.d, "..", "acc-%d.json" % os.getpid())
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = run("--accept-skipped", "--json", out)
        self.assertEqual(r.returncode, 0, r.stdout)
        with open(out) as fh:
            d = json.load(fh)
        self.assertTrue(d["passed"] and d["skipped_accepted"] and d["skipped"])

    def test_accept_skipped_does_not_hide_hits(self):
        self.put("a.js", "OriginalApp\n")
        with open(os.path.join(self.d, "logo.png"), "wb") as fh:
            fh.write(b"\x00")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App", "--accept-skipped"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)

    def test_modern_space_separated_rgb_is_caught(self):
        self.put("a.css", "a{color: rgb(17 34 51)}\nb{color: rgb(17 34 51 / 50%)}\nc{color: rgb(17, 34, 52)}\n")
        h, _, _ = self.hits(colours=["#112233"])
        self.assertEqual(sorted(x["line"] for x in h), [1, 2])

    def test_percentage_and_decimal_rgb_are_caught(self):
        self.put("a.css", "a{color: rgb(100% 0% 0%)}\nb{color: rgb(100%, 0%, 0%)}\nc{color: rgb(255.0 0 0)}\n"
                          "d{color: rgba(100% 0% 0% / 40%)}\ne{color: rgb(99% 0% 0%)}\nf{color: rgb(1.2.3 0 0)}\n")
        h, _, _ = self.hits(colours=["#ff0000"])
        self.assertEqual(sorted(x["line"] for x in h), [1, 2, 3, 4])

    def test_multiline_signed_exponent_and_absurd_rgb_forms(self):
        self.put("a.css", "a{color: rgb(255\n 0\n 0)}\nb{color: rgb(+255 0 0)}\nc{color: rgb(2.55e2 0 0)}\n"
                          "d{color: rgb(999 0 0)}\ne{color: rgb(" + "9" * 400 + " -5 0)}\nf{color: rgb(255 0 1)}\n")
        h, _, _ = self.hits(colours=["#ff0000"])
        # a (starts on line 1), b, c, d (999 clamps to 255), e (huge clamps to 255, -5 to 0); f has blue 1, so is not red
        self.assertEqual(sorted(x["line"] for x in h), [1, 4, 5, 6, 7])
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--color", "#ff0000"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("Traceback", r.stderr)

    def test_a_name_split_across_a_line_break_is_caught(self):
        self.put("a.md", "Built on Original\nApp ideas\n")
        h, _, _ = self.hits(names=["Original App"])
        self.assertEqual(len(h), 1)
        self.assertEqual(h[0]["line"], 1)

    def test_unreadable_folder_is_reported_not_ignored(self):
        self.put("a.js", "Skyline\n")
        locked = os.path.join(self.d, "locked")
        os.makedirs(locked)
        with open(os.path.join(locked, "x.js"), "w") as fh:
            fh.write("OriginalApp\n")
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o755)
        if os.access(locked, os.R_OK):
            self.skipTest("running as a user who can read mode-000 folders")
        h, skipped, _ = self.hits(names=["Original App"])
        self.assertTrue(any("locked" in s and "unreadable" in s for s in skipped), skipped)

    def test_binary_content_after_the_first_4kb_is_still_binary(self):
        with open(os.path.join(self.d, "late.bin"), "wb") as fh:
            fh.write(b"a" * 5000 + b"\x00\xff\xfe OriginalApp")
        self.put("a.js", "Skyline\n")
        h, skipped, scanned = self.hits(names=["Original App"])
        self.assertEqual(scanned, 1)
        self.assertTrue(any("late.bin" in s and "binary" in s for s in skipped))

    def test_invalid_utf8_text_is_reported_not_silently_decoded(self):
        with open(os.path.join(self.d, "latin.txt"), "wb") as fh:
            fh.write(b"caf\xe9 OriginalApp\n")
        _, skipped, scanned = self.hits(names=["Original App"])
        self.assertEqual(scanned, 0)
        self.assertTrue(any("latin.txt" in s and "UTF-8" in s for s in skipped))

    def test_a_named_pipe_does_not_hang_the_scan(self):
        os.mkfifo(os.path.join(self.d, "pipe.txt"))
        self.put("a.js", "Skyline\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App"],
                           capture_output=True, text=True, timeout=20)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not a regular file", r.stdout)

    def test_symlinked_folders_and_files_are_reported_not_followed(self):
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside)
        with open(os.path.join(outside, "x.js"), "w") as fh:
            fh.write("OriginalApp\n")
        self.put("a.js", "Skyline\n")
        os.symlink(outside, os.path.join(self.d, "linked-dir"))
        os.symlink(os.path.join(outside, "x.js"), os.path.join(self.d, "linked-file.js"))
        h, skipped, scanned = self.hits(names=["Original App"])
        self.assertEqual(h, [])
        self.assertEqual(scanned, 1)
        self.assertTrue(any("linked-dir" in s and "symlink" in s for s in skipped))
        self.assertTrue(any("linked-file.js" in s and "symlink" in s for s in skipped))
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("not scanned", r.stdout)

    def test_a_scan_of_nothing_is_not_clean(self):
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App", "--accept-skipped"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("no file was scanned", r.stdout)
        self.put("swap/notes.md", "OriginalApp\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App", "--exclude", "swap"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)

    def test_unwritable_json_is_a_clean_error(self):
        self.put("a.js", "Skyline\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App",
                            "--json", "/no/such/dir/o.json"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)

    def test_large_files_are_listed_not_silently_ignored(self):
        with open(os.path.join(self.d, "big.txt"), "wb") as fh:
            fh.write(b"a" * (sweep.MAX_BYTES + 10))
        _, skipped, _ = self.hits(names=["Original App"])
        self.assertTrue(any("over 2 MB" in s for s in skipped))

    def test_bad_arguments(self):
        run = lambda *a: subprocess.run([sys.executable, os.path.join(HERE, "sweep.py")] + list(a),
                                        capture_output=True, text=True)
        self.assertEqual(run("/no/such/dir", "--avoid", "x" * 5).returncode, 2)
        self.assertEqual(run(self.d).returncode, 2)
        self.assertEqual(run(self.d, "--avoid", "---").returncode, 2)
        self.assertEqual(run(self.d, "--color", "blue").returncode, 2)

    def test_cli_exit_codes_and_json(self):
        self.put("a.js", "OriginalApp\n")
        out = os.path.join(self.d, "..", "sweep-out-%d.json" % os.getpid())
        self.addCleanup(lambda: os.path.exists(out) and os.unlink(out))
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App",
                            "--json", out], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("NOT CLEAN", r.stdout)
        with open(out) as fh:
            self.assertFalse(json.load(fh)["passed"])
        os.unlink(os.path.join(self.d, "a.js"))
        self.put("a.js", "Skyline\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "sweep.py"), self.d, "--avoid", "Original App"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("CLEAN", r.stdout)


if __name__ == "__main__":
    unittest.main()
