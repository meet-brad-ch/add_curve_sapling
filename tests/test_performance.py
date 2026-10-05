# SPDX-License-Identifier: GPL-3.0-or-later

"""Build time must grow linearly with the number of leaves, with the armature, wind and Leaf Animation on.

Leaf Animation used to make a bone, a vertex group and two F-curves per leaf; Blender's cost to create each
grows with how many there already are, so doubling the leaves made the leaf part about 4 times slower and
big trees took minutes. The leaf part is timed inside the build (the leaf stages), not as a difference of
whole builds: the rig's own time varies by more than the leaf part now takes.
"""

import math
import time
import unittest

import bpy
import helpers

# Leaf stages at 80 leaves per sprout over the stages at 40: 2 if linear, 4 if quadratic
MAX_RATIO = 2.6


class StageTimer:
    """Adds up the time spent in the given methods while a tree is built (patched for the test's duration)."""

    def __init__(self, test: unittest.TestCase, stages: tuple[tuple[str, str, str], ...]) -> None:
        self.total = 0.0
        for module_name, class_name, method_name in stages:
            owner = getattr(helpers.module(module_name), class_name)
            raw = owner.__dict__[method_name]
            function = raw.__func__ if isinstance(raw, staticmethod | classmethod) else raw
            timed = self._timed(function)
            setattr(owner, method_name, type(raw)(timed) if isinstance(raw, staticmethod | classmethod) else timed)
            test.addCleanup(setattr, owner, method_name, raw)

    def _timed(self, function):
        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.total += time.perf_counter() - started

        return timed


class LeafScaling(unittest.TestCase):
    RUNS = 2  # the shortest of these runs counts, which keeps other load on the machine out of the ratio
    STAGES = (
        ("model.leaves", "LeafGenerator", "generate"),
        ("build.leaf_object", "LeafObjectBuilder", "build"),
        ("build.leaf_object", "LeafObjectBuilder", "finish"),
        ("build.armature", "ArmatureBuilder", "_leaf_groups"),  # vertex groups and the flutter
    )

    def leaf_time(self, leaves):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(
            levels=3, branches=(0, 50, 30, 10), leaves=leaves, showLeaves=True,
            useRig=True, windAnim=True, leafFlutter=True,
        )  # fmt: skip
        times = []
        with helpers.untraced():
            for _ in range(self.RUNS):
                helpers.reset_scene()
                timer = StageTimer(self, self.STAGES)
                self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
                times.append(timer.total)
                self.doCleanups()
        return min(times)

    def test_leaf_build_is_linear(self):
        half = self.leaf_time(40)
        full = self.leaf_time(80)
        self.assertGreater(half, 0.0)
        self.assertLess(full / half, MAX_RATIO, f"leaf stages {half:.3f} s at 40 leaves, {full:.3f} s at 80")


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
                grown = grower(params, random.Random(params.seed)).grow(curve_class(), params.scale)
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
