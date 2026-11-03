# SPDX-License-Identifier: GPL-3.0-or-later

"""A tree added with the rig, and the checks on its root."""

import unittest
from dataclasses import dataclass
from typing import Any

import bpy

from support.addon import Addon
from support.scene import Scene


@dataclass(frozen=True)
class RiggedTree:
    """A quaking aspen added with the rig: the tree mesh (the root), its armature and the one bone collection."""

    root: Any
    armature: Any
    collection: Any

    @classmethod
    def add(cls, test: unittest.TestCase, **changes) -> "RiggedTree":
        """Add the tree in an empty scene; the test fails unless the root is the tree mesh with one armature."""
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, **changes)
        test.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        root = Scene.active_object()
        test.assertEqual((root.name, root.type), ("tree", "MESH"))
        (armature,) = [ob for ob in root.children if ob.type == "ARMATURE"]
        (collection,) = armature.data.collections
        return cls(root=root, armature=armature, collection=collection)

    @staticmethod
    def assert_selected_and_movable(test: unittest.TestCase, root: Any) -> None:
        """The root is visible, selected and among the objects the user can move."""
        test.assertTrue(root.visible_get())
        test.assertTrue(root.select_get())
        editable = bpy.context.selected_editable_objects
        if editable is None:
            raise AssertionError("no selected_editable_objects in this context")
        test.assertIn(root, editable)
