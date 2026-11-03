# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind: flutter (the requirements each class or test names)."""

import unittest

import bpy
from support.addon import Addon
from support.foliage import Foliage
from support.node_trees import NodeTrees
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0122")
class LeafFlutter(unittest.TestCase):
    """Leaf Animation: one Geometry Nodes modifier turns every leaf about its sprout; no bone per leaf.

    A bone, a vertex group and two F-curves per leaf made big trees take minutes: Blender's cost to create
    each of them grows with how many there already are.
    """

    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        cls.result = Scene.generate(settings)
        cls.rest = [v.co.copy() for v in bpy.data.objects["leaves"].data.vertices]
        cls.pivots = [a.vector.copy() for a in bpy.data.objects["leaves"].data.attributes["leaf_pivot"].data]

    def test_no_bone_or_group_per_leaf(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertFalse([b.name for b in Scene.armature().data.bones if b.name.startswith("leaf")])
        groups = [g.name for g in bpy.data.objects["leaves"].vertex_groups]
        self.assertTrue(groups)
        self.assertTrue(all(name.startswith("bone") for name in groups), groups[:5])

    def test_flutter_comes_before_the_armature(self):
        self.assertEqual([m.type for m in bpy.data.objects["leaves"].modifiers], ["NODES", "ARMATURE"])

    def test_leaves_move_between_frames(self):
        self.assertNotEqual(Foliage.positions(1), Foliage.positions(17))

    def test_each_leaf_turns_rigidly_about_its_sprout(self):
        moved = 0
        for frame in (5, 17):
            for rest, now, pivot in zip(
                self.rest, Foliage.positions(frame, armature_on=False), self.pivots, strict=True
            ):
                self.assertAlmostEqual((now - pivot).length, (rest - pivot).length, places=5)
                moved += (now - rest).length > 1e-4
        self.assertGreater(moved, len(self.rest) // 2)


@Verifies("SWR-0122")
class LeafFlutterOptions(unittest.TestCase):
    def generate(self, **overrides):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        settings.update(overrides)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})

    def test_no_flutter_without_leaf_animation(self):
        self.generate(leafFlutter=False)
        leaves = bpy.data.objects["leaves"]
        self.assertEqual([m.type for m in leaves.modifiers], ["ARMATURE"])
        self.assertNotIn("leaf_pivot", leaves.data.attributes)

    def test_no_flutter_without_wind(self):
        self.generate(windAnim=False)
        self.assertEqual([m.type for m in bpy.data.objects["leaves"].modifiers], ["ARMATURE"])


@Verifies("SWR-0122")
class NodeWindLeafOptions(unittest.TestCase):
    def test_flutter_comes_before_the_wind(self):
        settings = NodeTrees.settings(showLeaves=True, windAnim=True, leafFlutter=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        names = [m.name for m in bpy.data.objects["leaves"].modifiers]
        self.assertEqual(names[1:], ["Sapling Follow Wind"])
        self.assertEqual(bpy.data.objects["leaves"].modifiers[0].type, "NODES")

    def test_instanced_leaves_follow(self):
        settings = NodeTrees.settings(showLeaves=True, windAnim=True, leafShape="dVert")
        Scene.reset()
        card = Scene.add_leaf_card()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True), {"FINISHED"})
        positions = []
        for frame in (1, 17):
            bpy.context.scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            positions.append([i.matrix_world.translation.copy() for i in depsgraph.object_instances if i.is_instance])
        self.assertEqual(len(positions[0]), len(bpy.data.objects["leaves"].data.vertices))
        self.assertTrue(any((a - b).length > 1e-4 for a, b in zip(*positions, strict=True)))
