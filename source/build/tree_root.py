# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree's root object (a mesh that draws the bark) and the curves it sweeps.

The root is a Mesh object whose "Sapling Tree" modifier sweeps the tree's curves to the bark: exporters,
selection and rendering treat it as an ordinary mesh. Bevel Depth, Bevel Resolution, Resolution U and Fill Caps
are live inputs of that modifier, and so is its bark Material (a mesh made by Geometry Nodes has no material
slots of its own: the slot of the root's mesh data would not reach the render). The curves live on a hidden child,
"tree_curves", a Curves object written in bulk from the grown curve. With the node wind, every point carries its
joint number and the sweep moves it by that joint's transform, read from the wind curves (NodeWind); with the
armature rig, the sweep reads each point's posed position and handles from the joint proxy (JointProxy), which the
rig's bones deform.
"""

from typing import Any

import bpy
import numpy as np
from bpy.types import Curves, Material, NodeSocket, NodeTree, Object

from ..model.curve_data import CurveData
from .build_params import BuildParams
from .node_groups import SharedNodeGroup
from .node_math import NodeMath, SocketSpec
from .node_wind import NodeWind
from .objects import ObjectFactory


class TreeRootBuilder:
    """The root object of a tree: an empty mesh that the "Sapling Tree" modifier fills with the bark."""

    ROLE = "tree"
    MODIFIER = "Sapling Tree"

    def __init__(self, params: BuildParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self) -> Object:
        """The root, with no geometry of its own yet."""
        return self.objects.new(self.ROLE, bpy.data.meshes.new(self.ROLE))

    @classmethod
    def set_material(cls, root: Object, material: Material) -> None:
        """The bark's material: an input of the root's modifier (its swept mesh carries it, also when applied)."""
        SharedNodeGroup.set_input(root.modifiers[cls.MODIFIER], "Material", material)  # type: ignore[arg-type]  # a root's modifier is a Geometry Nodes modifier

    def sweep(
        self, root: Object, curves_ob: Object, wind_ob: Object | None, preview: bool, joints_ob: Object | None
    ) -> None:
        """The bark: the root's modifier sweeps `curves_ob`, moved by the node wind's curves `wind_ob` when given,
        or posed by the rig's joint proxy `joints_ob` when given."""
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
            "Wind": wind_ob is not None,
            "Wind Joints": wind_ob,
            "Rig": joints_ob is not None,
            "Joints": joints_ob,
        }
        for name, value in values.items():
            SharedNodeGroup.set_input(modifier, name, value)


class CurveSource:
    """The hidden child that holds the tree's curves: written in bulk, swept by the root."""

    ROLE = "tree_curves"

    def __init__(self, params: BuildParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, curve: CurveData, root: Object) -> Object:
        """The Curves object under the root, with the grown curve's points, handles, radii and resolution."""
        data: Curves = bpy.data.hair_curves.new(self.ROLE)
        flat = curve.flatten()  # one array per column: each attribute is written in a single foreach_set
        data.add_curves(flat.sizes.tolist())
        data.set_types(type="BEZIER")
        data.position_data.foreach_set("vector", flat.co.ravel())
        self._attribute(data, "handle_left", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", flat.left.ravel())
        self._attribute(data, "handle_right", "FLOAT_VECTOR", "POINT").data.foreach_set("vector", flat.right.ravel())
        self._attribute(data, "handle_type_left", "INT8", "POINT").data.foreach_set("value", flat.h1)
        self._attribute(data, "handle_type_right", "INT8", "POINT").data.foreach_set("value", flat.h2)
        self._attribute(data, "radius", "FLOAT", "POINT").data.foreach_set("value", flat.radius)
        resolution = np.full(len(flat.sizes), self.params.res_u, np.int32)
        self._attribute(data, "resolution", "INT", "CURVE").data.foreach_set("value", resolution)
        ob = self.objects.new(self.ROLE, data, parent=root)
        # a part the root draws: hidden itself, still evaluated for the root (Object > Visibility shows it again)
        ob.hide_viewport = True
        ob.hide_render = True
        return ob

    @staticmethod
    def _attribute(data: Curves, name: str, kind: str, domain: str) -> Any:
        """The attribute (typed Any: its data type depends on `kind`): Blender's own ones (handles, radius,
        resolution) exist on a Bezier curve already; any other must not exist yet."""
        existing = data.attributes.get(name)
        if existing is not None:
            if existing.data_type != kind or existing.domain != domain:
                raise RuntimeError(
                    f"attribute {name} is {existing.data_type} on {existing.domain}, not {kind} on {domain}"
                )
            return existing
        return data.attributes.new(name, kind, domain)  # type: ignore[arg-type]  # kind and domain are Blender's names, given by the callers


class TreeSweepNodes:
    """The "Sapling Tree" group: the tree's curves (moved by the node wind, or posed by the rig) swept to the bark.

    As Blender's curve bevel: a circle of 4 + 2 x Bevel Resolution points, Bevel Depth times each point's
    radius; Resolution U points per segment; no bevel (depth 0) gives the curves as edges. A curve of one point
    (a stem pruning removed) draws nothing. Fast Preview shows the curves themselves in the viewport (renders
    keep the bark).
    """

    GROUP = "Sapling Tree"
    VERSION = 6
    INPUTS = [
        SocketSpec("Curves", "NodeSocketObject"),
        SocketSpec("Bevel Depth", "NodeSocketFloat"),
        SocketSpec("Bevel Resolution", "NodeSocketInt"),
        SocketSpec("Resolution U", "NodeSocketInt"),
        SocketSpec("Fill Caps", "NodeSocketBool"),
        SocketSpec("Fast Preview", "NodeSocketBool"),
        SocketSpec("Wind", "NodeSocketBool"),
        SocketSpec("Material", "NodeSocketMaterial"),
        SocketSpec("Rig", "NodeSocketBool"),
        SocketSpec("Joints", "NodeSocketObject"),
        SocketSpec("Wind Joints", "NodeSocketObject"),
    ]

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: curves, wind or rig, resolution, sweep, Fast Preview."""
        m = NodeMath(group)
        inputs = m.interface(group, cls.INPUTS)
        source = m.object_geometry(inputs["Curves"])
        windy = m.switch(inputs["Wind"], source, cls._windy(m, source, m.object_geometry(inputs["Wind Joints"])))
        curves = m.switch(inputs["Rig"], windy, cls._posed(m, source, m.object_geometry(inputs["Joints"])))
        resolution = m.nodes.new("GeometryNodeSetSplineResolution")
        m.link(cls._drop_single_points(m, curves), resolution.inputs["Curve"])
        m.link(inputs["Resolution U"], resolution.inputs["Resolution"])
        bark = cls._bark(m, inputs, resolution.outputs["Curve"])
        viewport = m.nodes.new("GeometryNodeIsViewport").outputs[0]
        preview = m.nodes.new("FunctionNodeBooleanMath")
        preview.operation = "AND"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(inputs["Fast Preview"], preview.inputs[0])
        m.link(viewport, preview.inputs[1])
        m.link(m.switch(preview.outputs[0], bark, curves), m.nodes.new("NodeGroupOutput").inputs["Geometry"])

    @staticmethod
    def _windy(m: NodeMath, curves: NodeSocket, wind: NodeSocket) -> NodeSocket:
        """The curves with every point moved by the transform of its joint (NodeWind numbers the points), read from
        the wind curves: the joint's own pose turns about its head, so the head itself stays where the joints above
        it put it, and the points up to the next joint turn with it, as the rig's bones turn the bark."""
        transform = m.sample(wind, m.attr("fk_incl", "FLOAT4X4"), m.attr(NodeWind.JOINT, "INT"))
        moved = m.set_position(curves, m.transform_point(m.position(), transform))
        # Set Position moves FREE handles by their point's offset but does not turn them (measured in 5.2.2); a
        # helix's FREE handles turn with their joint, from their positions at rest (Auto handles follow the points)
        for side in ("LEFT", "RIGHT"):
            moved = TreeSweepNodes._turned_free_handles(m, curves, moved, side, transform)
        return moved

    @staticmethod
    def _turned_free_handles(
        m: NodeMath, rest: NodeSocket, moved: NodeSocket, side: str, transform: NodeSocket
    ) -> NodeSocket:
        """The moved curves with their FREE handles on one side ("LEFT" or "RIGHT") at the rest handle moved by
        the transform."""
        handles = m.nodes.new("GeometryNodeInputCurveHandlePositions").outputs[side.title()]
        at_rest = m.sample(rest, handles, m.nodes.new("GeometryNodeInputIndex").outputs[0], "FLOAT_VECTOR")
        free = m.nodes.new("GeometryNodeCurveHandleTypeSelection")
        free.handle_type = "FREE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        free.mode = {side}  # type: ignore[attr-defined]  # stub: as above
        node = m.nodes.new("GeometryNodeSetCurveHandlePositions")
        node.mode = side  # type: ignore[attr-defined]  # stub: as above
        m.link(moved, node.inputs["Curve"])
        m.link(free.outputs[0], node.inputs["Selection"])
        m.link(m.transform_point(at_rest, transform), node.inputs["Position"])
        return node.outputs["Curve"]

    @staticmethod
    def _posed(m: NodeMath, curves: NodeSocket, proxy: NodeSocket) -> NodeSocket:
        """The curves with every point and its handles where the rig's joint proxy holds them (JointProxy: vertex
        3i is point i, 3i + 1 and 3i + 2 its left and right handles)."""
        base = m.math("MULTIPLY", m.nodes.new("GeometryNodeInputIndex").outputs[0], 3.0)

        def sampled(offset: float) -> NodeSocket:
            return m.sample(proxy, m.position(), m.math("ADD", base, offset), "FLOAT_VECTOR")

        # Free handles take the posed positions as they are (Blender recomputes Auto and Vector handles from the
        # points, which would change the bark at rest; the model's handles are Blender's own, moved with the bones)
        free = m.nodes.new("GeometryNodeCurveSetHandles")
        free.handle_type = "FREE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        free.mode = {"LEFT", "RIGHT"}  # type: ignore[attr-defined]  # stub: as above
        m.link(curves, free.inputs["Curve"])
        posed = m.set_position(free.outputs["Curve"], sampled(0.0))
        posed = TreeSweepNodes._handles(m, posed, "LEFT", sampled(1.0))
        return TreeSweepNodes._handles(m, posed, "RIGHT", sampled(2.0))

    @staticmethod
    def _handles(m: NodeMath, curves: NodeSocket, side: str, position: NodeSocket) -> NodeSocket:
        """The curves with the handles on one side ("LEFT" or "RIGHT") at the given positions."""
        handles = m.nodes.new("GeometryNodeSetCurveHandlePositions")
        handles.mode = side  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(curves, handles.inputs["Curve"])
        m.link(position, handles.inputs["Position"])
        return handles.outputs["Curve"]

    @staticmethod
    def _bark(m: NodeMath, inputs: Any, curves: NodeSocket) -> NodeSocket:
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
        m.link(m.switch(bevelled, lines.outputs["Mesh"], swept.outputs["Mesh"]), smooth.inputs["Geometry"])
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
