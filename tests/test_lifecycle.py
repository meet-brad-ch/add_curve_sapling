# SPDX-License-Identifier: GPL-3.0-or-later

"""Blender data lifecycle: nothing left behind by removing or regenerating a tree, clean re-register."""

import unittest

import bpy
import helpers


def full_tree_settings(rig=True):
    """Everything on, with the armature rig or with the node wind."""
    settings = helpers.resolve_preset("quaking_aspen.py")
    settings.update(showLeaves=True, useRig=rig, windAnim=True, leafFlutter=True, makeMesh=True, prune=True)
    return settings


class DataLifecycle(unittest.TestCase):
    def test_remove_leaves_no_data(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                helpers.reset_scene()
                empty = helpers.counts()
                self.assertEqual(bpy.ops.curve.tree_add(**full_tree_settings(rig), do_update=True), {"FINISHED"})
                root = helpers.module("build.tree_record").TreeRecord.root_of(bpy.context.active_object)
                helpers.module("build.tree_record").TreeRecord.remove(root)
                self.assertEqual(helpers.counts(), empty)

    def test_regenerate_leaves_no_orphans(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                self.regenerate_three_times(full_tree_settings(rig))

    def regenerate_three_times(self, settings):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        kinds = [*helpers.DATA, "materials", "node_groups"]  # materials and node groups are shared, made once
        after_first = helpers.counts(kinds)
        root = helpers.active_object()
        stored = helpers.stored_settings(root)
        for _ in range(3):
            result = bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)
            self.assertEqual(result, {"FINISHED"})
            root = helpers.active_object()
        self.assertEqual(helpers.counts(kinds), after_first)


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


class FailedRegistration(unittest.TestCase):
    """A class that fails to register leaves nothing registered behind it."""

    def test_failed_register_leaves_nothing(self):
        self.addCleanup(bpy.ops.preferences.addon_enable, module=helpers.MODULE)
        bpy.ops.preferences.addon_disable(module=helpers.MODULE)
        original = bpy.utils.register_class

        def failing(klass):
            if klass.__name__ == "SavePresetOperator":
                raise RuntimeError("injected failure")
            original(klass)

        bpy.utils.register_class = failing
        self.addCleanup(setattr, bpy.utils, "register_class", original)
        with self.assertRaises(RuntimeError):
            bpy.ops.preferences.addon_enable(module=helpers.MODULE)
        self.assertIsNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))
        bpy.utils.register_class = original
