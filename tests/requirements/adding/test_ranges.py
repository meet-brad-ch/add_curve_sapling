# SPDX-License-Identifier: GPL-3.0-or-later

"""Adding a tree: the setting ranges (the requirements each class names)."""

import unittest

import bpy
from support.addon import Addon
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


@Verifies("SWR-0174")
class SettingRanges(unittest.TestCase):
    """A script value outside a setting's range is kept within the range, as Blender's own operators do."""

    def test_values_outside_the_range_are_clamped(self):
        for name, value, expected in (("levels", 9, 6), ("pruneRatio", 3.0, 1.0), ("leafScale", -2.0, 0.0)):
            with self.subTest(setting=name):
                Scene.reset()
                settings = Addon.resolve_preset("quaking_aspen.py")
                settings[name] = value
                self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
                stored = Addon.stored_settings(Scene.active_object())
                self.assertEqual(stored[name], expected)

    def test_the_tree_grows_the_clamped_levels(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings["levels"] = 9
        model = Trees.generated_model(self, settings)
        self.assertEqual(len(model.grown.level_ends), 6)
