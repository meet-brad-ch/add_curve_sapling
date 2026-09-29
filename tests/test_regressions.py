# SPDX-License-Identifier: GPL-3.0-or-later

"""One test per fixed bug. Each one failed before its fix."""

import re
import unittest
from collections import defaultdict

import bpy
import helpers

BONE_NAME = re.compile(r"bone(\d{3})\.(\d{3})$")


def armature():
    return next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")


def tree_curve():
    return next(ob for ob in bpy.data.objects if ob.type == "CURVE" and ob.name.startswith("tree"))


class WindAnimation(unittest.TestCase):
    """Blender 5.0 removed Action.fcurves; wind animation crashed on every 5.x release."""

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useArm=True, armAnim=True, leafAnim=True)
        cls.result = helpers.generate(settings)

    def test_generates(self):
        self.assertEqual(self.result, {"FINISHED"})

    def test_branch_and_leaf_bones_move(self):
        arm = armature()
        scene = bpy.context.scene
        poses = {}
        for frame in (1, 17):
            scene.frame_set(frame)
            poses[frame] = {p.name: tuple(p.rotation_euler) for p in arm.pose.bones}
        moved = {name for name in poses[1] if poses[1][name] != poses[17][name]}
        self.assertTrue(any(n.startswith("bone") for n in moved), "no branch bone moves")
        self.assertTrue(any(n.startswith("leaf") for n in moved), "no leaf bone moves")

    def test_each_leaf_bone_owns_its_x_and_z_sway(self):
        channels = defaultdict(set)
        for fc in helpers.fcurves_of(armature()):
            bone = re.match(r'pose\.bones\["(.+)"\]\.rotation_euler', fc.data_path).group(1)
            channels[bone].add(fc.array_index)
        leaf_bones = [b.name for b in armature().data.bones if b.name.startswith("leaf")]
        self.assertTrue(leaf_bones)
        for name in leaf_bones:
            self.assertEqual(channels[name], {0, 2}, name)


class PruningInterpolation(unittest.TestCase):
    """interpStem: t rounding to the stem top gave index == numSegs -> IndexError (review, v0.3.6)."""

    def test_branch_distribution_near_max(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(prune=True, branchDist=9.6)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
