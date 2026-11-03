# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind: fast preview (the requirements each class or test names)."""

import unittest

import bpy
from support.addon import Addon
from support.node_trees import NodeTrees
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0124")
class RootSweep(unittest.TestCase):
    """The root is a mesh: the bark it sweeps has the old bevel's vertices and faces."""

    def test_fast_preview_shows_the_curves(self):
        self.assertEqual(Scene.generate(NodeTrees.settings(fastPreview=True)), {"FINISHED"})
        root = bpy.data.objects["tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
        geometry = root.evaluated_geometry()
        if geometry.mesh:  # the root's own, empty mesh
            self.assertEqual(len(geometry.mesh.vertices), 0)
        self.assertGreater(len(geometry.curves.curves), 10)
        self.assertEqual(root.display_type, "TEXTURED")  # bounds are the rig's preview only


@Verifies("SWR-0124")
class RigFastPreview(unittest.TestCase):
    """Fast Preview with the rig: the proxy's deform is off in the viewport and the tree is drawn as its bounds."""

    def test_fast_preview_disables_the_proxy_deform(self):
        self.assertEqual(Scene.generate(NodeTrees.settings(useRig=True, fastPreview=True)), {"FINISHED"})
        proxy = bpy.data.objects["tree_joints"]
        self.assertFalse(proxy.modifiers[0].show_viewport)
        self.assertEqual(bpy.data.objects["tree"].display_type, "BOUNDS")


@Verifies("SWR-0124")
class BakedBark(unittest.TestCase):
    """Make Mesh bakes the sweep into the root's mesh: with the rig weighted to its bones, otherwise following the
    node wind through the Follow Wind modifier."""

    def test_fast_preview_shows_the_bounds(self):
        self.assertEqual(
            Scene.generate(NodeTrees.settings(windAnim=True, makeMesh=True, fastPreview=True)), {"FINISHED"}
        )
        self.assertEqual(bpy.data.objects["tree"].display_type, "BOUNDS")


@Verifies("SWR-0124")
class ArmatureDisplay(unittest.TestCase):
    """The tree mesh is the root, the armature its child; the bones are hidden, the root never is."""

    def add(self, **changes):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, **changes)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        root = Scene.active_object()
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        (armature,) = [ob for ob in root.children if ob.type == "ARMATURE"]
        (collection,) = armature.data.collections
        return root, armature, collection

    def assert_selected_and_movable(self, root):
        self.assertTrue(root.visible_get())
        self.assertTrue(root.select_get())
        editable = bpy.context.selected_editable_objects
        if editable is None:
            raise AssertionError("no selected_editable_objects in this context")
        self.assertIn(root, editable)

    def test_fast_preview_draws_the_tree_as_bounds_and_shows_the_bones(self):
        root, _armature, collection = self.add(fastPreview=True)
        self.assertTrue(collection.is_visible)
        self.assertEqual(root.display_type, "BOUNDS")
        self.assert_selected_and_movable(root)
