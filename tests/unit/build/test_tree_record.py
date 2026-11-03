# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/build: tree record."""

import unittest

import bpy
from support.scene import Scene


class Ownership(unittest.TestCase):
    """Edit Sapling Tree on a name that is not an object, or on an object that is not a tree, fails with the reason."""

    def test_replace_names(self):
        Scene.reset()
        plain = bpy.data.objects.new("plain", None)
        bpy.context.scene.collection.objects.link(plain)
        with self.assertRaisesRegex(RuntimeError, "No object named 'gone'"):
            bpy.ops.curve.tree_add(replace="gone", do_update=True)
        with self.assertRaisesRegex(RuntimeError, "'plain' is not part of a Sapling tree"):
            bpy.ops.curve.tree_add(replace="plain", do_update=True)
