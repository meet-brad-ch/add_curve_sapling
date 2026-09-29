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


class PrunedArmature(unittest.TestCase):
    """Issue #4: armature on a pruned tree raised KeyError; bones must sit on their own spline."""

    def assert_bones_on_their_splines(self):
        splines = tree_curve().data.splines
        checked = 0
        for bone in armature().data.bones:
            match = BONE_NAME.match(bone.name)
            if not match:
                continue
            spline, point = (int(g) for g in match.groups())
            self.assertLess(spline, len(splines), bone.name)
            co = splines[spline].bezier_points[point].co
            self.assertLess((bone.head_local - co).length, 1e-4, bone.name)
            checked += 1
        self.assertGreater(checked, 0)

    def test_prune_with_armature(self):
        for preset in ("callistemon.py", "quaking_aspen.py"):
            with self.subTest(preset=preset):
                settings = helpers.resolve_preset(preset)
                settings.update(prune=True, useArm=True, showLeaves=True)
                self.assertEqual(helpers.generate(settings), {"FINISHED"})
                self.assert_bones_on_their_splines()
                self.assertNotIn("sapling_prune_scratch", bpy.data.curves)

    def test_unpruned_bones_on_their_splines(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(useArm=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assert_bones_on_their_splines()


class SecondTree(unittest.TestCase):
    """The skin mesh looked the armature up by the name 'treeArm', so a second tree got the first one's."""

    def test_skin_mesh_uses_its_own_armature(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useArm=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        for mesh_name, arm_name in (("treemesh", "treeArm"), ("treemesh.001", "treeArm.001")):
            mesh = bpy.data.objects[mesh_name]
            modifier = next(m for m in mesh.modifiers if m.type == "ARMATURE")
            self.assertEqual(modifier.object.name, arm_name, mesh_name)
            self.assertEqual(mesh.parent.name, arm_name, mesh_name)


class LeafInstanceObject(unittest.TestCase):
    """`leafDupliObj not in "NONE"` was a substring test: objects named N, O, NE, ONE, ... were ignored."""

    def test_short_object_name(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace")
        helpers.reset_scene()
        instance = bpy.data.objects.new("N", bpy.data.meshes.new("N"))
        bpy.context.scene.collection.objects.link(instance)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj="N", do_update=True), {"FINISHED"})
        self.assertEqual(instance.parent, bpy.data.objects["leaves"])


class DeepTrees(unittest.TestCase):
    """The last-level checks compared the level index clamped to 3 with levels - 1, so with 5 or 6
    levels Close Tip and the last level's base size reset never applied."""

    def tip_radii(self, close_tip):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 8, 3, 2), closeTip=close_tip)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        return [s.bezier_points[-1].radius for s in tree_curve().data.splines]

    def test_close_tip_on_five_levels(self):
        closed = self.tip_radii(True)
        self.assertGreater(closed.count(0.0), self.tip_radii(False).count(0.0))


class BoneStep(unittest.TestCase):
    """With Bone Step > 1 a bone spans several points: its tail radius came from the point after its
    head instead of the point at its tail, and only one of the two trunk base bones was held still."""

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        # Bone Step only applies together with Make Mesh (armature simplification for the skin mesh)
        settings.update(useArm=True, armAnim=True, makeMesh=True, boneStep=(2, 2, 1, 1))
        cls.result = helpers.generate(settings)

    def test_tail_radius_from_tail_point(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = tree_curve().data.splines
        for bone in armature().data.bones:
            match = BONE_NAME.match(bone.name)
            if not match:
                continue
            points = splines[int(match.group(1))].bezier_points
            tail = next(p for p in points if (p.co - bone.tail_local).length < 1e-5)
            self.assertAlmostEqual(bone.tail_radius, tail.radius, places=5, msg=bone.name)

    def test_trunk_base_bones_do_not_sway(self):
        base = sorted(b.name for b in armature().data.bones if b.name.startswith("bone000."))[:2]
        self.assertEqual(len(base), 2)
        for fc in helpers.fcurves_of(armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")
