# SPDX-License-Identifier: GPL-3.0-or-later

"""Build time must grow linearly with the number of leaves, with the armature, wind and Leaf Animation on.

Leaf Animation used to make a bone, a vertex group and two F-curves per leaf; Blender's cost to create each
grows with how many there already are, so doubling the leaves made the leaf part about 4 times slower and
big trees took minutes. Measured now (Quaking Aspen, 3 levels, branches 50/30/10): the leaf part takes
0.125, 0.25 and 0.465 s for 20, 40 and 80 leaves per sprout (9,676 to 38,730 leaves).
"""

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
            useArm=True, armAnim=True, leafAnim=True,
        )  # fmt: skip
        times = []
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
