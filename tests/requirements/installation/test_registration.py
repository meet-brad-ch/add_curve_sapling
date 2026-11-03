# SPDX-License-Identifier: GPL-3.0-or-later

"""Installation and compatibility: registration (the requirements each class or test names)."""

import unittest

import bpy
from support.addon import Addon
from support.verifies import Verifies


@Verifies("SWR-0005")
class LifecycleRegistration(unittest.TestCase):
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


@Verifies("SWR-0006")
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


@Verifies("SWR-0005")
class UiRegistration(unittest.TestCase):
    def test_reregister(self):
        self.addCleanup(bpy.ops.preferences.addon_enable, module=Addon.MODULE)  # enabled again if a step fails
        for _ in range(2):
            bpy.ops.preferences.addon_disable(module=Addon.MODULE)
            self.assertFalse(hasattr(bpy.types, "VIEW3D_PT_sapling_tree"))
            bpy.ops.preferences.addon_enable(module=Addon.MODULE)
        self.assertIsNotNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))


@Verifies("SWR-0010")
class SmokeRegistration(unittest.TestCase):
    def test_operator_registered(self):
        self.assertIsNotNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))
        self.assertIn("seed", Addon.operator_property_names())
