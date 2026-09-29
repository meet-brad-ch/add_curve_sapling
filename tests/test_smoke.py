# SPDX-License-Identifier: GPL-3.0-or-later

"""The installed extension registers and every built-in preset generates a tree."""

import unittest

import bpy
import helpers
from golden_cases import PRESETS


class Registration(unittest.TestCase):
    def test_operator_registered(self):
        self.assertIsNotNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))
        self.assertIn("seed", helpers.operator_property_names())


class Presets(unittest.TestCase):
    def test_every_preset_generates(self):
        for name in PRESETS:
            with self.subTest(preset=name):
                settings = helpers.resolve_preset(f"{name}.py")
                self.assertEqual(helpers.generate(settings), {"FINISHED"})
                self.assertIn("tree", bpy.data.objects)
