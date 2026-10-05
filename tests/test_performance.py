# SPDX-License-Identifier: GPL-3.0-or-later

"""Build time must grow linearly with the number of leaves, with the armature, wind and Leaf Animation on.

Leaf Animation used to make a bone, a vertex group and two F-curves per leaf; Blender's cost to create each
grows with how many there already are, so doubling the leaves made the leaf part about 4 times slower and
big trees took minutes. Measured now (Quaking Aspen, 3 levels, branches 50/30/10): the leaf part takes
0.125, 0.25 and 0.465 s for 20, 40 and 80 leaves per sprout (9,676 to 38,730 leaves).
"""

import math
import time
import unittest

import bpy
import helpers

# Leaf part at 80 leaves per sprout over the part at 40: about 1.9 measured, 2 if linear, 4 if quadratic
MAX_RATIO = 2.6


class LeafScaling(unittest.TestCase):
    RUNS = 2  # the shortest of these runs counts, which keeps other load on the machine out of the ratio

    def build_time(self, leaves):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(
            levels=3, branches=(0, 50, 30, 10), leaves=leaves, showLeaves=leaves > 0,
            useRig=True, windAnim=True, leafFlutter=True,
        )  # fmt: skip
        times = []
        with helpers.untraced():
            for _ in range(self.RUNS):
                helpers.reset_scene()
                started = time.perf_counter()
                self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
                times.append(time.perf_counter() - started)
        return min(times)

    def test_leaf_build_is_linear(self):
        bare = self.build_time(0)
        half = self.build_time(40) - bare
        full = self.build_time(80) - bare
        self.assertLess(full / half, MAX_RATIO, f"leaf part {half:.3f} s at 40 leaves, {full:.3f} s at 80")


class ModelSpeed(unittest.TestCase):
    """The array model grows the test tree (Quaking Aspen, 1,336 stems) in well under a tenth of a second."""

    LIMIT = 0.1
    RUNS = 3

    def test_quaking_aspen_model(self):
        from types import SimpleNamespace

        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, branches=(0, 100, 30, 10))
        params = helpers.module("model.params").TreeParams(SimpleNamespace(**settings, leafDupliObj=""))
        grower = helpers.module("model.tree").TreeGrower
        curve_class = helpers.module("model.curve_data").CurveData
        import random

        times = []
        with helpers.untraced():
            for _ in range(self.RUNS):
                started = time.perf_counter()
                grown = grower(params, random.Random(params.seed)).grow(curve_class(), None, params.scale)
                times.append(time.perf_counter() - started)
        self.assertGreater(grown.level_ends[-1], 1000)
        self.assertLess(min(times), self.LIMIT, f"model time {min(times):.3f} s for {grown.level_ends[-1]} stems")


class BuildScaling(unittest.TestCase):
    """The whole build (growth, curves, leaves, node wind, skin mesh) grows linearly with the tree.

    Every per-item Blender call used to cost time in proportion to the items already made, so trees of 20,000
    stems took about a minute; the model now grows in memory and every part is written in bulk.
    """

    MAX_EXPONENT = 1.3  # 1 if linear, 2 if quadratic
    RUNS = 2

    def build(self, branches):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(
            levels=3, branches=(0, branches, 30, 10), showLeaves=True,
            windAnim=True, leafFlutter=True, makeMesh=True,
        )  # fmt: skip
        times = []
        with helpers.untraced():
            for _ in range(self.RUNS):
                helpers.reset_scene()
                started = time.perf_counter()
                self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
                times.append(time.perf_counter() - started)
        return len(helpers.spline_points()), min(times)

    def test_build_is_linear(self):
        small_stems, small = self.build(25)
        big_stems, big = self.build(100)
        exponent = math.log(big / small) / math.log(big_stems / small_stems)
        measured = f"{small_stems} stems {small:.2f} s, {big_stems} stems {big:.2f} s"
        self.assertLess(exponent, self.MAX_EXPONENT, measured)
