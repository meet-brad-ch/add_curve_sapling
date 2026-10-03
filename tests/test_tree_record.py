# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree ownership, re-editing in place and failure safety."""

import unittest

import bpy
import helpers
from mathutils import Matrix


def record():
    return helpers.module("build.tree_record").TreeRecord


def counts():
    return {name: len(getattr(bpy.data, name)) for name in ("objects", "curves", "meshes", "armatures", "actions")}


def add_tree(**overrides):
    settings = helpers.resolve_preset("quaking_aspen.py")
    settings.update(overrides)
    result = bpy.ops.curve.tree_add(**settings, do_update=True)
    if result != {"FINISHED"}:
        raise AssertionError(result)
    return helpers.active_object()


def edit(root, **changes):
    """Edit Sapling Tree with some settings changed (stored settings + changes)."""
    stored = helpers.stored_settings(root)
    stored.update(changes)
    return bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)


class Ownership(unittest.TestCase):
    def test_duplicated_tree_survives_editing_its_twin(self):
        """Duplicating copies the custom properties; editing one copy used to delete both."""
        helpers.reset_scene()
        root = add_tree(showLeaves=True, useRig=True)
        parts = record().owned(root)
        copies = {}
        for ob in parts:  # like Shift+D on the whole tree: custom properties are copied too
            copy = ob.copy()
            copy.data = ob.data.copy()
            bpy.context.scene.collection.objects.link(copy)
            copies[ob.name] = copy
        for ob in parts:
            if ob.parent is not None:
                copies[ob.name].parent = copies[ob.parent.name]
        twin = copies[root.name]
        twin_parts = sorted(ob.name for ob in record().owned(twin))

        self.assertEqual(edit(root, seed=7), {"FINISHED"})
        self.assertEqual(sorted(ob.name for ob in record().owned(twin)), twin_parts)
        self.assertNotEqual(twin[record().ID], helpers.active_object()[record().ID])

    def test_skin_mesh_without_armature_belongs_to_the_tree(self):
        helpers.reset_scene()
        root = add_tree(makeMesh=True, useRig=False)
        mesh = bpy.data.objects["treemesh"]
        self.assertEqual(mesh.parent, root)
        self.assertTrue(record().is_tree(mesh))
        self.assertEqual(record().root_of(mesh), root)
        self.assertNotIn("sharp_face", mesh.data.attributes, "an edge-only skeleton has no faces to shade")

    def test_broken_record_is_an_error(self):
        helpers.reset_scene()
        root = add_tree(showLeaves=True)
        del root[record().SETTINGS]
        leaves = bpy.data.objects["leaves"]
        self.assertFalse(record().is_tree(leaves))
        with self.assertRaisesRegex(helpers.module("build.tree_record").TreeRecordError, "lost its settings"):
            record().root_of(leaves)
        with self.assertRaisesRegex(RuntimeError, "lost its settings"):
            bpy.ops.curve.tree_add(replace="leaves", do_update=True)

    def test_replace_names(self):
        helpers.reset_scene()
        plain = bpy.data.objects.new("plain", None)
        bpy.context.scene.collection.objects.link(plain)
        with self.assertRaisesRegex(RuntimeError, "No object named 'gone'"):
            bpy.ops.curve.tree_add(replace="gone", do_update=True)
        with self.assertRaisesRegex(RuntimeError, "'plain' is not part of a Sapling tree"):
            bpy.ops.curve.tree_add(replace="plain", do_update=True)


class Placement(unittest.TestCase):
    def test_bone_parent_is_kept(self):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.object.armature_add(), {"FINISHED"})
        rig = helpers.active_object()
        root = add_tree()
        root.parent = rig
        root.parent_type = "BONE"
        root.parent_bone = rig.data.bones[0].name
        bpy.context.view_layer.update()
        world = root.matrix_world.copy()

        self.assertEqual(edit(root), {"FINISHED"})
        new_root = helpers.active_object()
        bpy.context.view_layer.update()
        self.assertEqual((new_root.parent, new_root.parent_type, new_root.parent_bone), (rig, "BONE", "Bone"))
        self.assertLess((new_root.matrix_world.to_translation() - world.to_translation()).length, 1e-5)

    def test_vertex_parent_is_kept(self):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.mesh.primitive_plane_add(location=(2, 0, 1)), {"FINISHED"})
        plane = helpers.active_object()
        root = add_tree()
        root.parent = plane
        root.parent_type = "VERTEX_3"
        root.parent_vertices = (0, 1, 3)
        bpy.context.view_layer.update()
        world = root.matrix_world.copy()

        self.assertEqual(edit(root), {"FINISHED"})
        new_root = helpers.active_object()
        bpy.context.view_layer.update()
        link = (new_root.parent, new_root.parent_type, tuple(new_root.parent_vertices))
        self.assertEqual(link, (plane, "VERTEX_3", (0, 1, 3)))
        self.assertLess((new_root.matrix_world.to_translation() - world.to_translation()).length, 1e-5)

    def test_moved_armature_tree_stays_on_edit(self):
        helpers.reset_scene()
        root = add_tree(useRig=True, windAnim=True)
        self.assertEqual(root.name, "tree")
        root.location = (3.0, 0.0, 1.0)

        self.assertEqual(edit(root), {"FINISHED"})
        new_root = helpers.active_object()
        self.assertEqual(new_root.name, "tree")
        self.assertEqual(new_root.location.to_tuple(), (3.0, 0.0, 1.0))
        self.assertEqual([ob.name for ob in new_root.children if ob.type == "ARMATURE"], ["treeArm"])

    def test_all_collections_are_kept(self):
        helpers.reset_scene()
        root = add_tree()
        extra = bpy.data.collections.new("Orchard")
        bpy.context.scene.collection.children.link(extra)
        self.addCleanup(bpy.data.collections.remove, extra)
        extra.objects.link(root)
        expected = sorted(c.name for c in root.users_collection)
        self.assertEqual(len(expected), 2)
        self.assertEqual(edit(root), {"FINISHED"})
        self.assertEqual(sorted(c.name for c in helpers.active_object().users_collection), expected)

    def test_child_of_a_removed_part_is_reported_and_kept(self):
        helpers.reset_scene()
        root = add_tree(showLeaves=True)
        marker = bpy.data.objects.new("marker", None)
        bpy.context.scene.collection.objects.link(marker)
        marker.parent = bpy.data.objects["leaves"]
        marker.matrix_world = Matrix.Translation((1, 2, 3))
        self.assertEqual(edit(root, showLeaves=False), {"FINISHED"})  # reports a WARNING
        self.assertIsNone(marker.parent)
        self.assertEqual(marker.matrix_world.to_translation().to_tuple(), (1.0, 2.0, 3.0))


class FailureSafety(unittest.TestCase):
    """A generation that fails part-way leaves nothing behind, and a failed edit keeps the old tree."""

    def fail_during_skin_mesh(self):
        builder = helpers.module("build.skin_mesh").SkinMeshBuilder
        original = builder.build

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.build = failing
        self.addCleanup(setattr, builder, "build", original)

    def test_failed_add_leaves_nothing(self):
        helpers.reset_scene()
        before = counts()
        self.fail_during_skin_mesh()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, prune=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
        self.assertEqual(counts(), before)

    def test_failed_edit_keeps_the_old_tree(self):
        helpers.reset_scene()
        root = add_tree(showLeaves=True)
        before = helpers.fingerprint()
        self.fail_during_skin_mesh()
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            edit(root, makeMesh=True)
        self.assertEqual(helpers.fingerprint(), before)


class OlderTrees(unittest.TestCase):
    """A tree stores its settings; Edit failed on trees made before a setting existed ("missing [...]")."""

    def test_edit_fills_settings_added_since(self):
        import json

        helpers.reset_scene()
        root = add_tree()
        stored = json.loads(root[record().SETTINGS])
        default = helpers.operator_defaults()["rootFlare"]
        stored["settings"].pop("rootFlare")  # as if the tree came from a version without this setting
        root[record().SETTINGS] = json.dumps(stored)

        self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        self.assertEqual(helpers.stored_settings(helpers.active_object())["rootFlare"], default)
