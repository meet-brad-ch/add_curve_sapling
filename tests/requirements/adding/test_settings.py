# SPDX-License-Identifier: GPL-3.0-or-later

"""Adding a tree: settings (the requirements each class or test names)."""

import json
import math
import random
import re
import statistics
import time
import unittest
from types import SimpleNamespace
from typing import Any

import bpy
from mathutils import Vector
from support.addon import Addon
from support.evaluated import Evaluated
from support.layout import RecordingLayout
from support.model import BoneIndex, Model
from support.scene import Scene
from support.verifies import Verifies

CASES = 100


SEED = 20260929


SLOW_FACTOR = 8.0


SLOW_FLOOR = 1.0


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


SPREAD = {"angle": 90.0, "other": 2.0}


ANGLES = re.compile(r"(?i)angle|rotate|curve(V|Back)?$|leafangle")


SKIP = {"leafDupliObj"}  # set explicitly (instanced leaves need an object)


BOOL_ODDS = {"helix": 0.15}


HELIX_ANGLE = 89.0


FACES_PER_LEAF = {"hex": 2, "rect": 1, "dFace": 1, "dVert": 0}


@Verifies("SWR-0014")
class SettingsPages(unittest.TestCase):
    def draw(self, **changes):
        """The properties drawn on every page, with the operator's defaults plus `changes`."""
        pages = Addon.module("ui.pages").SettingsPages
        drawn_per_page = []
        for page in range(len(Addon.module("ui.properties").Choices.PAGES)):
            values = {**Addon.operator_defaults(), "leafDupliObj": "", "presetName": "", "overwrite": False}
            props = SimpleNamespace(**{**values, "chooseSet": str(page), **changes})
            layout = RecordingLayout()
            pages.draw(props, layout)
            drawn_per_page.append(layout.props)
        return drawn_per_page

    def test_one_drawing_method_per_page(self):
        pages = Addon.module("ui.pages").SettingsPages
        choices = Addon.module("ui.properties").Choices.PAGES
        self.assertEqual(len(pages.ORDER), len(choices))
        missing = [name for name in pages.ORDER if not hasattr(pages, name)]
        self.assertEqual(missing, [], "page names without a drawing method")

    def test_every_page_draws_existing_properties(self):
        properties = set(Addon.operator_property_names())
        for page, drawn in enumerate(self.draw()):
            with self.subTest(page=page):
                self.assertEqual(drawn[0], "chooseSet")
                self.assertGreater(len(drawn), 3)
                self.assertEqual(set(drawn) - properties, set())

    def test_every_generation_property_is_on_a_page(self):
        drawn = set()
        for changes in ({}, {"shape": "8", "leafShape": "dFace", "blossomRate": 0.5}):
            for page in self.draw(**changes):
                drawn.update(page)
        hidden = {"bend"}  # Leaf Bend has no control, as in earlier versions
        self.assertEqual(set(Addon.generation_names()) - drawn - hidden, set())

    def test_conditional_fields(self):
        geometry, leaves = 0, 5
        self.assertNotIn("customShape", self.draw()[geometry])
        self.assertIn("customShape", self.draw(shape="8")[geometry])
        self.assertIn("leafMaterial", self.draw(leafShape="hex")[leaves])
        self.assertNotIn("leafDupliObj", self.draw(leafShape="hex")[leaves])
        instanced = self.draw(leafShape="dVert")[leaves]
        self.assertIn("leafDupliObj", instanced)
        self.assertNotIn("leafMaterial", instanced)
        self.assertNotIn("blossomShape", self.draw()[leaves])
        blossoming = self.draw(leafShape="dVert", blossomRate=0.5)[leaves]
        self.assertIn("blossomShape", blossoming)
        self.assertIn("leafMaterial", blossoming)


@Verifies("SWR-0016")
class SettingsFuzz(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(SEED)
        self.grown = Model.record_growth(self)

    def random_settings(self):
        rna = bpy.ops.curve.tree_add.get_rna_type()
        settings = {}
        for name in Addon.generation_names():
            if name in SKIP:
                continue
            settings[name] = self.random_value(rna.properties[name])
        settings["blossomRate"] = max(settings["blossomRate"], 0.0)
        curves = []
        for v, helix in zip(settings["curveV"], settings["helix"], strict=True):
            curve = v
            if helix:
                curve = math.copysign(abs(v) % HELIX_ANGLE, v)
            curves.append(curve)
        settings["curveV"] = curves
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
            values = []
            for i in range(prop.array_length):
                cap = None
                if caps:
                    cap = caps[i]
                values.append(self.number(prop, cap, prop.default_array[i]))
            return values
        return self.number(prop, CAPS.get(name), prop.default)

    def number(self, prop, cap, default):
        if prop.type == "INT":
            return self.integer(prop, cap)
        if cap:
            return self.rng.uniform(*cap)
        low = prop.soft_min
        high = prop.soft_max
        if not (math.isfinite(low) and math.isfinite(high)) or high - low > 1000:
            spread = SPREAD["other"]
            if ANGLES.search(prop.identifier):
                spread = SPREAD["angle"]
            low = max(low, default - spread)
            high = min(high, default + spread)
        return self.rng.uniform(low, high)

    def integer(self, prop, cap):
        """An integer in the cap, or in the soft range limited to -100..100."""
        if cap:
            low, high = cap
        else:
            low = max(prop.soft_min, -100)
            high = min(prop.soft_max, 100)
        return self.rng.randint(low, high)

    FEATURES = (
        "prune", "useRig", "windAnim", "leafFlutter", "makeMesh", "showLeaves", "levels_4",
        "leaf_hex", "leaf_rect", "leaf_dFace", "leaf_dVert", "palmate", "trunks", "bend", "helix", "blossoms",
    )  # fmt: skip

    SWITCHES = ("prune", "useRig", "windAnim", "leafFlutter", "makeMesh", "showLeaves")

    @classmethod
    def features(cls, settings):
        """The features a case exercises, so the run can prove it covered all of them."""
        flags = [name for name in cls.SWITCHES if settings[name]]
        flags += cls.shape_features(settings)
        if settings["showLeaves"]:
            flags += cls.leaf_features(settings)
        return flags

    @staticmethod
    def shape_features(settings):
        """The stem features a case exercises: four levels, a clump of trunks, bends, helices."""
        levels = settings["levels"]
        flags = []
        if levels == 4:
            flags.append("levels_4")
        if settings["trunks"] > 1:
            flags.append("trunks")
        if any(settings["bendV"][:levels]):
            flags.append("bend")
        if any(settings["helix"][:levels]):
            flags.append("helix")
        return flags

    @staticmethod
    def leaf_features(settings):
        """The leaf features a case with leaves exercises: its leaf shape, palmate leaves, blossoms."""
        flags = [f"leaf_{settings['leafShape']}"]
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
            Scene.reset()
            leaf = Scene.add_leaf_card()
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
        self.assert_finite("tree_curves", [c for points in Evaluated.spline_points() for co, _r in points for c in co])
        self.assert_meshes_finite()
        self.assert_whole_leaves(settings)
        if settings["useRig"]:
            self.assert_bones_on_splines()

    def assert_meshes_finite(self):
        """Every mesh of the tree (not the user's leaf card) has finite vertex coordinates."""
        for ob in bpy.data.objects:
            if ob.type == "MESH" and ob.name != "leaf_card":
                self.assert_finite(ob.name, [c for v in ob.data.vertices for c in v.co])

    def assert_whole_leaves(self, settings):
        """The leaves mesh holds whole leaves: its face count is a multiple of the leaf shape's faces (dVert
        instances on vertices, so it has no faces to count)."""
        leaves = bpy.data.objects.get("leaves")
        if leaves is None or settings["leafShape"] == "dVert":
            return
        per_leaf = FACES_PER_LEAF[settings["leafShape"]]
        self.assertEqual(len(leaves.data.polygons) % per_leaf, 0, "whole leaves")

    def assert_finite(self, name, values):
        not_finite = [v for v in values if not math.isfinite(v)]
        self.assertEqual(not_finite[:5], [], f"{name} has NaN or inf coordinates")

    def assert_bones_on_splines(self):
        splines = Evaluated.spline_points()
        for bone in Scene.armature().data.bones:
            index = BoneIndex.of(bone.name)
            if index is not None:
                co = Vector(splines[index.spline][index.point][0])
                self.assertLess((bone.head_local - co).length, 1e-4, bone.name)
