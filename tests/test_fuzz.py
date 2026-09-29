# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate trees from random settings within the operator's own ranges and check invariants.

The seed is fixed, so a failure is reproducible; each case prints its settings when it fails.
"""

import json
import math
import random
import re
import sys
import unittest
from typing import Any

import bpy
import helpers

CASES = 100
SEED = 20260929

# Unbounded counts are capped so each tree stays small; (low, high) per vector element or scalar.
CAPS: dict[str, Any] = {
    "levels": (1, 4),
    "branches": [(0, 40), (0, 20), (0, 8), (0, 6)],
    "curveRes": [(1, 8), (1, 6), (1, 4), (1, 3)],
    "leaves": (-6, 30),
    "nrings": (0, 6),
    "baseSplits": (0, 4),
    "boneStep": [(1, 3)] * 4,
    "armLevels": (0, 4),
    "loopFrames": (0, 60),
    "bevelRes": (0, 3),
    "resU": (1, 6),
    "seed": (0, 10_000),
}
# Floats without a finite soft range vary around their default by this much.
SPREAD = {"angle": 90.0, "other": 2.0}
ANGLES = re.compile(r"(?i)angle|rotate|curve(V|Back)?$|leafangle")
SKIP = {"leafDupliObj"}  # set explicitly (instanced leaves need an object)

FACES_PER_LEAF = {"hex": 2, "rect": 1, "dFace": 1, "dVert": 0}
BONE_NAME = re.compile(r"bone(\d{3})\.(\d{3})$")


def tree_module():
    return sys.modules[f"{helpers.MODULE}.model.tree"]


class SettingsFuzz(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(SEED)
        self.grown: list[tuple[int, int]] = []
        grower = tree_module().TreeGrower
        original = grower.grow

        def recording_grow(grower_self, curve, scratch, scale):
            grown = original(grower_self, curve, scratch, scale)
            self.grown.append((len(grown.bone_map), len(curve.splines)))
            return grown

        grower.grow = recording_grow
        self.addCleanup(setattr, grower, "grow", original)

    def random_settings(self):
        rna = bpy.ops.curve.tree_add.get_rna_type()
        settings = {}
        for name in helpers.generation_names():
            if name in SKIP:
                continue
            settings[name] = self.random_value(rna.properties[name])
        return settings

    def random_value(self, prop):
        name = prop.identifier
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
        low, high = prop.soft_min, prop.soft_max
        if not (math.isfinite(low) and math.isfinite(high)) or high - low > 1000:
            spread = SPREAD["angle"] if ANGLES.search(prop.identifier) else SPREAD["other"]
            low, high = max(low, default - spread), min(high, default + spread)
        return self.rng.uniform(low, high)

    FEATURES = (
        "prune", "useArm", "armAnim", "leafAnim", "makeMesh", "showLeaves", "levels_4",
        "leaf_hex", "leaf_rect", "leaf_dFace", "leaf_dVert", "palmate",
    )  # fmt: skip

    @staticmethod
    def features(settings):
        """The features a case exercises, so the run can prove it covered all of them."""
        flags = [
            name for name in ("prune", "useArm", "armAnim", "leafAnim", "makeMesh", "showLeaves") if settings[name]
        ]
        if settings["levels"] == 4:
            flags.append("levels_4")
        if settings["showLeaves"]:
            flags.append(f"leaf_{settings['leafShape']}")
            if settings["leaves"] < 0:
                flags.append("palmate")
        return flags

    def test_random_settings(self):
        failures = []
        seen: dict[str, int] = {}
        for case in range(CASES):
            settings = self.random_settings()
            for feature in self.features(settings):
                seen[feature] = seen.get(feature, 0) + 1
            helpers.reset_scene()
            leaf = bpy.data.objects.new("leaf_card", bpy.data.meshes.new("leaf_card"))
            bpy.context.scene.collection.objects.link(leaf)
            try:
                result = bpy.ops.curve.tree_add(**settings, leafDupliObj="leaf_card", do_update=True)
                self.assertEqual(result, {"FINISHED"})
                self.check_tree(settings)
            except Exception as error:  # collect every failing case, then fail the test with all of them
                failures.append(f"case {case}: {type(error).__name__}: {error}\n  {json.dumps(settings)}")
        self.assertEqual(failures, [], "\n".join(failures))
        self.assertEqual(len(self.grown), CASES)
        rare = {feature: count for feature, count in seen.items() if count < 5}
        self.assertEqual(rare, {}, f"features too rare to trust the run: {seen}")
        self.assertEqual(set(seen), set(self.FEATURES), "every feature occurs")

    def check_tree(self, settings):
        bone_links, splines = self.grown[-1]
        self.assertEqual(bone_links, splines, "one bone link per spline")
        for ob in bpy.data.objects:
            if ob.type == "CURVE" and ob.name.startswith("tree"):
                self.assert_finite(ob.name, [c for s in ob.data.splines for p in s.bezier_points for c in p.co])
            elif ob.type == "MESH" and ob.name != "leaf_card":
                self.assert_finite(ob.name, [c for v in ob.data.vertices for c in v.co])
        leaves = bpy.data.objects.get("leaves")
        if leaves and settings["leafShape"] != "dVert":
            per_leaf = FACES_PER_LEAF[settings["leafShape"]]
            self.assertEqual(len(leaves.data.polygons) % per_leaf, 0, "whole leaves")
        if settings["useArm"]:
            self.assert_bones_on_splines()

    def assert_finite(self, name, values):
        self.assertTrue(all(math.isfinite(v) for v in values), f"{name} has NaN or inf coordinates")

    def assert_bones_on_splines(self):
        arm = next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")
        splines = bpy.data.objects["tree"].data.splines
        for bone in arm.data.bones:
            match = BONE_NAME.match(bone.name)
            if match:
                spline, point = (int(g) for g in match.groups())
                co = splines[spline].bezier_points[point].co
                self.assertLess((bone.head_local - co).length, 1e-4, bone.name)
