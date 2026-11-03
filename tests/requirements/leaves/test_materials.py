# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves and blossoms: materials (the requirements each class or test names)."""

import unittest
import unittest.mock

import bpy
import numpy as np
from support.addon import Addon
from support.materials import Materials
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0085")
class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        """Generate a quaking aspen (2 levels, leaves, blossom rate 0.5, the changes) and return its blossoms object."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_object_material_and_uvs(self):
        blossoms = self.generate()
        record = Addon.module("build.tree_record").TreeRecord
        self.assertEqual(blossoms.parent, bpy.data.objects["tree"])
        self.assertEqual(blossoms[record.ROLE], "blossoms")
        mesh = blossoms.data
        self.assertEqual(len(mesh.polygons) % 25, 0)  # five petals of five quads each
        self.assertEqual([m.name for m in mesh.materials], ["Sapling Blossom"])
        self.assertNotIn("sharp_face", mesh.attributes)
        uv = np.zeros(len(mesh.loops) * 2)
        mesh.uv_layers["blossomUV"].uv.foreach_get("vector", uv)
        self.assertTrue((uv >= 0).all() and (uv <= 1).all())
        self.assertIn("leaves", bpy.data.objects)

    def test_leaf_material_off(self):
        self.assertEqual(len(self.generate(leafMaterial=False).data.materials), 0)


@Verifies("SWR-0085")
class LeafMaterial(unittest.TestCase):
    """Leaf Material gives mesh leaves the Sapling Leaf material and the bark Sapling Bark, also on a baked mesh.
    Instanced leaves keep their object's material, and an existing Sapling Leaf material is used again as it is."""

    def generate(self, **overrides):
        """Generate a quaking aspen with leaves and with the overrides."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, **overrides)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})

    def test_thin_wall_leaves(self):
        self.generate()
        (material,) = bpy.data.objects["leaves"].data.materials
        self.assertEqual(material.name, "Sapling Leaf")
        bsdf = Materials.principled(material)
        self.assertTrue(bsdf.inputs["Thin Wall"].default_value)
        self.assertEqual(bsdf.inputs["Subsurface Weight"].default_value, 1.0)
        self.assertEqual(material.thickness_mode, "SLAB")

    def test_bark_on_the_baked_mesh(self):
        self.generate(useRig=True, makeMesh=True)
        self.assertEqual(Materials.evaluated("tree"), ["Sapling Bark"])
        self.assertEqual([m.name for m in bpy.data.objects["tree"].data.materials], ["Sapling Bark"])

    def test_option_off(self):
        self.generate(leafMaterial=False)
        self.assertEqual(len(bpy.data.objects["leaves"].data.materials), 0)
        self.assertEqual(Materials.evaluated("tree"), ["Sapling Bark"])

    def test_instanced_leaves_keep_their_object_material(self):
        for shape in ("dFace", "dVert"):  # the fixed bug: the leaf material went onto Instance Points leaves
            with self.subTest(shape=shape):
                self.generate(leafShape=shape)
                self.assertEqual(len(bpy.data.objects["leaves"].data.materials), 0)

    def test_existing_material_is_reused_not_reset(self):
        self.generate()
        Materials.principled(bpy.data.materials["Sapling Leaf"]).inputs["Subsurface Weight"].default_value = 0.25
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        self.assertEqual(len([m for m in bpy.data.materials if m.name.startswith("Sapling Leaf")]), 1)
        self.assertEqual(
            Materials.principled(bpy.data.materials["Sapling Leaf"]).inputs["Subsurface Weight"].default_value, 0.25
        )
        self.assertEqual(bpy.data.objects["leaves.001"].data.materials[0].name, "Sapling Leaf")
