import json
import math
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import motion_check as mc  # noqa: E402


def smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def checks(doc, level=None):
    out = mc.check_tracks(doc)
    return {(f["check"], f["level"]) for f in out if level is None or f["level"] == level}


class Ease(unittest.TestCase):
    def test_linear_move_fails(self):
        xs = [0] * 5 + [i * 10 for i in range(21)] + [200] * 10
        self.assertIn(("ease", "FAIL"), checks({"fps": 24, "context": "object", "tracks": {"x": xs}}))

    def test_eased_move_passes(self):
        xs = [0] * 5 + [200 * smooth(i / 20) for i in range(21)] + [200] * 10
        self.assertNotIn("ease", {c for c, _ in checks({"fps": 24, "context": "object", "tracks": {"x": xs}})})


class Volume(unittest.TestCase):
    def test_kept_volume_passes(self):
        sy = [1, 1, 0.8, 0.75, 0.85, 1.1, 1.2, 1.05, 1, 1] + [1] * 30
        doc = {"tracks": {"sx": [1 / v for v in sy], "sy": sy}, "volume": [["sx", "sy"]]}
        self.assertEqual(checks(doc, "FAIL"), set())

    def test_lost_volume_fails(self):
        sy = [1, 1, 0.7, 0.7, 1, 1] + [1] * 30
        doc = {"tracks": {"sx": [1.0] * len(sy), "sy": sy}, "volume": [["sx", "sy"]]}
        self.assertIn(("volume", "FAIL"), checks(doc))


class Overlap(unittest.TestCase):
    def wave(self, lag):
        return [20 * math.sin(2 * math.pi * (f - lag) / 24) * math.exp(-f / 40) for f in range(72)]

    def test_welded_chain_fails(self):
        doc = {"tracks": {"a": self.wave(0), "b": self.wave(0), "c": self.wave(0)}, "chains": [["a", "b", "c"]]}
        self.assertIn(("overlap", "FAIL"), checks(doc))

    def test_lagged_chain_passes(self):
        doc = {"tracks": {"a": self.wave(0), "b": self.wave(2), "c": self.wave(4)}, "chains": [["a", "b", "c"]]}
        self.assertNotIn("overlap", {c for c, _ in checks(doc)})


class Settle(unittest.TestCase):
    def test_ui_big_overshoot_fails(self):
        xs = [0, 30, 70, 100, 125, 130, 118, 104, 98, 100] + [100] * 20
        self.assertIn(("overshoot", "FAIL"), checks({"context": "ui", "tracks": {"x": xs}}))

    def test_jelly_warns(self):
        xs = [0] * 3 + [100 + 40 * math.cos(2 * math.pi * f / 6) for f in range(36)] + [100] * 20
        self.assertIn(("jelly", "WARN"), checks({"context": "object", "tracks": {"x": xs}}))

    def test_decaying_wag_is_not_jelly(self):
        xs = [40 * math.exp(-f / 8) * math.sin(2 * math.pi * f / 8) for f in range(60)] + [0] * 20
        self.assertNotIn("jelly", {c for c, _ in checks({"context": "character", "tracks": {"x": xs}})})


class Anticipation(unittest.TestCase):
    def test_cold_start_warns(self):
        xs = [0] * 10 + [100 * smooth(i / 12) for i in range(13)] + [100] * 10
        self.assertIn(("anticipation", "WARN"), checks({"context": "character", "tracks": {"x": xs}}))

    def test_wind_up_passes(self):
        prep = [-15 * smooth(i / 6) for i in range(7)]
        act = [-15 + 115 * smooth(i / 12) for i in range(1, 13)]
        xs = [0] * 10 + prep + act + [100] * 10
        self.assertNotIn("anticipation", {c for c, _ in checks({"context": "character", "tracks": {"x": xs}})})


class Arcs(unittest.TestCase):
    def test_straight_path_warns(self):
        n = 20
        doc = {"context": "character",
               "tracks": {"x": [0] * 3 + [10 * smooth(i / n) * n for i in range(n + 1)] + [200] * 3,
                          "y": [0] * 3 + [5 * smooth(i / n) * n for i in range(n + 1)] + [100] * 3},
               "paths": [["x", "y"]]}
        self.assertIn(("arcs", "WARN"), checks(doc))

    def test_parabola_passes(self):
        n = 20
        doc = {"context": "character",
               "tracks": {"x": [10.0 * i for i in range(n + 1)], "y": [400 * (i / n) * (1 - i / n) for i in range(n + 1)]},
               "paths": [["x", "y"]]}
        self.assertNotIn("arcs", {c for c, _ in checks(doc)})


class Twins(unittest.TestCase):
    def test_identical_limbs_warn(self):
        w = [30 * math.sin(2 * math.pi * f / 16) for f in range(48)]
        self.assertIn(("twins", "WARN"), checks({"tracks": {"l": w, "r": list(w)}, "mirrors": [["l", "r"]]}))


class Curves(unittest.TestCase):
    def test_back_out_overshoot(self):
        r = mc.bezier_report(0.34, 1.56, 0.64, 1)
        self.assertAlmostEqual(r["overshoot"], 0.10, delta=0.01)

    def test_critical_spring_no_overshoot(self):
        r = mc.spring_report(100, 20)
        self.assertLess(r["overshoot"], 0.001)
        self.assertAlmostEqual(r["damping_ratio"], 1.0, delta=1e-6)


class CriticCases(unittest.TestCase):
    """Regression cases from the first independent review."""

    def kinds(self, doc):
        return {c for c, _ in checks(doc)}

    def test_ballistic_x_fails_unless_exempt(self):
        n = 20
        doc = {"context": "character", "tracks": {"x": [10.0 * i for i in range(n + 1)] + [200.0] * 4}}
        self.assertIn(("ease", "FAIL"), checks(doc))
        doc["exempt"] = {"ease": ["x"]}
        self.assertNotIn("ease", self.kinds(doc))

    def test_brief_endpoint_easing_passes(self):
        xs = [0, 2] + [2 + 10 * i for i in range(1, 18)] + [174, 176, 176, 176]
        self.assertNotIn("ease", self.kinds({"context": "object", "tracks": {"x": xs}}))

    def test_short_linear_ui_move_fails(self):
        xs = [0.0] * 3 + [10.0 * i for i in range(11)] + [100.0] * 5  # 167 ms at 60 fps
        self.assertIn(("ease", "FAIL"), checks({"fps": 60, "context": "ui", "tracks": {"x": xs}}))

    def test_ui_overshoot_in_short_clips(self):
        for xs in ([0, 70, 120, 100, 100], [0, 80, 220, 100, 100, 100]):
            self.assertIn(("overshoot", "FAIL"), checks({"context": "ui", "tracks": {"x": xs}}), xs)

    def test_overshoot_of_an_earlier_beat(self):
        xs = [0, 60, 125, 100, 100, 100, 100, 100, 150, 200, 200, 200]
        self.assertIn(("overshoot", "FAIL"), checks({"context": "ui", "tracks": {"x": xs}}))

    def test_jelly_counts_crossings_through_exact_target(self):
        xs = [0, 50, 100, 108, 100, 93, 100, 106, 100, 95, 100, 100, 100]
        self.assertIn(("jelly", "WARN"), checks({"context": "ui", "tracks": {"x": xs}}))

    def test_scale_overshoot_is_checked(self):
        sy = [0.9, 0.95, 1.05, 1.15, 1.08, 1.0, 1.0, 1.0]
        doc = {"context": "ui", "tracks": {"sx": [1 / v for v in sy], "sy": sy}, "volume": [["sx", "sy"]]}
        self.assertIn(("overshoot", "FAIL"), checks(doc))

    def test_static_chain_is_not_welded(self):
        doc = {"tracks": {"a": [0.0] * 30, "b": [5.0] * 30}, "chains": [["a", "b"]]}
        self.assertNotIn("overlap", self.kinds(doc))

    def test_mixed_chain_names_the_welded_link(self):
        w = [20 * math.sin(2 * math.pi * f / 24) * math.exp(-f / 40) for f in range(72)]
        late = [0.0] * 3 + w[:-3]
        doc = {"tracks": {"a": w, "b": list(w), "c": late}, "chains": [["a", "b", "c"]]}
        found = [f for f in mc.check_tracks(doc) if f["check"] == "overlap"]
        self.assertEqual(len(found), 1)
        self.assertIn("a->b", found[0]["msg"])
        self.assertNotIn("b->c", found[0]["msg"])

    def test_closed_rectangle_has_corners(self):
        side = [i / 6 for i in range(6)]
        pts = ([(100 * t, 0) for t in side] + [(100, 100 * t) for t in side]
               + [(100 - 100 * t, 100) for t in side] + [(0, 100 - 100 * t) for t in side] + [(0, 0)])
        doc = {"context": "object", "tracks": {"x": [p[0] for p in pts], "y": [p[1] for p in pts]},
               "paths": [["x", "y"]]}
        self.assertIn(("arcs", "WARN"), checks(doc))

    def test_unrelated_prop_does_not_clear_cold_move(self):
        cold = [0.0] * 10 + [100 * smooth(i / 12) for i in range(13)] + [100.0] * 10
        prop = [0.0] * 4 + [-3, -6, -8, -9, -10, -10] + [-10 + 60 * smooth(i / 12) for i in range(13)] + [50.0] * 10
        doc = {"context": "character", "tracks": {"body.x": cold, "prop.x": prop}}
        self.assertIn("body.x", {f["track"] for f in mc.check_tracks(doc) if f["check"] == "anticipation"})

    def test_opposite_sign_mirrors_are_twins(self):
        w = [30 * math.sin(2 * math.pi * f / 16) for f in range(48)]
        doc = {"tracks": {"l": w, "r": [-x for x in w]}, "mirrors": [["l", "r"]]}
        self.assertIn(("twins", "WARN"), checks(doc))

    def test_spring_settle_reporting(self):
        self.assertIsNone(mc.spring_report(100, 0)["settle_seconds_2pct"])
        slow = mc.spring_report(1, 100)
        self.assertGreater(slow["settle_seconds_2pct"], 100)
        self.assertEqual(slow["status"], "settles")
        self.assertAlmostEqual(mc.spring_report(100, 4)["overshoot"], math.exp(-math.pi * 0.2 / math.sqrt(0.96)),
                               places=6)

    def test_bad_input_exits_2(self):
        bad_docs = [
            {"tracks": {"x": [0, "1", 2]}},
            {"tracks": {"x": [0, 1, 2]}, "paths": [["x"]]},
            {"fps": 0, "tracks": {"x": [0, 1, 2]}},
            {"context": "film", "tracks": {"x": [0, 1, 2]}},
            {"tracks": {"x": [0, 1, 2], "y": [0, 1]}},
            {"tracks": {"x": [0, 1, 2]}, "chains": [["x", "nope"]]},
        ]
        script = os.path.join(ROOT, "scripts", "motion_check.py")
        with tempfile.TemporaryDirectory() as d:
            for i, doc in enumerate(bad_docs):
                path = os.path.join(d, f"{i}.json")
                with open(path, "w") as fh:
                    json.dump(doc, fh)
                p = subprocess.run([sys.executable, script, "tracks", path], capture_output=True, text=True)
                self.assertEqual(p.returncode, 2, (doc, p.stdout, p.stderr))
        for args in (["bezier", "0.2,0.4"], ["bezier", "1.2,0,-0.1,1"], ["spring", "--stiffness", "0",
                                                                           "--damping", "1"]):
            p = subprocess.run([sys.executable, script] + args, capture_output=True, text=True)
            self.assertEqual(p.returncode, 2, (args, p.stdout, p.stderr))


class ExampleFile(unittest.TestCase):
    def test_example_track_file_is_valid(self):
        with open(os.path.join(ROOT, "examples", "tracks.example.json")) as fh:
            mc.check_tracks(json.load(fh))


class Demo(unittest.TestCase):
    """The shipped example must keep showing the difference this skill makes."""

    def test_demo_naive_fails_and_skill_passes(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([sys.executable, os.path.join(ROOT, "examples", "hop_demo.py"), "--out", d],
                           check=True, capture_output=True)
            for name, code in (("naive", 1), ("disney", 0)):
                p = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "motion_check.py"), "tracks",
                                    os.path.join(d, f"{name}.tracks.json"), "--json"], capture_output=True, text=True)
                self.assertEqual(p.returncode, code, p.stdout)
                if name == "disney":
                    self.assertEqual(json.loads(p.stdout)["findings"], [])


if __name__ == "__main__":
    unittest.main()
