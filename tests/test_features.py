# SPDX-License-Identifier: GPL-3.0-or-later

"""Generator features: several trunks (for tree-gen's species), leaf flutter with Geometry Nodes, ..."""

import itertools
import unittest

import bpy
import helpers


def armature():
    return next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")


def root_of(bone):
    while bone.parent is not None:
        bone = bone.parent
    return bone


class SeveralTrunks(unittest.TestCase):
    """Trunks above 1 grows a clump: further trunks stand on a disc around the first (bamboo)."""

    TRUNKS = 3

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, trunks=cls.TRUNKS, useRig=True, windAnim=True)
        cls.settings = settings
        cls.result = helpers.generate(settings)

    def roots(self):
        return [b for b in armature().data.bones if b.parent is None]

    def test_trunks_stand_on_the_ground_apart(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = bpy.data.objects["tree"].data.splines
        bases = [s.bezier_points[0].co.copy() for s in splines if s.bezier_points[0].co.z == 0.0]
        self.assertEqual(len(bases), self.TRUNKS)
        s = self.settings
        gap = 2.5 * s["scale"] * s["length"][0] * s["ratio"] * s["scale0"]
        for a, b in itertools.combinations(bases, 2):
            self.assertGreaterEqual((a - b).length, gap * 0.999)

    def test_each_trunk_is_a_root_with_its_own_branches(self):
        roots = self.roots()
        self.assertEqual(len(roots), self.TRUNKS)
        branches_per_root = {root.name: 0 for root in roots}
        for bone in armature().data.bones:
            if bone.parent is not None and not bone.use_connect:  # the first bone of a branch
                branches_per_root[root_of(bone).name] += 1
        self.assertTrue(all(count >= 10 for count in branches_per_root.values()), branches_per_root)

    def test_every_trunk_base_stays_still(self):
        base = {b.name for root in self.roots() for b in (root, *root.children) if b.use_connect or b.parent is None}
        base = {name for name in base if name.endswith((".000", ".001"))}
        self.assertGreaterEqual(len(base), self.TRUNKS)
        for fc in helpers.fcurves_of(armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")


class TrunkPlacementFailure(unittest.TestCase):
    """Placing a trunk gives up after a bounded number of tries instead of searching forever (tree-gen hangs)."""

    def test_no_room_is_an_error(self):
        clump = helpers.module("model.branching").TrunkClump
        tries = clump.TRIES
        clump.TRIES = 0  # no try can succeed
        self.addCleanup(setattr, clump, "TRIES", tries)
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=1, trunks=2)
        with self.assertRaisesRegex(RuntimeError, "No room for trunk 2 of 2 after 0 tries"):
            bpy.ops.curve.tree_add(**settings, do_update=True)


def leaf_positions(frame, armature_on=True):
    """The leaves' evaluated vertex positions at a frame (optionally without the Armature modifier)."""
    leaves = bpy.data.objects["leaves"]
    for modifier in leaves.modifiers:
        if modifier.type == "ARMATURE":
            modifier.show_viewport = armature_on
    bpy.context.scene.frame_set(frame)
    evaluated = leaves.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    positions = [v.co.copy() for v in mesh.vertices]
    evaluated.to_mesh_clear()
    return positions


class LeafFlutter(unittest.TestCase):
    """Leaf Animation: one Geometry Nodes modifier turns every leaf about its sprout; no bone per leaf.

    A bone, a vertex group and two F-curves per leaf made big trees take minutes: Blender's cost to create
    each of them grows with how many there already are.
    """

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        cls.result = helpers.generate(settings)
        cls.rest = [v.co.copy() for v in bpy.data.objects["leaves"].data.vertices]
        cls.pivots = [a.vector.copy() for a in bpy.data.objects["leaves"].data.attributes["leaf_pivot"].data]

    def test_no_bone_or_group_per_leaf(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertFalse([b.name for b in armature().data.bones if b.name.startswith("leaf")])
        groups = [g.name for g in bpy.data.objects["leaves"].vertex_groups]
        self.assertTrue(groups)
        self.assertTrue(all(name.startswith("bone") for name in groups), groups[:5])

    def test_flutter_comes_before_the_armature(self):
        self.assertEqual([m.type for m in bpy.data.objects["leaves"].modifiers], ["NODES", "ARMATURE"])

    def test_leaves_move_between_frames(self):
        self.assertNotEqual(leaf_positions(1), leaf_positions(17))

    def test_each_leaf_turns_rigidly_about_its_sprout(self):
        moved = 0
        for frame in (5, 17):
            for rest, now, pivot in zip(self.rest, leaf_positions(frame, armature_on=False), self.pivots, strict=True):
                self.assertAlmostEqual((now - pivot).length, (rest - pivot).length, places=5)
                moved += (now - rest).length > 1e-4
        self.assertGreater(moved, len(self.rest) // 2)


class LeafFlutterOptions(unittest.TestCase):
    def generate(self, **overrides):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        settings.update(overrides)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})

    def test_a_loop_starts_and_ends_at_rest(self):
        self.generate(loopFrames=48)
        rest = [v.co.copy() for v in bpy.data.objects["leaves"].data.vertices]

        def largest_move(frame):  # turning by zero about the sprout can still round in the last bit
            return max((a - b).length for a, b in zip(leaf_positions(frame, armature_on=False), rest, strict=True))

        self.assertLess(largest_move(0), 1e-6)
        self.assertLess(largest_move(48), 1e-6)
        self.assertGreater(largest_move(24), 1e-3)

    def test_no_flutter_without_leaf_animation(self):
        self.generate(leafFlutter=False)
        leaves = bpy.data.objects["leaves"]
        self.assertEqual([m.type for m in leaves.modifiers], ["ARMATURE"])
        self.assertNotIn("leaf_pivot", leaves.data.attributes)

    def test_no_flutter_without_wind(self):
        self.generate(windAnim=False)
        self.assertEqual([m.type for m in bpy.data.objects["leaves"].modifiers], ["ARMATURE"])
