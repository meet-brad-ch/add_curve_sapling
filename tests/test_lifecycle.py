# SPDX-License-Identifier: GPL-3.0-or-later

"""Blender data lifecycle: nothing left behind by removing or regenerating a tree, clean re-register."""

import unittest

import bpy
import helpers

DATA = ("objects", "curves", "meshes", "armatures", "actions")


def counts():
    return {name: len(getattr(bpy.data, name)) for name in DATA}


def full_tree_settings():
    settings = helpers.resolve_preset("quaking_aspen.py")
    settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True, makeMesh=True, prune=True)
    return settings


class DataLifecycle(unittest.TestCase):
    def test_remove_leaves_no_data(self):
        helpers.reset_scene()
        empty = counts()
        self.assertEqual(bpy.ops.curve.tree_add(**full_tree_settings(), do_update=True), {"FINISHED"})
        root = helpers.module("build.tree_record").TreeRecord.root_of(bpy.context.active_object)
        helpers.module("build.tree_record").TreeRecord.remove(root)
        self.assertEqual(counts(), empty)

    def test_regenerate_leaves_no_orphans(self):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.curve.tree_add(**full_tree_settings(), do_update=True), {"FINISHED"})
        after_first = counts()
        materials = len(bpy.data.materials)
        node_groups = len(bpy.data.node_groups)
        root = helpers.active_object()
        stored = helpers.stored_settings(root)
        for _ in range(3):
            result = bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)
            self.assertEqual(result, {"FINISHED"})
            root = helpers.active_object()
        self.assertEqual(counts(), after_first)
        self.assertEqual(len(bpy.data.materials), materials)
        self.assertEqual(len(bpy.data.node_groups), node_groups)


class Registration(unittest.TestCase):
    @staticmethod
    def menu_entries():
        # Menu.append stores the functions on the draw method; there is no public accessor.
        return len(getattr(bpy.types.VIEW3D_MT_curve_add.draw, "_draw_funcs", ()))

    def test_disable_enable_leaves_no_menu_entries(self):
        enabled = self.menu_entries()
        bpy.ops.preferences.addon_disable(module=helpers.MODULE)
        self.addCleanup(bpy.ops.preferences.addon_enable, module=helpers.MODULE)
        self.assertEqual(self.menu_entries(), enabled - 1)
        bpy.ops.preferences.addon_enable(module=helpers.MODULE)
        self.assertEqual(self.menu_entries(), enabled)
