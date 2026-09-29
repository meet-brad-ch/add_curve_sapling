# SPDX-License-Identifier: GPL-3.0-or-later

"""Default materials: bark, and leaves rendered as Thin Wall (Blender 5.2) so light shines through."""

from typing import Any

import bpy
from bpy.types import Material, Node

from ..model.leaves import LeafShape
from ..model.params import TreeParams
from .leaf_object import LeafObjectBuilder
from .skin_mesh import SkinMeshBuilder
from .tree_curve import TreeCurveBuilder


class MaterialLibrary:
    """Creates the Sapling materials once and reuses them, so edits made to them are kept."""

    LEAF = "Sapling Leaf"
    BARK = "Sapling Bark"
    LEAF_COLOR = (0.1, 0.35, 0.05, 1.0)
    BARK_COLOR = (0.2, 0.13, 0.08, 1.0)

    @classmethod
    def leaf(cls) -> Material:
        """Principled BSDF in Thin Wall mode with thin subsurface scattering.

        Thin Wall renders the leaf as a zero-thickness slab; with subsurface it scatters light
        diffusely through the leaf (translucency) instead of refracting it like glass. Measured with
        a backlit leaf, the side facing the camera gets about 5x brighter in Cycles, 2x in EEVEE.
        """
        material = bpy.data.materials.get(cls.LEAF)
        if material is None:
            material = cls._new(cls.LEAF, cls.LEAF_COLOR, roughness=0.5)
            bsdf = cls._bsdf(material)
            bsdf.inputs["Thin Wall"].default_value = True  # type: ignore[attr-defined]  # stub: NodeSocket base class
            bsdf.inputs["Subsurface Weight"].default_value = 1.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
            # EEVEE: treat the surface as a slab of zero thickness, like Thin Wall in Cycles
            material.thickness_mode = "SLAB"
            cls._output(material).inputs["Thickness"].default_value = 0.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
        return material

    @classmethod
    def bark(cls) -> Material:
        """The shared bark material: a plain brown Principled BSDF, created on first use."""
        material = bpy.data.materials.get(cls.BARK)
        if material is None:
            material = cls._new(cls.BARK, cls.BARK_COLOR, roughness=0.8)
        return material

    @classmethod
    def _new(cls, name: str, color: tuple[float, float, float, float], roughness: float) -> Material:
        material = bpy.data.materials.new(name)
        material.diffuse_color = color  # type: ignore[assignment]  # viewport color
        bsdf = cls._bsdf(material)
        bsdf.inputs["Base Color"].default_value = color  # type: ignore[attr-defined]  # stub: NodeSocket base class
        bsdf.inputs["Roughness"].default_value = roughness  # type: ignore[attr-defined]  # stub: NodeSocket base class
        return material

    @staticmethod
    def _bsdf(material: Material) -> Node:
        return next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")  # type: ignore[union-attr]  # new materials have a node tree

    @staticmethod
    def _output(material: Material) -> Node:
        return next(n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL")  # type: ignore[union-attr]  # new materials have a node tree

    @classmethod
    def assign(cls, result: Any, params: TreeParams) -> None:
        """Bark on the branches (curve and skin mesh); the leaf material on mesh leaves (not instanced).

        `result` is the generator's TreeResult (build/ must not import it): anything with role(name).
        """
        bark = cls.bark()
        for role in (TreeCurveBuilder.ROLE, SkinMeshBuilder.ROLE):
            ob = result.role(role)
            if ob is not None:
                ob.data.materials.append(bark)
        leaves = result.role(LeafObjectBuilder.ROLE)
        if params.leaf_material and leaves is not None and params.leaf_shape in LeafShape.MESH:
            leaves.data.materials.append(cls.leaf())
