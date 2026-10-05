# SPDX-License-Identifier: GPL-3.0-or-later

"""Default materials: bark, and leaves rendered as Thin Wall (Blender 5.2) so light shines through."""

from dataclasses import dataclass

import bpy
from bpy.types import Material, Mesh, Node

from ..model.leaves import LeafShape
from .build_params import BuildParams
from .leaf_object import LeafObjectBuilder
from .objects import TreeParts
from .tree_root import TreeRootBuilder


@dataclass(frozen=True, slots=True)
class Color:
    """An RGBA colour, each component 0..1."""

    red: float
    green: float
    blue: float
    alpha: float

    @property
    def rgba(self) -> list[float]:
        """The components as Blender's colour properties take them."""
        return [self.red, self.green, self.blue, self.alpha]


class MaterialLibrary:
    """Creates the Sapling materials once and reuses them, so edits made to them are kept."""

    LEAF = "Sapling Leaf"
    BARK = "Sapling Bark"
    LEAF_COLOR = Color(0.1, 0.35, 0.05, 1.0)
    BARK_COLOR = Color(0.2, 0.13, 0.08, 1.0)

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
    def _new(cls, name: str, color: Color, roughness: float) -> Material:
        material = bpy.data.materials.new(name)
        material.diffuse_color = color.rgba  # type: ignore[assignment]  # viewport color
        bsdf = cls._bsdf(material)
        bsdf.inputs["Base Color"].default_value = color.rgba  # type: ignore[attr-defined]  # stub: NodeSocket base class
        bsdf.inputs["Roughness"].default_value = roughness  # type: ignore[attr-defined]  # stub: NodeSocket base class
        return material

    @staticmethod
    def _bsdf(material: Material) -> Node:
        return next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")  # type: ignore[union-attr]  # new materials have a node tree

    @staticmethod
    def _output(material: Material) -> Node:
        return next(n for n in material.node_tree.nodes if n.type == "OUTPUT_MATERIAL")  # type: ignore[union-attr]  # new materials have a node tree

    @classmethod
    def assign(cls, result: TreeParts, params: BuildParams) -> None:
        """Bark on the branches (the root's sweep; a baked mesh keeps it); the leaf material on mesh leaves (not
        instanced)."""
        bark = cls.bark()
        TreeRootBuilder.set_material(result.root, bark)
        leaves = result.role(LeafObjectBuilder.ROLE)
        if params.leaf_material and leaves is not None and params.tree.leaf_shape in LeafShape.MESH:
            mesh: Mesh = leaves.data  # type: ignore[assignment]  # mesh leaves are a mesh object
            mesh.materials.append(cls.leaf())
