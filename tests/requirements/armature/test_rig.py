# SPDX-License-Identifier: GPL-3.0-or-later

"""Armature and baked mesh: rig (the requirements each class or test names)."""

import unittest
import unittest.mock

import bpy
import numpy as np
from mathutils import Vector
from support.addon import Addon
from support.console import Console
from support.evaluated import Evaluated
from support.model import BoneIndex, Model
from support.node_trees import NodeTrees
from support.rigged_tree import RiggedTree
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


@Verifies("SWR-0100")
class RigLevels(unittest.TestCase):
    """Joint Levels and Joint Length thin the rig: level 1 rigs the trunks, level 2 adds their branches, and so on;
    a stem above the levels follows the nearest bone below it, bark and leaves alike."""

    def test_joint_levels_rig_the_trunk_only(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, showLeaves=True, useRig=True, jointLevels=1)
        model = Trees.generated_model(self, settings)
        bone_name = Addon.module("model.stem").BoneName
        splines = {bone_name.spline(b.name) for b in Scene.armature().data.bones}
        self.assertTrue(splines)
        self.assertLess(max(splines), model.grown.level_ends[0], "a branch got bones of its own")
        self.assertEqual(len(Scene.armature().data.bones), self.rig_bones(settings, model))

    @staticmethod
    def rig_bones(settings, model):
        """The bone count of the rig for the settings and the grown model."""
        return Addon.module("build.armature").RigSize.bones(Model.joints(settings, model))

    def test_joint_length_thins_the_rig(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True, jointLevels=2, jointStep=(2, 3, 1, 1))
        model = Trees.generated_model(self, settings)
        bone_name = Addon.module("model.stem").BoneName
        for bone in Scene.armature().data.bones:
            spline = bone_name.spline(bone.name)
            step = 2 if spline < model.grown.level_ends[0] else 3
            self.assertEqual(bone_name.point(bone.name) % step, 0, bone.name)
        self.assertEqual(len(Scene.armature().data.bones), self.rig_bones(settings, model))

    def test_bark_above_the_joint_levels_follows_the_bones(self):
        """Joint Levels 1 with wind: the bark of the branches (no bones of their own) sways with the trunk's bones."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=3, branches=(0, 20, 5, 0), useRig=True, windAnim=True, jointLevels=1)
        model = Trees.generated_model(self, settings)
        moved = np.linalg.norm(Evaluated.vertices("tree", 17) - Evaluated.vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the bark moves")
        splines = {BoneIndex.of(b.name).spline for b in Scene.armature().data.bones}
        beyond_trunk = [spline for spline in splines if spline >= model.grown.level_ends[0]]
        self.assertEqual(beyond_trunk, [], "only the trunk has bones")


@Verifies("SWR-0100")
class PrunedArmature(unittest.TestCase):
    """Issue #4: armature on a pruned tree raised KeyError; bones must sit on their own spline."""

    def assert_bones_on_their_splines(self):
        """Each bone's head is on a spline that exists, at its own point within 1e-4. At least one bone is checked."""
        splines = Evaluated.spline_points()
        checked = 0
        for bone in Scene.armature().data.bones:
            index = BoneIndex.of(bone.name)
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
                settings = Addon.resolve_preset(preset)
                settings.update(prune=True, useRig=True, showLeaves=True)
                self.assertEqual(Scene.generate(settings), {"FINISHED"})
                self.assert_bones_on_their_splines()

    def test_unpruned_bones_on_their_splines(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(useRig=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        self.assert_bones_on_their_splines()


@Verifies("SWR-0100")
class BoneStep(unittest.TestCase):
    """With Bone Step > 1 a bone spans several points: its tail came from the point after its head instead of
    the point Joint Length segments on, and only one of the two trunk base bones was held still."""

    result: set[str]

    @classmethod
    def setUpClass(cls):
        """Generate a quaking aspen with the rig, wind and Joint Length 2, 2, 1, 1 once for all tests."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, jointStep=(2, 2, 1, 1))
        cls.result = Scene.generate(settings)

    def test_tail_at_the_point_joint_length_after_the_head(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = Evaluated.spline_points()
        checked = 0
        for bone in Scene.armature().data.bones:
            index = BoneIndex.of(bone.name)
            if index is None:
                continue
            points = splines[index.spline]
            tail = min(index.point + 2, len(points) - 1)  # Joint Length 2 on the first two levels
            self.assertLess((Vector(points[tail][0]) - bone.tail_local).length, 1e-5, bone.name)
            checked += 1
        self.assertGreater(checked, 10)


@Verifies("SWR-0100")
class ArmatureLevels(unittest.TestCase):
    """Armature Levels 0 ("all levels") read jointStep[-1] (the 4th level's step) for the leaves, so
    with Make Mesh they hung on the parent branch's bones; above 4 levels it indexed past jointStep."""

    def test_all_levels_leaves_hang_on_their_own_branch(self):
        captured = Model.record_growth(self)
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, jointLevels=0, jointStep=(1, 2, 1, 1))
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        groups = [g.name for g in bpy.data.objects["leaves"].vertex_groups]
        self.assertTrue(groups)
        last_level_start = captured[-1].grown.level_ends[-2]
        for name in groups:
            self.assertGreaterEqual(BoneIndex.of(name).spline, last_level_start, name)

    def test_more_armature_levels_than_parameter_levels(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 6, 3, 2), jointLevels=6, showLeaves=True, useRig=True, makeMesh=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        # Joint Levels above the tree's levels rig every level: every spline with two points or more has bones
        rigged = {BoneIndex.of(b.name).spline for b in Scene.armature().data.bones}
        drawn = {i for i, points in enumerate(Evaluated.spline_points()) if len(points) > 1}
        self.assertEqual(rigged, drawn)


@Verifies("SWR-0100")
class FiveLevelRig(unittest.TestCase):
    """A stem of the fifth level or deeper hung from its parent's bone rounded with the Joint Length of the level
    above its own: with Joint Length 1, 1, 1, 2 that bone did not exist (KeyError), or it was the wrong bone."""

    STEPS = (1, 1, 1, 2)

    def test_first_bones_hang_from_the_parents_nearest_joint(self):
        captured = Model.record_growth(self)
        settings = Addon.resolve_preset("quaking_aspen.py")
        # four segments on the fourth level: its children hang at odd points too, between its joints
        settings.update(levels=5, branches=(0, 6, 3, 2), curveRes=(3, 5, 3, 4), jointLevels=0, jointStep=self.STEPS)
        settings.update(useRig=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        grown = captured[-1].grown
        bones = {bone.name: bone for bone in Scene.armature().data.bones}
        bone_name = Addon.module("model.stem").BoneName
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


@Verifies("SWR-0101")
class RigSweep(unittest.TestCase):
    """With the rig, the bark is still the live sweep: its points and handles are read from the joint proxy, a
    hidden mesh the bones deform through vertex groups."""

    @classmethod
    def setUpClass(cls):
        """Generate the node-tree test tree with the rig and wind once for all tests."""
        cls.result = Scene.generate(NodeTrees.settings(useRig=True, windAnim=True))

    def test_curves_source_and_joint_proxy(self):
        self.assertEqual(self.result, {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual(Evaluated.tree_curves().type, "CURVES")
        proxy = bpy.data.objects["tree_joints"]
        self.assertEqual((proxy.type, proxy.parent, proxy.hide_viewport, proxy.hide_render), ("MESH", root, True, True))
        points = sum(len(c.points) for c in Evaluated.tree_curves().data.curves)
        self.assertEqual(len(proxy.data.vertices), 3 * points)
        self.assertEqual([m.type for m in proxy.modifiers], ["ARMATURE"])
        self.assertEqual(proxy.modifiers[0].object.name, "treeArm")
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        self.assertEqual({g.name for g in proxy.vertex_groups}, bones)
        not_rigid = [v.index for v in proxy.data.vertices if not (len(v.groups) == 1 and v.groups[0].weight == 1.0)]
        self.assertEqual(not_rigid[:5], [], "proxy vertices not in exactly one group at weight 1")
        inputs = Evaluated.modifier_inputs(root)["Sapling Tree"]["inputs"]
        self.assertEqual((inputs["Rig"], inputs["Wind"], inputs["Joints"]), (True, False, "tree_joints"))

    def test_bark_sways_with_the_bones(self):
        swayed = Evaluated.vertices("tree", 17)
        swayed_counts = NodeTrees.counts("tree")
        moved = np.linalg.norm(swayed - Evaluated.vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the bark moves")
        self.assertEqual(NodeTrees.counts("tree"), swayed_counts, "the sway keeps the bark's topology")


@Verifies("SWR-0101")
class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        """Generate a quaking aspen (2 levels, leaves, blossom rate 0.5, the changes) and return its blossoms object."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_rig_moves_the_blossoms(self):
        blossoms = self.generate(useRig=True)
        self.assertIn("Armature", [m.type.title() for m in blossoms.modifiers])
        bones = {bone.name for bone in Scene.armature().data.bones}
        self.assertTrue(blossoms.vertex_groups and {g.name for g in blossoms.vertex_groups} <= bones)
        weights = [len(v.groups) for v in blossoms.data.vertices]
        self.assertEqual(set(weights), {1}, "every vertex follows one bone")


class RigSizeLimits(unittest.TestCase):
    """Blender creates bones in time proportional to the bones already made, so a rig's build time grows with
    the square of its bone count: the operator warns above WARN_BONES and refuses above MAX_BONES."""

    def rig_size(self):
        """The add-on's RigSize class (the bone count limits and the time estimate)."""
        return Addon.module("build.armature").RigSize

    def limit(self, name, value):
        """Set a RigSize limit to the value for this test only (the old value comes back at cleanup)."""
        rig_size = self.rig_size()
        self.addCleanup(setattr, rig_size, name, getattr(rig_size, name))
        setattr(rig_size, name, value)

    @Verifies("SWR-0102")
    def test_check_names_the_count_and_the_settings_that_lower_it(self):
        rig_size = self.rig_size()
        self.assertIsNone(rig_size.check(rig_size.WARN_BONES))
        warning = rig_size.check(rig_size.WARN_BONES + 1)
        for text in ("10,001 bones", "Joint Levels", "Joint Length", "Wind without the rig"):
            self.assertIn(text, warning)
        settings_error = Addon.module("settings").SettingsError
        with self.assertRaisesRegex(settings_error, "40,001 bones.*limit of 40,000"):
            rig_size.check(rig_size.MAX_BONES + 1)

    @Verifies("SWR-0103")
    def test_seconds_follow_the_measured_square_law(self):
        rig_size = self.rig_size()
        measured = rig_size.MEASURED
        self.assertAlmostEqual(rig_size.seconds(measured.bones), measured.seconds)
        self.assertAlmostEqual(rig_size.seconds(measured.bones // 2), measured.seconds / 4)

    @Verifies("SWR-0103")
    def test_big_rig_warns_but_builds(self):
        self.limit("WARN_BONES", 10)
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True)
        with Console.capture() as console:
            result = Scene.generate(settings)
        self.assertEqual(result, {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn(f"{len(Scene.armature().data.bones):,} bones", warnings[0])
        self.assertIn("Joint Levels", warnings[0])

    @Verifies("SWR-0102")
    def test_too_big_rig_fails_before_building_anything(self):
        self.limit("MAX_BONES", 10)
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, useRig=True)
        with self.assertRaisesRegex(RuntimeError, "bones.*limit of 10 .*Joint Levels"):
            Scene.generate(settings)
        self.assertEqual(len(bpy.data.objects), 0)


@Verifies("SWR-0105")
class ArmatureDisplay(unittest.TestCase):
    """The tree mesh is the root, the armature its child; the bones are hidden, the root never is."""

    def test_bones_hidden_tree_selected_and_movable(self):
        tree = RiggedTree.add(self)
        root = tree.root
        armature = tree.armature
        collection = tree.collection
        self.assertEqual(collection.name, "Sapling Bones")
        self.assertFalse(collection.is_visible)
        self.assertEqual(len(collection.bones), len(armature.data.bones))
        self.assertGreater(len(armature.data.bones), 10)
        RiggedTree.assert_selected_and_movable(self, root)

    def test_hidden_bones_still_deform(self):
        RiggedTree.add(self, showLeaves=True, windAnim=True)
        leaves = bpy.data.objects["leaves"]
        scene = bpy.context.scene
        positions = []
        for frame in (1, 17):
            scene.frame_set(frame)
            mesh = leaves.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
            positions.append([v.co.copy() for v in mesh.vertices[:50]])
        self.assertTrue(any((a - b).length > 1e-6 for a, b in zip(*positions, strict=True)), "leaves do not sway")


@Verifies("SWR-0106")
class MoveByTheBranches(unittest.TestCase):
    """Clicking the branches selected the curve, a child of the armature; moving it tore the tree from its bones."""

    OFFSET = (1.0, 2.0, 3.0)

    FRAMES = (1, 17)

    @staticmethod
    def world_vertices(name, frame):
        """The evaluated world positions of the object's mesh vertices at a frame."""
        bpy.context.scene.frame_set(frame)
        ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        points = [ob.matrix_world @ v.co for v in mesh.vertices]
        ob.to_mesh_clear()
        return points

    def test_moving_the_clicked_tree_moves_the_whole_tree(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
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
