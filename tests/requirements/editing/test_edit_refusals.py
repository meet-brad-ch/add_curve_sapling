# SPDX-License-Identifier: GPL-3.0-or-later

"""Editing: the edits that are refused, and the tree that stays as it was (the requirements each class names)."""

import json
import unittest

import bpy
from support.addon import Addon
from support.scene import Scene
from support.verifies import Verifies


class EditRefusal:
    """An Edit Sapling Tree of a tree, as the sidebar button runs it, that must be refused."""

    @staticmethod
    def edit_error(root_name: str) -> str:
        """The error message of an Edit of the tree `root_name`; raises AssertionError when the Edit is not refused."""
        try:
            result = bpy.ops.curve.tree_add(replace=root_name, load_stored=True, do_update=True)
        except RuntimeError as error:  # the operator's error report: what these tests expect
            return str(error)
        raise AssertionError(f"the edit was not refused: {result}")

    @staticmethod
    def scene_state() -> dict:
        """Every object's name with its parent and its data's name: what a refused edit must leave as it was."""
        state = {}
        for ob in bpy.data.objects:
            parent = None
            if ob.parent is not None:
                parent = ob.parent.name
            data = None
            if ob.data is not None:
                data = ob.data.name
            state[ob.name] = (parent, data)
        return state


@Verifies("SWR-0172")
class MissingLeafObject(unittest.TestCase):
    """An Edit of a tree whose Leaf Object was deleted is refused, names the object, and leaves the tree as it was."""

    def test_the_edit_is_refused(self):
        Scene.reset()
        bpy.ops.mesh.primitive_plane_add(size=0.1)
        leaf = bpy.context.active_object
        leaf.name = "my_leaf"
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert", leafDupliObj="my_leaf")
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        root = Scene.active_object()
        bpy.data.objects.remove(leaf)
        before = EditRefusal.scene_state()
        message = EditRefusal.edit_error(root.name)
        self.assertIn("my_leaf", message)
        self.assertIn("Leaf Object", message)
        self.assertEqual(EditRefusal.scene_state(), before)


@Verifies("SWR-0173")
class OtherSettingsVersion(unittest.TestCase):
    """An Edit of a tree whose stored settings have another version is refused, names that version, and leaves the
    tree as it was."""

    def test_the_edit_is_refused(self):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        root = Scene.active_object()
        record = Addon.module("build.tree_record").TreeRecord
        stored = json.loads(root[record.SETTINGS])
        stored["version"] = 2
        root[record.SETTINGS] = json.dumps(stored)
        before = EditRefusal.scene_state()
        message = EditRefusal.edit_error(root.name)
        self.assertIn("version 2", message)
        self.assertEqual(EditRefusal.scene_state(), before)
