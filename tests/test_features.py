# SPDX-License-Identifier: GPL-3.0-or-later

"""Generator features: several trunks (for tree-gen's species), leaf flutter with Geometry Nodes, ..."""

import itertools
import unittest

import bpy
import helpers
import numpy as np
from mathutils import Vector


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
        return [b for b in helpers.armature().data.bones if b.parent is None]

    def test_trunks_stand_on_the_ground_apart(self):
        self.assertEqual(self.result, {"FINISHED"})
        bases = [Vector(s[0][0]) for s in helpers.spline_points() if s[0][0][2] == 0.0]
        self.assertEqual(len(bases), self.TRUNKS)
        s = self.settings
        gap = 2.5 * s["scale"] * s["length"][0] * s["ratio"] * s["scale0"]
        for a, b in itertools.combinations(bases, 2):
            self.assertGreaterEqual((a - b).length, gap * 0.999)

    def test_each_trunk_is_a_root_with_its_own_branches(self):
        roots = self.roots()
        self.assertEqual(len(roots), self.TRUNKS)
        branches_per_root = {root.name: 0 for root in roots}
        for bone in helpers.armature().data.bones:
            if bone.parent is not None and not bone.use_connect:  # the first bone of a branch
                branches_per_root[root_of(bone).name] += 1
        self.assertTrue(all(count >= 10 for count in branches_per_root.values()), branches_per_root)

    def test_every_trunk_base_stays_still(self):
        base = {b.name for root in self.roots() for b in (root, *root.children) if b.use_connect or b.parent is None}
        base = {name for name in base if name.endswith((".000", ".001"))}
        self.assertGreaterEqual(len(base), self.TRUNKS)
        for fc in helpers.fcurves_of(helpers.armature()):
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
    """The leaves' evaluated vertex positions at a frame (optionally without the Armature modifier, which is
    shown again after)."""
    leaves = bpy.data.objects["leaves"]
    armatures = [modifier for modifier in leaves.modifiers if modifier.type == "ARMATURE"]
    shown = [modifier.show_viewport for modifier in armatures]
    for modifier in armatures:
        modifier.show_viewport = armature_on
    try:
        return [Vector(co) for co in helpers.evaluated_vertices("leaves", frame).tolist()]
    finally:
        for modifier, was_shown in zip(armatures, shown, strict=True):
            modifier.show_viewport = was_shown


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
        self.assertFalse([b.name for b in helpers.armature().data.bones if b.name.startswith("leaf")])
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


def generated_model(test, settings):
    """Generate a tree (the result must be FINISHED) and return the model the generator grew for it."""
    captured = helpers.record_growth(test)
    test.assertEqual(helpers.generate(settings), {"FINISHED"})
    return captured[-1]


class RigLevels(unittest.TestCase):
    """Joint Levels and Joint Length thin the rig: level 1 rigs the trunks, level 2 adds their branches, and so on;
    a stem above the levels follows the nearest bone below it, bark and leaves alike."""

    def test_joint_levels_rig_the_trunk_only(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, showLeaves=True, useRig=True, jointLevels=1)
        model = generated_model(self, settings)
        bone_name = helpers.module("model.stem").BoneName
        splines = {bone_name.spline(b.name) for b in helpers.armature().data.bones}
        self.assertTrue(splines)
        self.assertLess(max(splines), model.grown.level_ends[0], "a branch got bones of its own")
        self.assertEqual(len(helpers.armature().data.bones), self.rig_bones(settings, model))

    @staticmethod
    def rig_bones(settings, model):
        return helpers.module("build.armature").RigSize.bones(helpers.joints_of(settings, model))

    def test_joint_length_thins_the_rig(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True, jointLevels=2, jointStep=(2, 3, 1, 1))
        model = generated_model(self, settings)
        bone_name = helpers.module("model.stem").BoneName
        for bone in helpers.armature().data.bones:
            step = 2 if bone_name.spline(bone.name) < model.grown.level_ends[0] else 3
            self.assertEqual(bone_name.point(bone.name) % step, 0, bone.name)
        self.assertEqual(len(helpers.armature().data.bones), self.rig_bones(settings, model))

    def test_bark_above_the_joint_levels_follows_the_bones(self):
        """Joint Levels 1 with wind: the bark of the branches (no bones of their own) sways with the trunk's bones."""
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, branches=(0, 20, 5, 0), useRig=True, windAnim=True, jointLevels=1)
        model = generated_model(self, settings)
        moved = np.linalg.norm(helpers.evaluated_vertices("tree", 17) - helpers.evaluated_vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the bark moves")
        splines = {helpers.bone_index(b.name).spline for b in helpers.armature().data.bones}
        self.assertTrue(all(spline < model.grown.level_ends[0] for spline in splines), "only the trunk has bones")


class RigSizeLimits(unittest.TestCase):
    """Blender creates bones in time proportional to the bones already made, so a rig's build time grows with
    the square of its bone count: the operator warns above WARN_BONES and refuses above MAX_BONES."""

    def rig_size(self):
        return helpers.module("build.armature").RigSize

    def limit(self, name, value):
        rig_size = self.rig_size()
        self.addCleanup(setattr, rig_size, name, getattr(rig_size, name))
        setattr(rig_size, name, value)

    def test_check_names_the_count_and_the_settings_that_lower_it(self):
        rig_size = self.rig_size()
        self.assertIsNone(rig_size.check(rig_size.WARN_BONES))
        warning = rig_size.check(rig_size.WARN_BONES + 1)
        for text in ("10,001 bones", "Joint Levels", "Joint Length", "Wind without the rig"):
            self.assertIn(text, warning)
        settings_error = helpers.module("settings").SettingsError
        with self.assertRaisesRegex(settings_error, "40,001 bones.*limit of 40,000"):
            rig_size.check(rig_size.MAX_BONES + 1)

    def test_seconds_follow_the_measured_square_law(self):
        rig_size = self.rig_size()
        measured = rig_size.MEASURED
        self.assertAlmostEqual(rig_size.seconds(measured.bones), measured.seconds)
        self.assertAlmostEqual(rig_size.seconds(measured.bones // 2), measured.seconds / 4)

    def test_big_rig_warns_but_builds(self):
        self.limit("WARN_BONES", 10)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True)
        with helpers.console_output() as console:
            result = helpers.generate(settings)
        self.assertEqual(result, {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn(f"{len(helpers.armature().data.bones):,} bones", warnings[0])
        self.assertIn("Joint Levels", warnings[0])

    def test_too_big_rig_fails_before_building_anything(self):
        self.limit("MAX_BONES", 10)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True)
        with self.assertRaisesRegex(RuntimeError, "bones.*limit of 10 .*Joint Levels"):
            helpers.generate(settings)
        self.assertEqual(len(bpy.data.objects), 0)
