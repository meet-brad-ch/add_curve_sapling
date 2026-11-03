# SPDX-License-Identifier: GPL-3.0-or-later

"""Editing and duplicating: edit (the requirements each class or test names)."""

import unittest
from types import SimpleNamespace

import bpy
from mathutils import Matrix
from support.addon import Addon
from support.console import Console
from support.evaluated import Evaluated
from support.fingerprint import Fingerprint
from support.layout import RecordingLayout
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


class ReEdit(unittest.TestCase):
    """Edit Sapling Tree: regenerate from the settings stored on the tree, in the same place."""

    def generate(self, **overrides):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", **overrides)
        Scene.reset()
        self.instance = Scene.add_leaf_card()
        result = bpy.ops.curve.tree_add(**settings, leafDupliObj=self.instance.name, do_update=True)
        self.assertEqual(result, {"FINISHED"})
        return bpy.context.active_object

    def assert_same_transform(self, a, b):
        self.assertLess((a.to_translation() - b.to_translation()).length, 1e-5)
        self.assertLess(a.to_quaternion().rotation_difference(b.to_quaternion()).angle, 1e-5)
        self.assertLess((a.to_scale() - b.to_scale()).length, 1e-5)

    @Verifies("SWR-0020")
    def test_settings_stored_on_root(self):
        root = self.generate(useRig=True)
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        stored = Addon.stored_settings(root)
        self.assertTrue(stored["useRig"])
        self.assertEqual(stored["leafDupliObj"], Scene.LEAF_CARD)
        tree_id = root["sapling_tree"]
        tagged = sorted(ob.name for ob in bpy.data.objects if ob.get("sapling_tree") == tree_id)
        self.assertEqual(tagged, ["leaves", "tree", "treeArm", "tree_curves", "tree_joints"])

    @Verifies("SWR-0021")
    def test_regenerate_in_place(self):
        root = self.generate()
        before = Fingerprint.scene()
        root.matrix_world = Matrix.Translation((5, 0, 0)) @ Matrix.Rotation(0.5, 4, "Z")
        bpy.context.view_layer.update()
        placed = root.matrix_world.copy()
        card_world = self.instance.matrix_world.copy()
        count = len(bpy.data.objects)

        self.assertEqual(bpy.ops.curve.tree_add("INVOKE_DEFAULT", replace=root.name), {"FINISHED"})

        new_root = bpy.context.active_object
        bpy.context.view_layer.update()
        self.assertEqual(len(bpy.data.objects), count)
        self.assertEqual(new_root.name, "tree")
        self.assert_same_transform(new_root.matrix_world, placed)
        self.assertEqual(self.instance.parent, bpy.data.objects["leaves"])
        self.assert_same_transform(self.instance.matrix_world, card_world)
        self.assertEqual(Fingerprint.scene(), before)

    @Verifies("SWR-0021")
    def test_edit_changes_settings(self):
        root = self.generate()
        splines = len(Evaluated.spline_points())
        self.assertEqual(
            bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **self._stored(), levels=1, do_update=True),
            {"FINISHED"},
        )
        self.assertLess(len(Evaluated.spline_points()), splines)
        self.assertNotIn("tree.001", bpy.data.objects)

    @Verifies("SWR-0031")
    def test_not_a_tree(self):
        Scene.reset()
        ob = bpy.data.objects.new("plain", None)
        bpy.context.scene.collection.objects.link(ob)
        with self.assertRaisesRegex(RuntimeError, "'plain' is not part of a Sapling tree"):
            bpy.ops.curve.tree_add(replace="plain", do_update=True)

    @staticmethod
    def _stored():
        values = Addon.stored_settings(bpy.data.objects["tree"])
        values.pop("levels")
        return values


class Placement(unittest.TestCase):
    @Verifies("SWR-0022")
    def test_bone_parent_is_kept(self):
        Scene.reset()
        self.assertEqual(bpy.ops.object.armature_add(), {"FINISHED"})
        rig = Scene.active_object()
        root = Trees.add()
        root.parent = rig
        root.parent_type = "BONE"
        root.parent_bone = rig.data.bones[0].name
        bpy.context.view_layer.update()
        world = root.matrix_world.copy()

        self.assertEqual(Trees.edit(root), {"FINISHED"})
        new_root = Scene.active_object()
        bpy.context.view_layer.update()
        self.assertEqual((new_root.parent, new_root.parent_type, new_root.parent_bone), (rig, "BONE", "Bone"))
        self.assertLess((new_root.matrix_world.to_translation() - world.to_translation()).length, 1e-5)

    @Verifies("SWR-0022")
    def test_vertex_parent_is_kept(self):
        Scene.reset()
        self.assertEqual(bpy.ops.mesh.primitive_plane_add(location=(2, 0, 1)), {"FINISHED"})
        plane = Scene.active_object()
        root = Trees.add()
        root.parent = plane
        root.parent_type = "VERTEX_3"
        root.parent_vertices = (0, 1, 3)
        bpy.context.view_layer.update()
        world = root.matrix_world.copy()

        self.assertEqual(Trees.edit(root), {"FINISHED"})
        new_root = Scene.active_object()
        bpy.context.view_layer.update()
        link = (new_root.parent, new_root.parent_type, tuple(new_root.parent_vertices))
        self.assertEqual(link, (plane, "VERTEX_3", (0, 1, 3)))
        self.assertLess((new_root.matrix_world.to_translation() - world.to_translation()).length, 1e-5)

    @Verifies("SWR-0022")
    def test_moved_armature_tree_stays_on_edit(self):
        Scene.reset()
        root = Trees.add(useRig=True, windAnim=True)
        self.assertEqual(root.name, "tree")
        root.location = (3.0, 0.0, 1.0)

        self.assertEqual(Trees.edit(root), {"FINISHED"})
        new_root = Scene.active_object()
        self.assertEqual(new_root.name, "tree")
        self.assertEqual(new_root.location.to_tuple(), (3.0, 0.0, 1.0))
        self.assertEqual([ob.name for ob in new_root.children if ob.type == "ARMATURE"], ["treeArm"])

    @Verifies("SWR-0022")
    def test_all_collections_are_kept(self):
        Scene.reset()
        root = Trees.add()
        extra = bpy.data.collections.new("Orchard")
        bpy.context.scene.collection.children.link(extra)
        self.addCleanup(bpy.data.collections.remove, extra)
        extra.objects.link(root)
        expected = sorted(c.name for c in root.users_collection)
        self.assertEqual(len(expected), 2)
        self.assertEqual(Trees.edit(root), {"FINISHED"})
        self.assertEqual(sorted(c.name for c in Scene.active_object().users_collection), expected)

    @Verifies("SWR-0023", "SWR-0024")
    def test_child_of_a_removed_part_is_reported_and_kept(self):
        Scene.reset()
        root = Trees.add(showLeaves=True)
        marker = bpy.data.objects.new("marker", None)
        bpy.context.scene.collection.objects.link(marker)
        marker.parent = bpy.data.objects["leaves"]
        marker.matrix_world = Matrix.Translation((1, 2, 3))
        self.assertEqual(Trees.edit(root, showLeaves=False), {"FINISHED"})  # reports a WARNING
        self.assertIsNone(marker.parent)
        self.assertEqual(marker.matrix_world.to_translation().to_tuple(), (1.0, 2.0, 3.0))


@Verifies("SWR-0024")
class EditReports(unittest.TestCase):
    """Edit Sapling Tree tells the user what it could not keep: objects whose part of the tree is gone, and
    settings an older tree did not store."""

    def test_unparented_objects_are_named(self):
        Scene.reset()
        root = Trees.add(showLeaves=True)
        marker = bpy.data.objects.new("marker", None)
        bpy.context.scene.collection.objects.link(marker)
        marker.parent = bpy.data.objects["leaves"]
        with Console.capture() as console:
            self.assertEqual(Trees.edit(root, showLeaves=False), {"FINISHED"})
        self.assertIn("Left unparented (their part of the tree is gone): marker", "\n".join(console.lines("Warning")))


@Verifies("SWR-0025")
class FailureSafety(unittest.TestCase):
    """A generation that fails part-way leaves nothing behind, and a failed edit keeps the old tree."""

    def fail_during_the_bake(self):
        builder = Addon.module("build.bake").BarkBake
        original = builder.bake

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.bake = failing
        self.addCleanup(setattr, builder, "bake", original)

    def test_failed_edit_keeps_the_old_tree(self):
        Scene.reset()
        root = Trees.add(showLeaves=True)
        before = Fingerprint.scene()
        self.fail_during_the_bake()
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            Trees.edit(root, makeMesh=True)
        self.assertEqual(Fingerprint.scene(), before)


class TreeUi(unittest.TestCase):
    """The sidebar panel and the menu entries, on a generated tree."""

    def panels(self):
        return Addon.module("ui.panels")

    @Verifies("SWR-0026")
    def test_panel_shows_for_tree_parts_only(self):
        root = Trees.add_with_leaves()
        panel = self.panels().TreePanel
        self.assertTrue(panel.poll(SimpleNamespace(mode="OBJECT", active_object=root)))
        self.assertFalse(panel.poll(SimpleNamespace(mode="EDIT_CURVE", active_object=root)))
        self.assertFalse(panel.poll(SimpleNamespace(mode="OBJECT", active_object=None)))
        card = Scene.add_leaf_card()
        self.assertFalse(panel.poll(SimpleNamespace(mode="OBJECT", active_object=card)))

    @Verifies("SWR-0026")
    def test_panel_draws_the_edit_button_for_the_root(self):
        root = Trees.add_with_leaves()
        child = root.children[0]
        layout = RecordingLayout()
        self.panels().TreePanel.draw(SimpleNamespace(layout=layout), SimpleNamespace(active_object=child))
        settings = Addon.stored_settings(root)
        self.assertEqual(layout.labels[0], f"Root: {root.name}")
        self.assertIn(f"Seed: {settings['seed']}", layout.labels[1])
        edit, duplicate = layout.buttons
        self.assertEqual((edit.idname, edit.replace), ("curve.tree_add", root.name))
        self.assertEqual(duplicate.idname, "sapling.tree_duplicate")

    @Verifies("SWR-0030")
    def test_panel_shows_a_broken_record(self):
        """A draw method cannot report: a record that cannot be read shows its reason, and no Edit button."""
        root = Trees.add_with_leaves()
        root[Addon.module("build.tree_record").TreeRecord.SETTINGS] = "{"
        layout = RecordingLayout()
        self.panels().TreePanel.draw(SimpleNamespace(layout=layout), SimpleNamespace(active_object=root))
        self.assertEqual(layout.labels[0], f"Root: {root.name}")
        self.assertIn("Invalid settings JSON", layout.labels[1])
        self.assertEqual(layout.buttons, [])


@Verifies("SWR-0030")
class Ownership(unittest.TestCase):
    def test_broken_record_is_an_error(self):
        Scene.reset()
        root = Trees.add(showLeaves=True)
        del root[Trees.record().SETTINGS]
        leaves = bpy.data.objects["leaves"]
        self.assertFalse(Trees.record().is_tree(leaves))
        with self.assertRaisesRegex(Addon.module("build.tree_record").TreeRecordError, "lost its settings"):
            Trees.record().root_of(leaves)
        with self.assertRaisesRegex(RuntimeError, "lost its settings"):
            bpy.ops.curve.tree_add(replace="leaves", do_update=True)
