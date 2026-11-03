# SPDX-License-Identifier: GPL-3.0-or-later

"""Performance: performance (the requirements each class or test names)."""

import math
import time
import unittest
from dataclasses import dataclass

import bpy
from support.addon import Addon
from support.coverage import Coverage
from support.evaluated import Evaluated
from support.model import Model
from support.scene import Scene
from support.timing import StageTimer, TimedStage
from support.verifies import Verifies

MAX_RATIO = 2.6


@dataclass(frozen=True)
class BuildTime:
    """A tree's spline count and its shortest build time in seconds."""

    splines: int
    seconds: float


@Verifies("SWR-0162")
class LeafScaling(unittest.TestCase):
    RUNS = 2  # the shortest of these runs counts, which keeps other load on the machine out of the ratio

    STAGES = (
        TimedStage(module="model.leaves", owner="LeafGenerator", method="generate"),
        TimedStage(module="build.leaf_object", owner="LeafObjectBuilder", method="build"),
        TimedStage(module="build.leaf_object", owner="LeafObjectBuilder", method="finish"),
        TimedStage(module="build.armature", owner="ArmatureBuilder", method="_leaf_groups"),  # groups and flutter
    )

    def leaf_time(self, leaves):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(
            levels=3, branches=(0, 50, 30, 10), leaves=leaves, showLeaves=True,
            useRig=True, windAnim=True, leafFlutter=True,
        )  # fmt: skip
        times = []
        with Coverage.untraced():
            for _ in range(self.RUNS):
                Scene.reset()
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


@Verifies("SWR-0163")
class BuildScaling(unittest.TestCase):
    """The whole build (growth, curves, leaves, node wind, baked mesh) grows linearly with the tree.

    Every per-item Blender call used to cost time in proportion to the items already made, so trees of 20,000
    stems took about a minute; the model now grows in memory and every part is written in bulk.
    """

    MAX_EXPONENT = 1.3  # 1 if linear, 2 if quadratic

    RUNS = 2

    def build(self, branches):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(
            levels=3, branches=(0, branches, 30, 10), showLeaves=True,
            windAnim=True, leafFlutter=True, makeMesh=True,
        )  # fmt: skip
        times = []
        with Coverage.untraced():
            for _ in range(self.RUNS):
                Scene.reset()
                started = time.perf_counter()
                self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
                times.append(time.perf_counter() - started)
        return BuildTime(splines=len(Evaluated.spline_points()), seconds=min(times))

    def test_build_is_linear(self):
        small_build = self.build(25)
        big_build = self.build(100)
        small_stems = small_build.splines
        small = small_build.seconds
        big_stems = big_build.splines
        big = big_build.seconds
        exponent = math.log(big / small) / math.log(big_stems / small_stems)
        measured = f"{small_stems} stems {small:.2f} s, {big_stems} stems {big:.2f} s"
        self.assertLess(exponent, self.MAX_EXPONENT, measured)


@Verifies("SWR-0164")
class ModelSpeed(unittest.TestCase):
    """The array model grows the test tree (Quaking Aspen, 1,336 stems) in well under a tenth of a second."""

    LIMIT = 0.1

    RUNS = 3

    def test_quaking_aspen_model(self):
        import random

        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, branches=(0, 100, 30, 10))
        params = Model.params(settings)
        grower = Addon.module("model.tree").TreeGrower
        curve_class = Addon.module("model.curve_data").CurveData
        times = []
        with Coverage.untraced():
            for _ in range(self.RUNS):
                started = time.perf_counter()
                grown = grower(params, random.Random(params.seed)).grow(curve_class(), params.scale)
                times.append(time.perf_counter() - started)
        self.assertGreater(grown.level_ends[-1], 1000)
        print(f"model time {min(times):.3f} s for {grown.level_ends[-1]} stems (limit {self.LIMIT} s)", flush=True)
        self.assertLess(min(times), self.LIMIT, f"model time {min(times):.3f} s for {grown.level_ends[-1]} stems")
