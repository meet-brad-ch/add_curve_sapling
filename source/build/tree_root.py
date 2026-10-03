# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree's root object (a mesh that draws the bark) and the curves it sweeps.

The root is a Mesh object whose "Sapling Tree" modifier sweeps the tree's curves to the bark: exporters,
selection and rendering treat it as an ordinary mesh. Bevel Depth, Bevel Resolution, Resolution U and Fill Caps
are live inputs of that modifier, and so is its bark Material (a mesh made by Geometry Nodes has no material
slots of its own: the slot of the root's mesh data would not reach the render). The curves live on a hidden child,
"tree_curves", written in bulk from the grown curve: a Curves object (Blender's curves type, which can hold the
node wind's per-point data), or for the armature rig a legacy Curve object, which the rig deforms through its bone
envelopes exactly as before.
"""

from typing import Any

import bpy
import numpy as np
from bpy.types import Curves, Material, NodeSocket, NodeTree, Object

from ..model.curve_data import CurveData
from ..model.params import TreeParams
from .node_groups import SharedNodeGroup
from .node_wind import NodeMath
from .objects import ObjectFactory
from .tree_curve import CurveWriter


class TreeRootBuilder:
    """The root object of a tree: an empty mesh that the "Sapling Tree" modifier fills with the bark."""

    ROLE = "tree"
    MODIFIER = "Sapling Tree"

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self) -> Object:
        """The root, with no geometry of its own yet."""
        return self.objects.new(self.ROLE, bpy.data.meshes.new(self.ROLE))

    @classmethod
    def set_material(cls, root: Object, material: Material) -> None:
        """The bark's material: an input of the root's modifier (its swept mesh carries it, also when applied)."""
        SharedNodeGroup.set_input(root.modifiers[cls.MODIFIER], "Material", material)  # type: ignore[arg-type]  # a root's modifier is a Geometry Nodes modifier

    def sweep(self, root: Object, curves_ob: Object, wind: bool, preview: bool) -> None:
        """The bark: the root's modifier sweeps `curves_ob` (moved by the node wind when `wind`)."""
        p = self.params
        group = SharedNodeGroup.ensure(TreeSweepNodes.GROUP, TreeSweepNodes.VERSION, TreeSweepNodes.build)
        modifier = SharedNodeGroup.add_modifier(root, self.MODIFIER, group)
        values = {
            "Curves": curves_ob,
            "Bevel Depth": p.bevel_depth,
            "Bevel Resolution": p.bevel_res,
            "Resolution U": p.res_u,
            "Fill Caps": False,
            "Fast Preview": preview,
            "Wind": wind,
        }
        for name, value in values.items():
            SharedNodeGroup.set_input(modifier, name, value)


class CurveSource:
    """The hidden child that holds the tree's curves: written in bulk, swept by the root."""

    ROLE = "tree_curves"

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, curve: CurveData, root: Object, rig: bool) -> Object:
        """A legacy Curve object for the rig (its bones deform the points), else a Curves object."""
        ob = self._legacy(curve, root) if rig else self._curves(curve, root)
        # a part the root draws: hidden itself, still evaluated for the root (Object > Visibility shows it again)
        ob.hide_viewport = True
        ob.hide_render = True
        return ob

    def _legacy(self, curve: CurveData, root: Object) -> Object:
        data = bpy.data.curves.new(self.ROLE, "CURVE")
        data.dimensions = "3D"
        data.resolution_u = self.params.res_u
        CurveWriter.write(curve, data)
        return self.objects.new(self.ROLE, data, parent=root)

    def _curves(self, curve: CurveData, root: Object) -> Object:
        data: Curves = bpy.data.hair_curves.new(self.ROLE)
        splines = list(curve.splines)
        for spline in splines:
            spline.ensure_handles()
        data.add_curves([len(spline.co) for spline in splines])
        data.set_types(type="BEZIER")
        data.position_data.foreach_set("vector", self._flat(splines, "co"))
        for name, column in (("handle_left", "left"), ("handle_right", "right")):
            self._attribute(data, name, "FLOAT_VECTOR", "POINT").data.foreach_set("vector", self._flat(splines, column))
        for name, column in (("handle_type_left", "h1"), ("handle_type_right", "h2")):
            values = np.array([t for spline in splines for t in getattr(spline, column)], np.int8)
            self._attribute(data, name, "INT8", "POINT").data.foreach_set("value", values)
        radii = np.array([r for spline in splines for r in spline.radius], np.float32)
        self._attribute(data, "radius", "FLOAT", "POINT").data.foreach_set("value", radii)
        resolution = np.full(len(splines), self.params.res_u, np.int32)
        self._attribute(data, "resolution", "INT", "CURVE").data.foreach_set("value", resolution)
        return self.objects.new(self.ROLE, data, parent=root)

    @staticmethod
    def _attribute(data: Curves, name: str, kind: str, domain: str) -> Any:
        """The attribute, made if the curves do not have it yet (typed Any: its data type depends on `kind`)."""
        return data.attributes.get(name) or data.attributes.new(name, kind, domain)  # type: ignore[arg-type]  # kind and domain are Blender's names, given by the callers

    @staticmethod
    def _flat(splines: list[Any], column: str) -> np.ndarray:
        """A vector column of every spline, flattened."""
        return np.array([c for spline in splines for v in getattr(spline, column) for c in v.to_tuple()], np.float32)


class TreeSweepNodes:
    """The "Sapling Tree" group: the tree's curves (moved by the node wind) swept to the bark.

    As a legacy curve's bevel: a circle of 4 + 2 x Bevel Resolution points, Bevel Depth times each point's
    radius; Resolution U points per segment; no bevel (depth 0) gives the curves as edges. A curve of one point
    (a stem pruning removed) draws nothing, as a legacy curve's bevel. Fast Preview shows the curves themselves
    in the viewport (renders keep the bark).
    """

    GROUP = "Sapling Tree"
    VERSION = 2
    INPUTS = (
        ("Curves", "NodeSocketObject"),
        ("Bevel Depth", "NodeSocketFloat"),
        ("Bevel Resolution", "NodeSocketInt"),
        ("Resolution U", "NodeSocketInt"),
        ("Fill Caps", "NodeSocketBool"),
        ("Fast Preview", "NodeSocketBool"),
        ("Wind", "NodeSocketBool"),
        ("Material", "NodeSocketMaterial"),
    )

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: curves, wind, resolution, sweep, Fast Preview."""
        interface = group.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type typed as 'DEFAULT' only
        for name, kind in cls.INPUTS:
            interface.new_socket(name, in_out="INPUT", socket_type=kind)  # type: ignore[union-attr, arg-type]  # stub: as above
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: as above
        m = NodeMath(group)
        inputs = m.nodes.new("NodeGroupInput").outputs
        info = m.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "RELATIVE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(inputs["Curves"], info.inputs["Object"])
        source = info.outputs["Geometry"]
        moved = m.set_position(source, m.transform_point(m.position(), m.attr("fk_total", "FLOAT4X4")))
        curves = cls._switch(m, inputs["Wind"], source, moved)
        resolution = m.nodes.new("GeometryNodeSetSplineResolution")
        m.link(cls._drop_single_points(m, curves), resolution.inputs["Curve"])
        m.link(inputs["Resolution U"], resolution.inputs["Resolution"])
        bark = cls._bark(m, inputs, resolution.outputs["Curve"])
        viewport = m.nodes.new("GeometryNodeIsViewport").outputs[0]
        preview = m.nodes.new("FunctionNodeBooleanMath")
        preview.operation = "AND"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(inputs["Fast Preview"], preview.inputs[0])
        m.link(viewport, preview.inputs[1])
        m.link(cls._switch(m, preview.outputs[0], bark, curves), m.nodes.new("NodeGroupOutput").inputs["Geometry"])

    @classmethod
    def _bark(cls, m: NodeMath, inputs: Any, curves: NodeSocket) -> NodeSocket:
        """The swept bark (or the curves as edges without bevel), smooth shaded."""
        resample = m.nodes.new("GeometryNodeResampleCurve")
        resample.inputs["Mode"].default_value = "Evaluated"  # type: ignore[attr-defined]  # stub: NodeSocket base class
        m.link(curves, resample.inputs["Curve"])
        evaluated = resample.outputs["Curve"]
        circle = m.nodes.new("GeometryNodeCurvePrimitiveCircle")
        m.link(m.math("ADD", m.math("MULTIPLY", inputs["Bevel Resolution"], 2.0), 4.0), circle.inputs["Resolution"])
        m.link(inputs["Bevel Depth"], circle.inputs["Radius"])
        swept = m.nodes.new("GeometryNodeCurveToMesh")
        m.link(evaluated, swept.inputs["Curve"])
        m.link(circle.outputs["Curve"], swept.inputs["Profile Curve"])
        m.link(m.nodes.new("GeometryNodeInputRadius").outputs[0], swept.inputs["Scale"])
        m.link(inputs["Fill Caps"], swept.inputs["Fill Caps"])
        lines = m.nodes.new("GeometryNodeCurveToMesh")  # no profile: the curves as edges
        m.link(evaluated, lines.inputs["Curve"])
        bevelled = m.math("GREATER_THAN", inputs["Bevel Depth"], 0.0)
        smooth = m.nodes.new("GeometryNodeSetShadeSmooth")
        m.link(cls._switch(m, bevelled, lines.outputs["Mesh"], swept.outputs["Mesh"]), smooth.inputs["Geometry"])
        material = m.nodes.new("GeometryNodeSetMaterial")
        m.link(smooth.outputs["Geometry"], material.inputs["Geometry"])
        m.link(inputs["Material"], material.inputs["Material"])
        return material.outputs["Geometry"]

    @staticmethod
    def _drop_single_points(m: NodeMath, curves: NodeSocket) -> NodeSocket:
        """The curves without those of a single point."""
        count = m.nodes.new("GeometryNodeSplineLength").outputs["Point Count"]
        delete = m.nodes.new("GeometryNodeDeleteGeometry")
        delete.domain = "CURVE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(curves, delete.inputs["Geometry"])
        m.link(m.math("LESS_THAN", count, 2.0), delete.inputs["Selection"])
        return delete.outputs["Geometry"]

    @staticmethod
    def _switch(m: NodeMath, condition: NodeSocket, if_false: NodeSocket, if_true: NodeSocket) -> NodeSocket:
        """A geometry switch."""
        node = m.nodes.new("GeometryNodeSwitch")
        node.input_type = "GEOMETRY"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(condition, node.inputs["Switch"])
        m.link(if_false, node.inputs["False"])
        m.link(if_true, node.inputs["True"])
        return node.outputs[0]
