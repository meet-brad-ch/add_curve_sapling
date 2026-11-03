# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/ui: limit import."""

import unittest

import bpy
from support.addon import Addon
from support.scene import Scene


class PresetDefaults(unittest.TestCase):
    """A preset that lacks settings loads with their defaults, and the operator says which ones."""

    def test_limit_import(self):
        settings = Addon.preset_store().load("quaking_aspen")
        settings.values["levels"] = 4
        settings.values["showLeaves"] = True
        settings.limit_import()
        self.assertEqual((settings.values["levels"], settings.values["showLeaves"]), (2, False))


class Presets(unittest.TestCase):
    def store(self):
        return Addon.preset_store()

    def test_limit_import_is_off_by_default(self):
        """With Limit Import on, presets loaded with 2 levels and no leaves, and multi-level trees looked bare."""
        prop = bpy.ops.curve.tree_add.get_rna_type().properties["limitImport"]
        self.assertFalse(prop.default)

    def add_preset(self, **options):
        Scene.reset()
        self.assertEqual(bpy.ops.curve.tree_add(preset="douglas_fir", do_update=True, **options), {"FINISHED"})
        return Addon.module("build.tree_record").TreeRecord.settings(bpy.context.active_object).values

    def test_limit_import_caps_levels_and_hides_leaves(self):
        stored = self.add_preset(limitImport=True)
        preset = self.store().load("douglas_fir").values
        self.assertGreater(preset["levels"], 2)
        self.assertEqual(stored["levels"], 2)
        self.assertFalse(stored["showLeaves"])
