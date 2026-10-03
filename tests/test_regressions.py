# SPDX-License-Identifier: GPL-3.0-or-later

"""One test per fixed bug. Each one failed before its fix."""

import re
import unittest
from collections import defaultdict

import bpy
import helpers
from mathutils import Vector

BONE_NAME = re.compile(r"bone(\d{3})\.(\d{3})$")


def armature():
    return next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")


def tree_curve():
    return next(ob for ob in bpy.data.objects if ob.type == "CURVE" and ob.name.startswith("tree"))


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
        # fcurve_ensure_for_datablock assigns the action slot itself
        self.assertIsNotNone(armature().animation_data.action_slot)

    def test_branch_bones_move(self):
        arm = armature()
        scene = bpy.context.scene
        poses = {}
        for frame in (1, 17):
            scene.frame_set(frame)
            poses[frame] = {p.name: tuple(p.rotation_euler) for p in arm.pose.bones}
        moved = {name for name in poses[1] if poses[1][name] != poses[17][name]}
        self.assertTrue(any(n.startswith("bone") for n in moved), "no branch bone moves")

    def test_each_bone_owns_its_x_and_z_sway(self):
        channels = defaultdict(set)
        for fc in helpers.fcurves_of(armature()):
            match = re.match(r'pose\.bones\["(.+)"\]\.rotation_euler', fc.data_path)
            self.assertIsNotNone(match, fc.data_path)
            assert match is not None
            bone = match.group(1)
            channels[bone].add(fc.array_index)
            # ungrouped: a grouped F-curve costs Blender about 4 times as much to create on big trees
            self.assertIsNone(fc.group, fc.data_path)
        names = [b.name for b in armature().data.bones]
        self.assertTrue(names)
        for name in names:
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
                settings.update(prune=True, useRig=True, showLeaves=True)
                self.assertEqual(helpers.generate(settings), {"FINISHED"})
                self.assert_bones_on_their_splines()
                self.assertNotIn("sapling_prune_scratch", bpy.data.curves)

    def test_unpruned_bones_on_their_splines(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(useRig=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        self.assert_bones_on_their_splines()


class SecondTree(unittest.TestCase):
    """The skin mesh looked the armature up by the name 'treeArm', so a second tree got the first one's."""

    def test_skin_mesh_uses_its_own_armature(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, makeMesh=True)
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

    result: set[str]

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        # Bone Step only applies together with Make Mesh (armature simplification for the skin mesh)
        settings.update(useRig=True, windAnim=True, makeMesh=True, jointStep=(2, 2, 1, 1))
        cls.result = helpers.generate(settings)

    def test_tail_radius_from_tail_point(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = tree_curve().data.splines
        checked = 0
        for bone in armature().data.bones:
            match = BONE_NAME.match(bone.name)
            if not match:
                continue
            points = splines[int(match.group(1))].bezier_points
            tail = next(p for p in points if (p.co - bone.tail_local).length < 1e-5)
            self.assertAlmostEqual(bone.tail_radius, tail.radius, places=5, msg=bone.name)
            checked += 1
        self.assertGreater(checked, 10)

    def test_trunk_base_bones_do_not_sway(self):
        base = sorted(b.name for b in armature().data.bones if b.name.startswith("bone000."))[:2]
        self.assertEqual(len(base), 2)
        matched = 0
        for fc in helpers.fcurves_of(armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                matched += 1
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")
        self.assertEqual(matched, 4, "X and Z sway curves of both base bones")


class InstancePointLeaves(unittest.TestCase):
    """Instance Points leaves were rotated by vertex normals, which cannot be set since Blender 4.1:
    every leaf was turned by its position instead. Each instance must follow its own leaf normal."""

    def test_instances_follow_leaf_normals(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert")
        helpers.reset_scene()
        card = bpy.data.objects.new("leaf_card", bpy.data.meshes.new("leaf_card"))
        bpy.context.scene.collection.objects.link(card)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj="leaf_card", do_update=True), {"FINISHED"})

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
        level_ends = []
        grower = helpers.module("model.tree").TreeGrower
        original = grower.grow

        def recording(grower_self, *args):
            grown = original(grower_self, *args)
            level_ends.extend(grown.level_ends)
            return grown

        grower.grow = recording
        self.addCleanup(setattr, grower, "grow", original)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, jointLevels=0, jointStep=(1, 2, 1, 1))
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        groups = [g.name for g in bpy.data.objects["leaves"].vertex_groups]
        self.assertTrue(groups)
        last_level_start = level_ends[-2]
        for name in groups:
            self.assertGreaterEqual(int(BONE_NAME.match(name).group(1)), last_level_start, name)

    def test_more_armature_levels_than_parameter_levels(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 6, 3, 2), jointLevels=6, showLeaves=True, useRig=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})


class ScriptCalls(unittest.TestCase):
    """UI-only keywords from a script used to make the operator pass through without a tree."""

    def test_ui_keywords_still_generate(self):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        result = bpy.ops.curve.tree_add(**settings, chooseSet="3", limitImport=False)
        self.assertEqual(result, {"FINISHED"})
        self.assertIn("tree", bpy.data.objects)


class FailFast(unittest.TestCase):
    def test_level_beyond_grown_splines(self):
        grown = helpers.module("model.tree").GrownTree([], [1, 5], None)
        self.assertEqual(grown.level_of(4), 1)
        with self.assertRaisesRegex(IndexError, "beyond the 5 grown splines"):
            grown.level_of(5)

    def test_bone_geometry_must_match_the_bones(self):
        helpers.reset_scene()
        armature = bpy.data.armatures.new("probe")
        ob = bpy.data.objects.new("probe", armature)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        self.addCleanup(bpy.ops.object.mode_set, mode="OBJECT")
        armature.edit_bones.new("extra")  # a bone the geometry does not know
        with self.assertRaisesRegex(RuntimeError, "1 bones for the geometry of 0"):
            helpers.module("build.armature").BoneGeometry().write(armature, 0.001)

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
        from types import SimpleNamespace

        settings = SimpleNamespace(**helpers.operator_defaults(), leafDupliObj="")
        params = helpers.module("model.params").TreeParams(settings)
        self.assertEqual(params.levels, settings.levels)
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

    def test_moving_the_clicked_curve_moves_the_whole_tree(self):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        curve = bpy.data.objects["tree"]  # what a click on the branches selects
        before = {(name, f): self.world_vertices(name, f) for name in ("tree", "leaves") for f in self.FRAMES}

        curve.location += Vector(self.OFFSET)
        bpy.context.view_layer.update()
        for (name, frame), points in before.items():
            with self.subTest(object=name, frame=frame):
                after = self.world_vertices(name, frame)
                self.assertEqual(len(after), len(points))
                worst = max((b - a - Vector(self.OFFSET)).length for a, b in zip(points, after, strict=True))
                self.assertLess(worst, 1e-5, "the part moved away from its bones")


class PrunedAwayStems(unittest.TestCase):
    """Pruning shrank some stems to ~1 cm stubs: invisible, but their leaves floated next to the branches."""

    def search(self, scale):
        search = helpers.module("model.stem_builder").PruningSearch()
        search.scale = scale
        return search

    def test_only_short_stems_at_full_ratio_are_removed(self):
        self.assertTrue(self.search(0.1).removes_stem(1.0))
        self.assertFalse(self.search(0.2).removes_stem(1.0))
        self.assertFalse(self.search(0.1).removes_stem(0.8))  # a partial ratio keeps part of the stem anyway

    def test_removed_stems_keep_only_their_start_point(self):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(prune=True, pruneRatio=1.0, pruneWidth=0.25, useRig=True, windAnim=True, makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        splines = bpy.data.objects["tree"].data.splines
        removed = [i for i, s in enumerate(splines) if i > 0 and len(s.bezier_points) == 1]
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
