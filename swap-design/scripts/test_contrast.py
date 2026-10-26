import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import contrast  # noqa: E402


def wjson(obj):
    fh = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(obj, fh)
    fh.close()
    return fh.name


class ContrastTests(unittest.TestCase):
    def test_black_on_white_is_21(self):
        self.assertAlmostEqual(contrast.ratio((0, 0, 0), (255, 255, 255)), 21.0, places=6)

    def test_identical_is_1(self):
        self.assertAlmostEqual(contrast.ratio((120, 30, 200), (120, 30, 200)), 1.0, places=6)

    def test_known_value_777_on_white(self):
        # #777777 on white is the textbook 4.48:1, which fails AA by a hair.
        r = contrast.ratio(contrast.parse_hex("#777", "t"), (255, 255, 255))
        self.assertAlmostEqual(r, 4.48, places=2)

    def test_symmetric(self):
        a, b = (10, 20, 30), (200, 210, 220)
        self.assertAlmostEqual(contrast.ratio(a, b), contrast.ratio(b, a))

    def test_pass_and_fail(self):
        res = contrast.run({"colors": {"t": "#000", "m": "#777777", "bg": "#fff"},
                            "pairs": [["t", "bg"], ["m", "bg"], ["m", "bg", 3.0]]})
        self.assertEqual([r["pass"] for r in res], [True, False, True])

    def test_themes_each_checked(self):
        doc = {"themes": {
            "light": {"colors": {"t": "#111", "bg": "#fff"}, "pairs": [["t", "bg"]]},
            "dark": {"colors": {"t": "#333", "bg": "#222"}, "pairs": [["t", "bg"]]}}}
        res = contrast.run(doc)
        self.assertEqual({r["theme"]: r["pass"] for r in res}, {"light": True, "dark": False})

    def test_bad_input(self):
        bad = [
            [],
            {"colors": {}, "pairs": [["a", "b"]]},
            {"colors": {"a": "red", "b": "#fff"}, "pairs": [["a", "b"]]},
            {"colors": {"a": "#12", "b": "#fff"}, "pairs": [["a", "b"]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": []},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [["a", "zzz"]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [["a"]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [[["a"], "b"]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [[{"x": 1}, "b"]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [["a", "b", 99]]},
            {"colors": {"a": "#000", "b": "#fff"}, "pairs": [["a", "b", True]]},
            {"themes": {}},
        ]
        for doc in bad:
            with self.assertRaises(contrast.InputError, msg=str(doc)):
                contrast.run(doc)

    def test_cli_exit_codes(self):
        good = wjson({"colors": {"t": "#000", "bg": "#fff"}, "pairs": [["t", "bg"]]})
        fail = wjson({"colors": {"t": "#999", "bg": "#fff"}, "pairs": [["t", "bg"]]})
        bad = wjson({"colors": {}})
        for p in (good, fail, bad):
            self.addCleanup(os.unlink, p)
        run = lambda p: subprocess.run([sys.executable, os.path.join(HERE, "contrast.py"), p],
                                       capture_output=True, text=True)
        self.assertEqual(run(good).returncode, 0)
        self.assertEqual(run(fail).returncode, 1)
        self.assertEqual(run(bad).returncode, 2)
        self.assertEqual(run("/nonexistent.json").returncode, 2)

    def test_unwritable_json_is_a_clean_error(self):
        good = wjson({"colors": {"t": "#000", "bg": "#fff"}, "pairs": [["t", "bg"]]})
        self.addCleanup(os.unlink, good)
        r = subprocess.run([sys.executable, os.path.join(HERE, "contrast.py"), good, "--json", "/no/such/dir/o.json"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 2)
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
