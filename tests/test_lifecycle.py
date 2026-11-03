# SPDX-License-Identifier: GPL-3.0-or-later

"""Blender data lifecycle: nothing left behind by removing or regenerating a tree, clean re-register."""

import unittest

import bpy
from support.addon import Addon
from support.scene import Scene
from support.trees import Trees


class DataLifecycle(unittest.TestCase):
    def test_remove_leaves_no_data(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                Scene.reset()
                empty = Scene.counts()
                self.assertEqual(bpy.ops.curve.tree_add(**Trees.full_settings(rig), do_update=True), {"FINISHED"})
                root = Addon.module("build.tree_record").TreeRecord.root_of(bpy.context.active_object)
                Addon.module("build.tree_record").TreeRecord.remove(root)
                self.assertEqual(Scene.counts(), empty)

    def test_regenerate_leaves_no_orphans(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                self.regenerate_three_times(Trees.full_settings(rig))

    def regenerate_three_times(self, settings):
        Scene.reset()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        kinds = [*Scene.DATA, "materials", "node_groups"]  # materials and node groups are shared, made once
        after_first = Scene.counts(kinds)
        root = Scene.active_object()
        stored = Addon.stored_settings(root)
        for _ in range(3):
            result = bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)
            self.assertEqual(result, {"FINISHED"})
            root = Scene.active_object()
        self.assertEqual(Scene.counts(kinds), after_first)


class Registration(unittest.TestCase):
    @staticmethod
    def menu_entries():
        # Menu.append stores the functions on the draw method; there is no public accessor.
        return len(getattr(bpy.types.VIEW3D_MT_curve_add.draw, "_draw_funcs", ()))

    def test_disable_enable_leaves_no_menu_entries(self):
        enabled = self.menu_entries()
        bpy.ops.preferences.addon_disable(module=Addon.MODULE)
        self.addCleanup(bpy.ops.preferences.addon_enable, module=Addon.MODULE)
        self.assertEqual(self.menu_entries(), enabled - 1)
        bpy.ops.preferences.addon_enable(module=Addon.MODULE)
        self.assertEqual(self.menu_entries(), enabled)


class FailedRegistration(unittest.TestCase):
    """A class that fails to register leaves nothing registered behind it."""

    def test_failed_register_leaves_nothing(self):
        self.addCleanup(bpy.ops.preferences.addon_enable, module=Addon.MODULE)
        bpy.ops.preferences.addon_disable(module=Addon.MODULE)
        original = bpy.utils.register_class

        def failing(klass):
            if klass.__name__ == "SavePresetOperator":
                raise RuntimeError("injected failure")
            original(klass)

        bpy.utils.register_class = failing
        self.addCleanup(setattr, bpy.utils, "register_class", original)
        with self.assertRaises(RuntimeError):
            bpy.ops.preferences.addon_enable(module=Addon.MODULE)
        self.assertIsNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))
        bpy.utils.register_class = original
