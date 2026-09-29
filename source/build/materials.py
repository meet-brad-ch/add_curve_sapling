# SPDX-License-Identifier: GPL-3.0-or-later

"""Default materials: bark, and leaves rendered as Thin Wall (Blender 5.2) so light shines through."""

import bpy

from ..model.leaves import LeafShape
from .leaf_object import LeafObjectBuilder
from .skin_mesh import SkinMeshBuilder
from .tree_curve import TreeCurveBuilder


class MaterialLibrary:
    """Creates the Sapling materials once and reuses them, so edits made to them are kept."""

    LEAF = "Sapling Leaf"
    BARK = "Sapling Bark"
    LEAF_COLOR = (0.1, 0.35, 0.05, 1.0)
    BARK_COLOR = (0.2, 0.13, 0.08, 1.0)

    def leaf(self):
        """Principled BSDF in Thin Wall mode with thin subsurface scattering.

        Thin Wall renders the leaf as a zero-thickness slab; with subsurface it scatters light
        diffusely through the leaf (translucency) instead of refracting it like glass. Measured with
        a backlit leaf, the side facing the camera gets about 5x brighter in Cycles, 2x in EEVEE.
        """
        material = bpy.data.materials.get(self.LEAF)
        if material is None:
            material = self._new(self.LEAF, self.LEAF_COLOR, roughness=0.5)
            bsdf = self._bsdf(material)
            bsdf.inputs["Thin Wall"].default_value = True
            bsdf.inputs["Subsurface Weight"].default_value = 1.0
            # EEVEE: treat the surface as a slab of zero thickness, like Thin Wall in Cycles
            material.thickness_mode = "SLAB"
            self._output(material).inputs["Thickness"].default_value = 0.0
        return material

    def bark(self):
        material = bpy.data.materials.get(self.BARK)
        if material is None:
            material = self._new(self.BARK, self.BARK_COLOR, roughness=0.8)
        return material

    def _new(self, name, color, roughness):
        material = bpy.data.materials.new(name)
        material.diffuse_color = color  # viewport color
        bsdf = self._bsdf(material)
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        return material

    @staticmethod
    def _bsdf(material):
        return next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")

    @staticmethod
    def _output(material):
        return next(n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL")

    def assign(self, result, params):
        """Bark on the branches (curve and skin mesh); the leaf material on mesh leaves (not instanced)."""
        bark = self.bark()
        for role in (TreeCurveBuilder.ROLE, SkinMeshBuilder.ROLE):
            ob = result.role(role)
            if ob is not None:
                ob.data.materials.append(bark)
        leaves = result.role(LeafObjectBuilder.ROLE)
        if params.leaf_material and leaves is not None and params.leaf_shape in LeafShape.MESH:
            leaves.data.materials.append(self.leaf())
