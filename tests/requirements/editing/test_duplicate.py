# SPDX-License-Identifier: GPL-3.0-or-later

"""Editing and duplicating: duplicate (the requirements each class or test names)."""

import unittest

import bpy
from mathutils import Vector
from support.addon import Addon
from support.evaluated import Evaluated
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


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
        parts = {ob[Trees.record().ROLE]: ob for ob in Trees.record().owned(root)}
        copies = {ob[Trees.record().ROLE]: ob for ob in Trees.record().owned(copy)}
        self.assertEqual(sorted(copies), sorted(parts))
        self.assertEqual(len(Trees.record().owned(copy)), len(parts), "no part is copied twice")
        self.assertNotEqual(copy[Trees.record().ID], root[Trees.record().ID])
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
        self.assertEqual(Trees.edit(root, seed=7), {"FINISHED"})
        self.assertEqual(sorted(ob[Trees.record().ROLE] for ob in Trees.record().owned(copy)), sorted(parts))
        self.assertGreater(len(Evaluated.vertices(copy.name)), 0)

    def shift_d(self, selected):
        """Blender's Duplicate of the selected objects, then the depsgraph update that shows the copy."""
        for other in bpy.context.view_layer.objects:
            other.select_set(other in selected)
        bpy.context.view_layer.objects.active = selected[0]
        self.assertEqual(bpy.ops.object.duplicate(), {"FINISHED"})
        bpy.context.view_layer.update()
        return Scene.active_object()

    @Verifies("SWR-0027")
    def test_shift_d_on_the_tree_copies_the_whole_tree(self):
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=True, blossomRate=0.5, windAnim=True, leafFlutter=True)
        self.assert_whole_copy(root, self.shift_d([root]))

    @Verifies("SWR-0027")
    def test_shift_d_of_a_blossom_only_tree_copies_the_blossoms(self):
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=True, blossomRate=1.0, useRig=True, windAnim=True)
        self.assertIn("blossoms", [ob[Trees.record().ROLE] for ob in Trees.record().owned(root)])
        self.assert_whole_copy(root, self.shift_d([root]))

    @Verifies("SWR-0027")
    def test_shift_d_of_the_whole_hierarchy_copies_nothing_twice(self):
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=True, blossomRate=0.5)
        visible = [ob for ob in Trees.record().owned(root) if ob.visible_get()]
        self.assertGreater(len(visible), 1)
        self.assert_whole_copy(root, self.shift_d(visible))

    @Verifies("SWR-0028")
    def test_duplicate_sapling_tree_copies_every_part(self):
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=True, blossomRate=0.5, windAnim=True, leafFlutter=True)
        self.select_only(bpy.data.objects["leaves"])
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        self.assert_whole_copy(root, Scene.active_object())

    @Verifies("SWR-0028")
    def test_duplicate_sapling_tree_copies_the_rig(self):
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=True, useRig=True, windAnim=True)
        self.select_only(root)
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        copies = {ob[Trees.record().ROLE]: ob for ob in Trees.record().owned(Scene.active_object())}
        for role in ("tree_joints", "leaves"):
            (armature,) = [m.object for m in copies[role].modifiers if m.type == "ARMATURE"]
            self.assertIs(armature, copies["treeArm"])

    @Verifies("SWR-0028")
    def test_duplicate_sapling_tree_copies_a_face_leaf_object(self):
        Scene.reset()
        card = Scene.add_leaf_card()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, leafShape="dFace", leafDupliObj=card.name)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        leaves = bpy.data.objects["leaves"]
        self.select_only(leaves)
        self.assertEqual(bpy.ops.sapling.tree_duplicate(), {"FINISHED"})
        copy_leaves = next(ob for ob in Trees.record().owned(Scene.active_object()) if ob.instance_type == "FACES")
        (copy_card,) = copy_leaves.children
        self.assertIsNot(copy_card, card)
        self.assertIs(copy_card.data, card.data)
        self.assertIs(card.parent, leaves)

    @Verifies("SWR-0028")
    def test_invoke_copies_then_moves(self):
        """From the UI the copy follows the mouse (Move), as Blender's Duplicate does; without a window the move
        does not start and the copy stays where the original is."""
        Scene.reset()
        root = Trees.add(levels=2, showLeaves=False)
        self.select_only(root)
        self.assertEqual(bpy.ops.sapling.tree_duplicate("INVOKE_DEFAULT"), {"FINISHED"})
        copy = Scene.active_object()
        self.assertIsNot(copy, root)
        self.assertEqual(copy.matrix_world, root.matrix_world)


@Verifies("SWR-0029")
class Ownership(unittest.TestCase):
    def test_duplicated_tree_survives_editing_its_twin(self):
        """Duplicating copies the custom properties; editing one copy used to delete both."""
        Scene.reset()
        root = Trees.add(showLeaves=True, useRig=True)
        parts = Trees.record().owned(root)
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
        twin_parts = sorted(ob.name for ob in Trees.record().owned(twin))

        self.assertEqual(Trees.edit(root, seed=7), {"FINISHED"})
        self.assertEqual(sorted(ob.name for ob in Trees.record().owned(twin)), twin_parts)
        self.assertNotEqual(twin[Trees.record().ID], Scene.active_object()[Trees.record().ID])
