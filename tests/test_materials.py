# SPDX-License-Identifier: GPL-3.0-or-later

"""Default materials: Thin Wall leaves, bark."""

import unittest

import bpy
import helpers


def principled(material):
    return next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")


class LeafMaterial(unittest.TestCase):
    def generate(self, **overrides):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, **overrides)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})

    def test_thin_wall_leaves(self):
        self.generate()
        (material,) = bpy.data.objects["leaves"].data.materials
        self.assertEqual(material.name, "Sapling Leaf")
        bsdf = principled(material)
        self.assertTrue(bsdf.inputs["Thin Wall"].default_value)
        self.assertEqual(bsdf.inputs["Subsurface Weight"].default_value, 1.0)
        self.assertEqual(material.thickness_mode, "SLAB")

    def test_bark_on_branches_and_skin_mesh(self):
        self.generate(useArm=True, makeMesh=True)
        for name in ("tree", "treemesh"):
            with self.subTest(object=name):
                self.assertEqual([m.name for m in bpy.data.objects[name].data.materials], ["Sapling Bark"])

    def test_option_off(self):
        self.generate(leafMaterial=False)
        self.assertEqual(len(bpy.data.objects["leaves"].data.materials), 0)
        self.assertEqual(len(bpy.data.objects["tree"].data.materials), 1)

    def test_instanced_leaves_keep_their_object_material(self):
        self.generate(leafShape="dFace")
        self.assertEqual(len(bpy.data.objects["leaves"].data.materials), 0)

    def test_existing_material_is_reused_not_reset(self):
        self.generate()
        principled(bpy.data.materials["Sapling Leaf"]).inputs["Subsurface Weight"].default_value = 0.25
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        self.assertEqual(len([m for m in bpy.data.materials if m.name.startswith("Sapling Leaf")]), 1)
        self.assertEqual(principled(bpy.data.materials["Sapling Leaf"]).inputs["Subsurface Weight"].default_value, 0.25)
        self.assertEqual(bpy.data.objects["leaves.001"].data.materials[0].name, "Sapling Leaf")
