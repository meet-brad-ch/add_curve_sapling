# SPDX-License-Identifier: GPL-3.0-or-later

"""One test per fixed bug. Each one failed before its fix."""

import random
import re
import unittest
from collections import defaultdict
from types import SimpleNamespace

import bpy
import helpers
import numpy as np
from mathutils import Vector


class WindAnimation(unittest.TestCase):
    """Blender 5.0 removed Action.fcurves; wind animation crashed on every 5.x release."""

    result: set[str]

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        cls.result = helpers.generate(settings)

    def test_generates(self):
        self.assertEqual(self.result, {"FINISHED"})
        # fcurve_ensure_for_datablock assigns the action slot itself; a big rig's actions sit in NLA strips
        animation = helpers.armature().animation_data
        strips = [strip for track in animation.nla_tracks for strip in track.strips]
        slots = [animation.action_slot] if animation.action else [strip.action_slot for strip in strips]
        self.assertTrue(slots)
        self.assertTrue(all(slot is not None for slot in slots))

    def test_branch_bones_move(self):
        arm = helpers.armature()
        scene = bpy.context.scene
        poses = {}
        for frame in (1, 17):
            scene.frame_set(frame)
            poses[frame] = {p.name: tuple(p.rotation_euler) for p in arm.pose.bones}
        moved = {name for name in poses[1] if poses[1][name] != poses[17][name]}
        self.assertTrue(any(n.startswith("bone") for n in moved), "no branch bone moves")

    def test_each_bone_owns_its_x_and_z_sway(self):
        channels = defaultdict(set)
        for fc in helpers.fcurves_of(helpers.armature()):
            match = re.match(r'pose\.bones\["(.+)"\]\.rotation_euler', fc.data_path)
            self.assertIsNotNone(match, fc.data_path)
            assert match is not None
            bone = match.group(1)
            channels[bone].add(fc.array_index)
            # ungrouped: a grouped F-curve costs Blender about 4 times as much to create on big trees
            self.assertIsNone(fc.group, fc.data_path)
        names = [b.name for b in helpers.armature().data.bones]
        self.assertTrue(names)
        for name in names:
            self.assertEqual(channels[name], {0, 2}, name)


class PruningInterpolation(unittest.TestCase):
    """interpStem: t rounding to the stem top gave index == numSegs -> IndexError (review, v0.3.6)."""

    def test_branch_distribution_near_max(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(prune=True, branchDist=9.6)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        # every spline is finite, and the branches crowd towards the top of the trunk (Branch Distribution > 1)
        splines = helpers.spline_points()
        self.assertTrue(all(np.isfinite(co).all() for points in splines for co, _radius in points))
        trunk_top = max(co[2] for co, _radius in splines[0])
        starts = [points[0][0][2] for points in splines[1:] if len(points) > 1]
        self.assertGreater(float(np.median(starts)), 0.5 * trunk_top)


class PrunedArmature(unittest.TestCase):
    """Issue #4: armature on a pruned tree raised KeyError; bones must sit on their own spline."""

    def assert_bones_on_their_splines(self):
        splines = helpers.spline_points()
        checked = 0
        for bone in helpers.armature().data.bones:
            index = helpers.bone_index(bone.name)
            if index is None:
                continue
            self.assertLess(index.spline, len(splines), bone.name)
            co = Vector(splines[index.spline][index.point][0])
            self.assertLess((bone.head_local - co).length, 1e-4, bone.name)
            checked += 1
        self.assertGreater(checked, 0)

    def test_prune_with_armature(self):
        for preset in ("callistemon.py", "quaking_aspen.py"):
            with self.subTest(preset=preset):
                settings = helpers.resolve_preset(preset)
                settings.update(prune=True, useRig=True, showLeaves=True)
                self.assertEqual(helpers.generate(settings), {"FINISHED"})
                self.assert_bones_on_their_splines()

    def test_unpruned_bones_on_their_splines(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(useRig=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assert_bones_on_their_splines()


class SecondTree(unittest.TestCase):
    """The skin mesh looked the armature up by the name 'treeArm', so a second tree got the first one's."""

    def test_baked_mesh_uses_its_own_armature(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        for root_name, arm_name in (("tree", "treeArm"), ("tree.001", "treeArm.001")):
            root = bpy.data.objects[root_name]
            modifier = next(m for m in root.modifiers if m.type == "ARMATURE")
            self.assertEqual(modifier.object.name, arm_name, root_name)
            self.assertEqual(bpy.data.objects[arm_name].parent, root, root_name)


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
        return [points[-1][1] for points in helpers.spline_points()]

    def test_close_tip_on_five_levels(self):
        closed = self.tip_radii(True)
        self.assertGreater(closed.count(0.0), self.tip_radii(False).count(0.0))


class BoneStep(unittest.TestCase):
    """With Bone Step > 1 a bone spans several points: its tail came from the point after its head instead of
    the point Joint Length segments on, and only one of the two trunk base bones was held still."""

    result: set[str]

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, jointStep=(2, 2, 1, 1))
        cls.result = helpers.generate(settings)

    def test_tail_at_the_point_joint_length_after_the_head(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = helpers.spline_points()
        checked = 0
        for bone in helpers.armature().data.bones:
            index = helpers.bone_index(bone.name)
            if index is None:
                continue
            points = splines[index.spline]
            tail = min(index.point + 2, len(points) - 1)  # Joint Length 2 on the first two levels
            self.assertLess((Vector(points[tail][0]) - bone.tail_local).length, 1e-5, bone.name)
            checked += 1
        self.assertGreater(checked, 10)

    def test_trunk_base_bones_do_not_sway(self):
        base = sorted(b.name for b in helpers.armature().data.bones if b.name.startswith("bone000."))[:2]
        self.assertEqual(len(base), 2)
        matched = 0
        for fc in helpers.fcurves_of(helpers.armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                matched += 1
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")
        self.assertEqual(matched, 4, "X and Z sway curves of both base bones")


class LargeRigWind(unittest.TestCase):
    """Above WindAnimator.CHUNK bones the wind's F-curves sit in one action per chunk, played by NLA strips. The
    strips spanned frames 1 to 2 (the range of an action whose curves are all F-modifiers) and held their end value
    from then on: the bones did not follow their F-curves (measured at 4,133 bones: 8,246 of 8,266 channels off)."""

    @classmethod
    def setUpClass(cls):
        animator = helpers.module("build.wind").WindAnimator
        cls.addClassCleanup(setattr, animator, "CHUNK", animator.CHUNK)  # runs even if this method fails
        animator.CHUNK = 50  # the test tree's 308 bones take the large-rig path
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True)
        cls.result = helpers.generate(settings)

    def test_strips_span_the_timeline(self):
        self.assertEqual(self.result, {"FINISHED"})
        strips = [strip for track in helpers.armature().animation_data.nla_tracks for strip in track.strips]
        self.assertGreater(len(strips), 1)
        for strip in strips:
            self.assertEqual((strip.frame_start, strip.action_frame_start), (0.0, 0.0), strip.name)
            self.assertGreaterEqual(strip.frame_end, 100_000, strip.name)
            self.assertEqual(strip.action_frame_end, strip.frame_end, strip.name)

    def test_bones_follow_their_f_curves(self):
        arm = helpers.armature()
        curves = {(c.data_path, c.array_index): c for c in helpers.fcurves_of(arm)}
        self.assertEqual(len(curves), 2 * len(arm.data.bones))
        self.assertGreater(len(arm.data.bones), 50, "the rig takes the large-rig path")
        for frame in (17, 60):
            bpy.context.scene.frame_set(frame)
            for bone in arm.pose.bones:
                for index in (0, 2):
                    curve = curves[(f'pose.bones["{bone.name}"].rotation_euler', index)]
                    self.assertAlmostEqual(bone.rotation_euler[index], curve.evaluate(frame), places=5, msg=bone.name)


class InstancePointLeaves(unittest.TestCase):
    """Instance Points leaves were rotated by vertex normals, which cannot be set since Blender 4.1:
    every leaf was turned by its position instead. Each instance must follow its own leaf normal."""

    def test_instances_follow_leaf_normals(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert")
        helpers.reset_scene()
        card = helpers.add_leaf_card()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True), {"FINISHED"})

        leaves = bpy.data.objects["leaves"]
        rotations = leaves.data.attributes["leaf_rotation"].data
        depsgraph = bpy.context.evaluated_depsgraph_get()
        instances = [
            i.matrix_world.copy()
            for i in depsgraph.object_instances
            if i.is_instance and i.parent and i.parent.name == "leaves"
        ]
        self.assertEqual(len(instances), len(leaves.data.vertices))
        turned = 0
        for matrix, vertex, stored in zip(instances, leaves.data.vertices, rotations, strict=True):
            self.assertLess((matrix.translation - vertex.co).length, 1e-5)
            self.assertLess(matrix.to_quaternion().rotation_difference(stored.value).angle, 1e-4)
            position_rotation = vertex.co.normalized().to_track_quat("Y", "Z")
            turned += position_rotation.rotation_difference(stored.value).angle > 0.01
        self.assertGreater(turned, len(instances) // 2, "rotations still follow the leaf positions")


class LeafObjectSetting(unittest.TestCase):
    """The leaf object used to be a dynamic enum, stored by index: stored trees recorded one of their
    own objects ("envelope") and a missing object silently gave leaves that instance nothing."""

    def test_instanced_leaves_without_object_cancel_before_creating_anything(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace")
        for name in ("", "no_such_object"):
            with self.subTest(leaf_object=name):
                helpers.reset_scene()
                with self.assertRaisesRegex(RuntimeError, "Instanced leaves need a Leaf Object"):
                    bpy.ops.curve.tree_add(**settings, leafDupliObj=name, do_update=True)
                self.assertEqual(len(bpy.data.objects), 0)

    def test_tree_part_is_not_a_leaf_object(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        settings.update(showLeaves=True, leafShape="dVert")
        with self.assertRaisesRegex(RuntimeError, "is part of a Sapling tree"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj="tree", do_update=True)

    def test_stored_leaf_object_is_the_chosen_one(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", prune=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        stored = helpers.stored_settings(helpers.active_object())
        self.assertEqual(stored["leafDupliObj"], helpers.LEAF_CARD)


class ArmatureLevels(unittest.TestCase):
    """Armature Levels 0 ("all levels") read jointStep[-1] (the 4th level's step) for the leaves, so
    with Make Mesh they hung on the parent branch's bones; above 4 levels it indexed past jointStep."""

    def test_all_levels_leaves_hang_on_their_own_branch(self):
        captured = helpers.record_growth(self)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, jointLevels=0, jointStep=(1, 2, 1, 1))
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        groups = [g.name for g in bpy.data.objects["leaves"].vertex_groups]
        self.assertTrue(groups)
        last_level_start = captured[-1].grown.level_ends[-2]
        for name in groups:
            self.assertGreaterEqual(helpers.bone_index(name).spline, last_level_start, name)

    def test_more_armature_levels_than_parameter_levels(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 6, 3, 2), jointLevels=6, showLeaves=True, useRig=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        # Joint Levels above the tree's levels rig every level: every spline with two points or more has bones
        rigged = {helpers.bone_index(b.name).spline for b in helpers.armature().data.bones}
        drawn = {i for i, points in enumerate(helpers.spline_points()) if len(points) > 1}
        self.assertEqual(rigged, drawn)


class ScriptCalls(unittest.TestCase):
    """UI-only keywords from a script used to make the operator pass through without a tree."""

    def test_ui_keywords_still_generate(self):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        result = bpy.ops.curve.tree_add(**settings, chooseSet="3", limitImport=False)
        self.assertEqual(result, {"FINISHED"})
        self.assertIn("tree", bpy.data.objects)


class FailFast(unittest.TestCase):
    def test_bone_geometry_must_match_the_bones(self):
        helpers.reset_scene()
        armature = bpy.data.armatures.new("probe")
        ob = bpy.data.objects.new("probe", armature)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        self.addCleanup(bpy.ops.object.mode_set, mode="OBJECT")
        armature.edit_bones.new("extra")  # a bone the geometry does not know
        none = np.zeros((0, 3), np.float32)
        with self.assertRaisesRegex(RuntimeError, "1 bones for the geometry of 0"):
            helpers.module("build.armature").BoneGeometry(none, none).write(armature)

    def test_foreign_node_group_with_the_instancer_name(self):
        helpers.reset_scene()
        nodes = helpers.module("build.leaf_object").LeafInstancerNodes
        bpy.data.node_groups.new(nodes.GROUP, "ShaderNodeTree")
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert")
        card = helpers.add_leaf_card()
        with self.assertRaisesRegex(RuntimeError, "is not a Geometry Nodes group"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True)
        self.assertEqual([ob.name for ob in bpy.data.objects], [card.name])


class ReadOnlyParams(unittest.TestCase):
    """Generation stages share one TreeParams; none of them may change it for the others."""

    def test_params_are_read_only(self):
        settings = helpers.operator_defaults()
        params = helpers.model_params(settings)
        self.assertEqual(params.levels, settings["levels"])
        with self.assertRaisesRegex(AttributeError, "read-only; cannot set levels"):
            params.levels = 1


class MoveByTheBranches(unittest.TestCase):
    """Clicking the branches selected the curve, a child of the armature; moving it tore the tree from its bones."""

    OFFSET = (1.0, 2.0, 3.0)
    FRAMES = (1, 17)

    @staticmethod
    def world_vertices(name, frame):
        bpy.context.scene.frame_set(frame)
        ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        points = [ob.matrix_world @ v.co for v in mesh.vertices]
        ob.to_mesh_clear()
        return points

    def test_moving_the_clicked_tree_moves_the_whole_tree(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        root = bpy.data.objects["tree"]  # what a click on the branches selects: the mesh that draws the bark
        before = {(name, f): self.world_vertices(name, f) for name in ("tree", "leaves") for f in self.FRAMES}

        root.location += Vector(self.OFFSET)
        bpy.context.view_layer.update()
        for (name, frame), points in before.items():
            with self.subTest(object=name, frame=frame):
                after = self.world_vertices(name, frame)
                self.assertEqual(len(after), len(points))
                worst = max((b - a - Vector(self.OFFSET)).length for a, b in zip(points, after, strict=True))
                self.assertLess(worst, 1e-5, "the part moved away from its bones")


class PrunedAwayStems(unittest.TestCase):
    """Pruning shrank some stems to ~1 cm stubs: invisible, but their leaves floated next to the branches."""

    def test_only_short_stems_at_full_ratio_are_removed(self):
        pruning = helpers.module("model.pruning").LevelPruning
        self.assertTrue(pruning.removes(0.1, 1.0))
        self.assertFalse(pruning.removes(0.2, 1.0))
        self.assertFalse(pruning.removes(0.1, 0.8))  # a partial ratio keeps part of the stem anyway

    def test_removed_stems_keep_only_their_start_point(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(prune=True, pruneRatio=1.0, pruneWidth=0.25, useRig=True, windAnim=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        splines = helpers.spline_points()
        removed = [i for i, s in enumerate(splines) if i > 0 and len(s) == 1]
        self.assertGreater(len(removed), 10)
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        self.assertFalse(any(name.startswith(f"bone{i:03d}.") for name in bones for i in removed))

    def test_envelope_is_hidden(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(prune=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        envelope = bpy.data.objects["envelope"]
        self.assertTrue(envelope.hide_viewport)
        self.assertTrue(envelope.hide_render)


class FiveLevelRig(unittest.TestCase):
    """A stem of the fifth level or deeper hung from its parent's bone rounded with the Joint Length of the level
    above its own: with Joint Length 1, 1, 1, 2 that bone did not exist (KeyError), or it was the wrong bone."""

    STEPS = (1, 1, 1, 2)

    def test_first_bones_hang_from_the_parents_nearest_joint(self):
        captured = helpers.record_growth(self)
        settings = helpers.resolve_preset("quaking_aspen.py")
        # four segments on the fourth level: its children hang at odd points too, between its joints
        settings.update(levels=5, branches=(0, 6, 3, 2), curveRes=(3, 5, 3, 4), jointLevels=0, jointStep=self.STEPS)
        settings.update(useRig=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        grown = captured[-1].grown
        bones = {bone.name: bone for bone in helpers.armature().data.bones}
        bone_name = helpers.module("model.stem").BoneName
        checked = 0
        for curve in range(grown.level_ends[0], grown.level_ends[-1]):
            first = bones.get(bone_name.of(curve, 0))
            if first is None:  # a stem pruning removed has no bones
                continue
            link = grown.bone_map[curve]
            parent = bone_name.spline(link.bone)
            depth = int(np.searchsorted(grown.level_ends, parent, side="right"))
            step = self.STEPS[min(depth, 3)]
            expected = bone_name.of(parent, (bone_name.point(link.bone) // step) * step)
            self.assertEqual(first.parent.name, expected, f"curve {curve}")
            checked += 1
        self.assertGreater(len(grown.level_ends), 4)
        self.assertGreater(checked, 20)


class SharedRandom(unittest.TestCase):
    """The add-on reseeded Python's shared random module: a tree changed every other user's random numbers."""

    def test_the_shared_random_state_is_untouched(self):
        random.seed(1)
        state = random.getstate()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assertEqual(random.getstate(), state)


class LastLevelBase(unittest.TestCase):
    """The last level has no bare base (its base size is reset to 0), also with 5 levels: the check compared the
    level clamped to 3 with levels - 1, so on deep trees the leaves started above a bare base."""

    def test_leaves_start_near_the_base_of_their_stem(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 10, 6, 4), showLeaves=True, leaves=60, baseSize=0.4, baseSize_s=1.0)
        sprouts = helpers.grow_model(settings).grown.sprouts
        along = sprouts.offset[~sprouts.is_end]
        self.assertGreater(len(along), 50)
        self.assertLess(float(along.min()), 0.2)


class SplitTrunkBranches(unittest.TestCase):
    """A split trunk shares one branch per height among its pieces, as Sapling's per-stem code did: the array
    rewrite grouped the trunk's sprouts by their offset, which each piece measures on its own length, so every
    piece kept its own branch at every height and a birch with two base splits grew 2.7 times the branches."""

    def branches(self, base_splits: int) -> int:
        settings = helpers.resolve_preset("white_birch.py")
        settings.update(levels=2, baseSplits=base_splits, segSplits=(0.0, 0.0, 0.0, 0.0), showLeaves=False)
        ends = helpers.grow_model(settings).grown.level_ends
        return ends[1] - ends[0]

    def test_base_splits_do_not_multiply_the_first_level(self):
        whole, split = self.branches(0), self.branches(2)
        self.assertGreater(whole, 20)
        self.assertLess(split, 1.25 * whole, f"{split} branches on the split trunk, {whole} on the whole one")


class Guards(unittest.TestCase):
    """The internal checks fail with a message naming the cause, instead of a wrong tree or a bare KeyError."""

    def test_unknown_node_group_input(self):
        helpers.reset_scene()
        self.assertEqual(helpers.generate(helpers.resolve_preset("quaking_aspen.py")), {"FINISHED"})
        modifier = bpy.data.objects["tree"].modifiers["Sapling Tree"]
        with self.assertRaisesRegex(RuntimeError, "has no input called 'Bogus'"):
            helpers.module("build.node_groups").SharedNodeGroup.set_input(modifier, "Bogus", 1)

    def test_following_twice_is_an_error(self):
        helpers.reset_scene()
        mesh = bpy.data.meshes.new("probe")
        mesh.vertices.add(1)
        ob = bpy.data.objects.new("probe", mesh)
        mesh.attributes.new("sapling_joint", "INT", "POINT")
        with self.assertRaisesRegex(RuntimeError, "already has a 'sapling_joint' attribute"):
            helpers.module("build.node_wind").NodeWind.follow(ob, ob, np.zeros(1, np.int32))

    def test_sway_for_other_bones(self):
        sway = SimpleNamespace(wind1=np.zeros(2))
        animator = helpers.module("build.wind").WindAnimator(None)
        with self.assertRaisesRegex(RuntimeError, "1 bones for the sway of 2 joints"):
            animator.add_joints(["bone000.000"], sway)

    def test_unknown_leaf_shape(self):
        with self.assertRaisesRegex(ValueError, "unknown leaf shape star"):
            helpers.module("model.leaves").LeafShape.verts_per_leaf("star")

    def test_original_branching_does_not_pick(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(rMode="original")
        pick = helpers.module("model.branching").TrunkPick(helpers.model_params(settings), np.zeros(1, np.uint64))
        one = np.zeros(1, np.int64)
        sprouts = SimpleNamespace(is_end=np.zeros(1, bool), family=one, position=one)
        with self.assertRaisesRegex(ValueError, "does not choose"):
            pick.choose(sprouts, 0.0, np.zeros((1, 3)))

    def test_curve_attribute_of_another_kind(self):
        data = bpy.data.hair_curves.new("probe")
        self.addCleanup(bpy.data.hair_curves.remove, data)
        data.attributes.new("probe", "FLOAT", "POINT")
        with self.assertRaisesRegex(RuntimeError, "attribute probe is FLOAT on POINT, not INT on POINT"):
            helpers.module("build.tree_root").CurveSource._attribute(data, "probe", "INT", "POINT")

    def test_object_factory_rules(self):
        factory = helpers.module("build.objects").ObjectFactory
        with self.assertRaisesRegex(ValueError, "at least one collection"):
            factory([])
        helpers.reset_scene()
        objects = factory([bpy.context.scene.collection])
        self.addCleanup(objects.discard)
        objects.new("probe", None)
        with self.assertRaisesRegex(ValueError, "already has a 'probe' object"):
            objects.new("probe", None)

    def test_baked_joint_numbers_out_of_range(self):
        mesh = bpy.data.meshes.new("probe")
        self.addCleanup(bpy.data.meshes.remove, mesh)
        mesh.vertices.add(2)
        attribute = mesh.attributes.new("sapling_ordinal", "FLOAT", "POINT")
        attribute.data.foreach_set("value", [0.0, 5.0])
        with self.assertRaisesRegex(RuntimeError, "Baked joint numbers 0..5 are outside the 2 joints"):
            helpers.module("build.bake").BarkBake._vertex_ordinals(mesh, 2)
