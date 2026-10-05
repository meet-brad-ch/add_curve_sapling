# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate trees from random settings within the operator's own ranges and check invariants.

The seed is fixed, so a failure is reproducible; each case prints its settings when it fails.
"""

import json
import math
import random
import re
import statistics
import time
import unittest
from typing import Any

import bpy
import helpers
from mathutils import Vector

CASES = 100
SEED = 20260929
# A case slower than SLOW_FACTOR times the median case and slower than SLOW_FLOOR seconds fails: a slow build is a
# defect. The limit is relative because the cases run under the gate's coverage tracer, which slows every build
# several times over and by how much depends on the machine; the run prints the median and the slowest case.
SLOW_FACTOR = 8.0
SLOW_FLOOR = 1.0

# Unbounded counts are capped so each tree stays small; (low, high) per vector element or scalar.
CAPS: dict[str, Any] = {
    "levels": (1, 4),
    "branches": [(0, 40), (0, 20), (0, 8), (0, 6)],
    "curveRes": [(1, 8), (1, 6), (1, 4), (1, 3)],
    "leaves": (-6, 30),
    "nrings": (0, 6),
    "baseSplits": (0, 4),
    "trunks": (1, 3),
    # splits on every segment of every level grow tens of thousands of stems (13,000-23,000 seen); with an
    # armature on every level that is 30,000+ bones, and Blender's own cost to create each bone, F-curve and
    # vertex group grows with how many exist (case 8 of the uncapped run: 73 s)
    "segSplits": [(0.0, 0.5)] * 4,
    "bendV": [(0.0, 180.0)] * 4,
    # below 0 means no blossoms (about a third of the cases), so the leaves-only path stays common
    "blossomRate": (-0.5, 1.0),
    "jointStep": [(1, 3)] * 4,
    "jointLevels": (0, 4),
    "loopFrames": (0, 60),
    "bevelRes": (0, 3),
    "resU": (1, 6),
    "seed": (0, 10_000),
}
# Floats without a finite soft range vary around their default by this much.
SPREAD = {"angle": 90.0, "other": 2.0}
ANGLES = re.compile(r"(?i)angle|rotate|curve(V|Back)?$|leafangle")
SKIP = {"leafDupliObj"}  # set explicitly (instanced leaves need an object)
# A boolean vector element is on with this probability (helix stems on half of all levels would leave few plain ones)
BOOL_ODDS = {"helix": 0.15}
# A helix level needs a Curvature Variation below 90 degrees: larger draws are folded below this
HELIX_ANGLE = 89.0

FACES_PER_LEAF = {"hex": 2, "rect": 1, "dFace": 1, "dVert": 0}


class SettingsFuzz(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(SEED)
        self.grown = helpers.record_growth(self)

    def random_settings(self):
        rna = bpy.ops.curve.tree_add.get_rna_type()
        settings = {}
        for name in helpers.generation_names():
            if name in SKIP:
                continue
            settings[name] = self.random_value(rna.properties[name])
        settings["blossomRate"] = max(settings["blossomRate"], 0.0)
        settings["curveV"] = [
            math.copysign(abs(v) % HELIX_ANGLE, v) if helix else v
            for v, helix in zip(settings["curveV"], settings["helix"], strict=True)
        ]
        return settings

    def random_value(self, prop):
        name = prop.identifier
        if prop.type == "BOOLEAN" and prop.is_array:
            return [self.rng.random() < BOOL_ODDS[name] for _ in range(prop.array_length)]
        if prop.type == "BOOLEAN":
            return self.rng.random() < 0.5
        if prop.type == "ENUM":
            return self.rng.choice([item.identifier for item in prop.enum_items])
        if prop.is_array:
            caps = CAPS.get(name)
            return [
                self.number(prop, caps[i] if caps else None, prop.default_array[i]) for i in range(prop.array_length)
            ]
        return self.number(prop, CAPS.get(name), prop.default)

    def number(self, prop, cap, default):
        if prop.type == "INT":
            low, high = cap if cap else (max(prop.soft_min, -100), min(prop.soft_max, 100))
            return self.rng.randint(low, high)
        if cap:
            return self.rng.uniform(*cap)
        low, high = prop.soft_min, prop.soft_max
        if not (math.isfinite(low) and math.isfinite(high)) or high - low > 1000:
            spread = SPREAD["angle"] if ANGLES.search(prop.identifier) else SPREAD["other"]
            low, high = max(low, default - spread), min(high, default + spread)
        return self.rng.uniform(low, high)

    FEATURES = (
        "prune", "useRig", "windAnim", "leafFlutter", "makeMesh", "showLeaves", "levels_4",
        "leaf_hex", "leaf_rect", "leaf_dFace", "leaf_dVert", "palmate", "trunks", "bend", "helix", "blossoms",
    )  # fmt: skip

    @staticmethod
    def features(settings):
        """The features a case exercises, so the run can prove it covered all of them."""
        flags = [
            name for name in ("prune", "useRig", "windAnim", "leafFlutter", "makeMesh", "showLeaves") if settings[name]
        ]
        if settings["levels"] == 4:
            flags.append("levels_4")
        if settings["trunks"] > 1:
            flags.append("trunks")
        if any(settings["bendV"][: settings["levels"]]):
            flags.append("bend")
        if any(settings["helix"][: settings["levels"]]):
            flags.append("helix")
        if settings["showLeaves"]:
            flags.append(f"leaf_{settings['leafShape']}")
            if settings["leaves"] < 0:
                flags.append("palmate")
            if settings["leaves"] and settings["blossomRate"] > 0:
                flags.append("blossoms")
        return flags

    def test_random_settings(self):
        failures = []
        seen: dict[str, int] = {}
        times: list[float] = []
        cases: list[dict] = []
        for case in range(CASES):
            settings = self.random_settings()
            cases.append(settings)
            for feature in self.features(settings):
                seen[feature] = seen.get(feature, 0) + 1
            helpers.reset_scene()
            leaf = helpers.add_leaf_card()
            started = time.perf_counter()
            try:
                result = bpy.ops.curve.tree_add(**settings, leafDupliObj=leaf.name, do_update=True)
                self.assertEqual(result, {"FINISHED"})
                self.check_tree(settings)
            except Exception as error:  # collect every failing case, then fail the test with all of them
                failures.append(f"case {case}: {type(error).__name__}: {error}\n  {json.dumps(settings)}")
            times.append(time.perf_counter() - started)
            print(f"fuzz case {case}: {times[-1]:.2f} s", flush=True)  # progress: a slow case shows which one it is
        failures += self.slow_cases(times, cases)
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertEqual(len(self.grown), CASES)
        rare = {feature: count for feature, count in seen.items() if count < 5}
        self.assertEqual(rare, {}, f"features too rare to trust the run: {seen}")
        self.assertEqual(set(seen), set(self.FEATURES), "every feature occurs")

    @staticmethod
    def slow_cases(times, cases):
        """The cases slower than SLOW_FACTOR times the median and SLOW_FLOOR seconds; prints the median and the
        slowest case, so every run's log shows the margin."""
        median = statistics.median(times)
        slowest = max(range(len(times)), key=times.__getitem__)
        print(f"fuzz: median {median:.2f} s, slowest {times[slowest]:.2f} s (case {slowest})", flush=True)
        return [
            f"case {case}: took {seconds:.1f} s, {seconds / median:.0f} times the median\n  {json.dumps(cases[case])}"
            for case, seconds in enumerate(times)
            if seconds > SLOW_FACTOR * median and seconds > SLOW_FLOOR
        ]

    def check_tree(self, settings):
        model = self.grown[-1]
        self.assertEqual(len(model.grown.bone_map), model.curve.spline_count, "one bone link per spline")
        self.assert_finite("tree_curves", [c for points in helpers.spline_points() for co, _r in points for c in co])
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name != "leaf_card":
                self.assert_finite(ob.name, [c for v in ob.data.vertices for c in v.co])
        leaves = bpy.data.objects.get("leaves")
        if leaves and settings["leafShape"] != "dVert":
            per_leaf = FACES_PER_LEAF[settings["leafShape"]]
            self.assertEqual(len(leaves.data.polygons) % per_leaf, 0, "whole leaves")
        if settings["useRig"]:
            self.assert_bones_on_splines()

    def assert_finite(self, name, values):
        self.assertTrue(all(math.isfinite(v) for v in values), f"{name} has NaN or inf coordinates")

    def assert_bones_on_splines(self):
        splines = helpers.spline_points()
        for bone in helpers.armature().data.bones:
            index = helpers.bone_index(bone.name)
            if index is not None:
                co = Vector(splines[index.spline][index.point][0])
                self.assertLess((bone.head_local - co).length, 1e-4, bone.name)
