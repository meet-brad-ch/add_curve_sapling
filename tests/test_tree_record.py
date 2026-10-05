# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree ownership, re-editing in place and failure safety."""

import unittest

import bpy
import helpers
from mathutils import Matrix, Vector


def record():
    return helpers.module("build.tree_record").TreeRecord


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

    def test_baked_mesh_is_the_tree_itself(self):
        helpers.reset_scene()
        root = add_tree(makeMesh=True, useRig=False)
        self.assertGreater(len(root.data.vertices), 0)
        self.assertEqual(root.data.name, "tree")
        self.assertNotIn("treemesh", bpy.data.objects)
        self.assertEqual(sorted(ob.name for ob in record().owned(root)), ["leaves", "tree", "tree_curves"])

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

    def fail_during_the_bake(self):
        builder = helpers.module("build.bake").BarkBake
        original = builder.bake

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.bake = failing
        self.addCleanup(setattr, builder, "bake", original)

    def test_failed_add_leaves_nothing(self):
        helpers.reset_scene()
        before = helpers.counts()
        self.fail_during_the_bake()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, prune=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
        self.assertEqual(helpers.counts(), before)

    def test_failed_edit_keeps_the_old_tree(self):
        helpers.reset_scene()
        root = add_tree(showLeaves=True)
        before = helpers.fingerprint()
        self.fail_during_the_bake()
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


class EditReports(unittest.TestCase):
    """Edit Sapling Tree tells the user what it could not keep: objects whose part of the tree is gone, and
    settings an older tree did not store."""

    def test_unparented_objects_are_named(self):
        helpers.reset_scene()
        root = add_tree(showLeaves=True)
        marker = bpy.data.objects.new("marker", None)
        bpy.context.scene.collection.objects.link(marker)
        marker.parent = bpy.data.objects["leaves"]
        with helpers.console_output() as console:
            self.assertEqual(edit(root, showLeaves=False), {"FINISHED"})
        self.assertIn("Left unparented (their part of the tree is gone): marker", "\n".join(console.lines("Warning")))

    def test_settings_an_older_tree_lacks_are_reported_and_listed(self):
        import json

        helpers.reset_scene()
        root = add_tree()
        stored = json.loads(root[record().SETTINGS])
        stored["settings"].pop("rootFlare")
        root[record().SETTINGS] = json.dumps(stored)
        edit_class = helpers.module("build.tree_record").TreeEdit
        found = edit_class(root.name, bpy.context.view_layer).stored(helpers.operator_defaults())
        self.assertEqual(found.missing, ["rootFlare"])
        self.assertIn("rootFlare", found.settings.values)
        with helpers.console_output() as console:
            self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn("does not have 1 settings: rootFlare", warnings[0])


class FailureRollback(unittest.TestCase):
    """A generation that fails after its objects exist removes them, and puts the user's leaf object back."""

    def test_failed_tag_leaves_nothing(self):
        helpers.reset_scene()
        before = helpers.counts()
        tree_record = record()
        original = tree_record.__dict__["tag"]

        def failing(*args):
            raise RuntimeError("injected failure")

        tree_record.tag = classmethod(failing)
        self.addCleanup(setattr, tree_record, "tag", original)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**helpers.resolve_preset("quaking_aspen.py"), do_update=True)
        self.assertEqual(helpers.counts(), before)

    def test_failed_add_restores_the_leaf_object(self):
        helpers.reset_scene()
        holder = bpy.data.objects.new("holder", None)
        bpy.context.scene.collection.objects.link(holder)
        holder.location = (1, 2, 3)
        card = helpers.add_leaf_card()
        card.parent = holder
        bpy.context.view_layer.update()
        world = card.matrix_world.copy()
        builder = helpers.module("build.bake").BarkBake
        original = builder.bake

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.bake = failing
        self.addCleanup(setattr, builder, "bake", original)
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", makeMesh=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True)
        bpy.context.view_layer.update()
        self.assertIs(card.parent, holder)
        self.assertLess((card.matrix_world.to_translation() - world.to_translation()).length, 1e-6)


class DuplicateTree(unittest.TestCase):
    """Duplicating a tree gives a whole, independent tree: Duplicate Sapling Tree copies every part, and after
    Blender's Duplicate (which copies only the selected objects; hidden parts cannot be selected) the add-on
    copies the parts the copy lacks."""

    MOVE = 5.0

    @staticmethod
    def world_box(ob):
        """The evaluated object's world bounds, (2, 3)."""
        evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        corners = [evaluated.matrix_world @ Vector(c) for c in evaluated.bound_box]
        return [[min(c[i] for c in corners) for i in range(3)], [max(c[i] for c in corners) for i in range(3)]]

    def assert_moved(self, original, copy):
        """The copy draws where it stands: its bounds are the original's, moved along x."""
        copy.location.x += self.MOVE
        bpy.context.view_layer.update()
        before, after = self.world_box(original), self.world_box(copy)
        for low_high in range(2):
            self.assertAlmostEqual(after[low_high][0], before[low_high][0] + self.MOVE, places=4)
            self.assertAlmostEqual(after[low_high][2], before[low_high][2], places=4)

    @staticmethod
    def select_only(ob):
        for other in bpy.context.view_layer.objects:
            other.select_set(other == ob)
        bpy.context.view_layer.objects.active = ob

    def assert_whole_copy(self, root, copy):
        """The copy has a part for every part of the original, none shared, all its links inside the copy, a new
        tree id, and it draws where it stands; editing the original leaves it whole."""
        parts = {ob[record().ROLE]: ob for ob in record().owned(root)}
        copies = {ob[record().ROLE]: ob for ob in record().owned(copy)}
        self.assertEqual(sorted(copies), sorted(parts))
        self.assertEqual(len(record().owned(copy)), len(parts), "no part is copied twice")
        self.assertNotEqual(copy[record().ID], root[record().ID])
        self.assertFalse(set(copies.values()) & set(parts.values()))
        for ob in copies.values():
            for modifier in ob.modifiers:
                if modifier.type == "NODES":
                    for item in modifier.node_group.interface.items_tree:
                        if item.item_type != "SOCKET" or item.socket_type != "NodeSocketObject":
                            continue
                        value = getattr(modifier.properties.inputs, item.identifier).value
                        if isinstance(value, bpy.types.Object):
                            self.assertIn(value, copies.values(), f"{ob.name}: {item.name}")
        self.assert_moved(root, copy)
        self.assertEqual(edit(root, seed=7), {"FINISHED"})
        self.assertEqual(sorted(ob[record().ROLE] for ob in record().owned(copy)), sorted(parts))
        self.assertGreater(len(helpers.evaluated_vertices(copy.name)), 0)

    def shift_d(self, selected):
        """Blender's Duplicate of the selected objects, then the depsgraph update that shows the copy."""
        for other in bpy.context.view_layer.objects:
            other.select_set(other in selected)
        bpy.context.view_layer.objects.active = selected[0]
        self.assertEqual(bpy.ops.object.duplicate(), {"FINISHED"})
        bpy.context.view_layer.update()
        return helpers.active_object()

    def test_shift_d_on_the_tree_copies_the_whole_tree(self):
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=True, blossomRate=0.5, windAnim=True, leafFlutter=True)
        self.assert_whole_copy(root, self.shift_d([root]))

    def test_shift_d_of_a_blossom_only_tree_copies_the_blossoms(self):
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=True, blossomRate=1.0, useRig=True, windAnim=True)
        self.assertIn("blossoms", [ob[record().ROLE] for ob in record().owned(root)])
        self.assert_whole_copy(root, self.shift_d([root]))

    def test_shift_d_of_the_whole_hierarchy_copies_nothing_twice(self):
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=True, blossomRate=0.5)
        visible = [ob for ob in record().owned(root) if ob.visible_get()]
        self.assertGreater(len(visible), 1)
        self.assert_whole_copy(root, self.shift_d(visible))

    def test_duplicate_sapling_tree_copies_every_part(self):
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=True, blossomRate=0.5, windAnim=True, leafFlutter=True)
        self.select_only(bpy.data.objects["leaves"])
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        self.assert_whole_copy(root, helpers.active_object())

    def test_duplicate_sapling_tree_copies_the_rig(self):
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=True, useRig=True, windAnim=True)
        self.select_only(root)
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        copies = {ob[record().ROLE]: ob for ob in record().owned(helpers.active_object())}
        for role in ("tree_joints", "leaves"):
            (armature,) = [m.object for m in copies[role].modifiers if m.type == "ARMATURE"]
            self.assertIs(armature, copies["treeArm"])

    def test_duplicate_sapling_tree_copies_a_face_leaf_object(self):
        helpers.reset_scene()
        card = helpers.add_leaf_card()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, leafShape="dFace", leafDupliObj=card.name)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        leaves = bpy.data.objects["leaves"]
        self.select_only(leaves)
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        copy_leaves = next(ob for ob in record().owned(helpers.active_object()) if ob.instance_type == "FACES")
        (copy_card,) = copy_leaves.children
        self.assertIsNot(copy_card, card)
        self.assertIs(copy_card.data, card.data)
        self.assertIs(card.parent, leaves)

    def test_invoke_copies_then_moves(self):
        """From the UI the copy follows the mouse (Move), as Blender's Duplicate does; without a window the move
        does not start and the copy stays where the original is."""
        helpers.reset_scene()
        root = add_tree(levels=2, showLeaves=False)
        self.select_only(root)
        self.assertEqual(bpy.ops.sapling.tree_duplicate("INVOKE_DEFAULT"), {"FINISHED"})
        copy = helpers.active_object()
        self.assertIsNot(copy, root)
        self.assertEqual(copy.matrix_world, root.matrix_world)
