# SPDX-License-Identifier: GPL-3.0-or-later

"""Small node-building helpers shared by the tree's Geometry Nodes groups."""

from dataclasses import dataclass
from typing import Any

from bpy.types import NodeSocket, NodeTree


@dataclass(frozen=True, slots=True)
class RepeatZone:
    """A repeat zone: the geometry inside it, the iteration index, and the zone's output node."""

    inside: NodeSocket
    iteration: NodeSocket
    end: Any


@dataclass(frozen=True, slots=True)
class CurveOffset:
    """Offset Point in Curve: whether the point at the offset exists, and its index."""

    valid: NodeSocket
    index: NodeSocket


@dataclass(frozen=True, slots=True)
class SocketSpec:
    """A group interface socket: its name and its socket type."""

    name: str
    kind: str


class NodeMath:
    """Builds nodes in a group: maths, attributes, sampling and the geometry primitives the groups share."""

    def __init__(self, group: NodeTree) -> None:
        self.nodes = group.nodes
        self.links = group.links

    def link(self, a: Any, b: Any) -> None:
        """Connect two sockets."""
        self.links.new(a, b)

    def math(self, op: str, a: Any, b: Any = None, vector: bool = False, clamp: bool = False) -> NodeSocket:
        """A Math (or Vector Math) node of a and b: sockets are linked, numbers set; returns its result."""
        node = self.nodes.new("ShaderNodeVectorMath" if vector else "ShaderNodeMath")
        node.operation = op  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        if not vector:
            node.use_clamp = clamp  # type: ignore[attr-defined]  # stub: as above
        for socket, value in zip([s for s in node.inputs if s.enabled], (a, b), strict=False):
            if value is None:
                continue
            if isinstance(value, int | float):
                socket.default_value = value  # type: ignore[attr-defined]  # stub: NodeSocket base class
            else:
                self.link(value, socket)
        return node.outputs[0]

    def attr(self, name: str, kind: str = "FLOAT") -> NodeSocket:
        """A named attribute of the given type."""
        node = self.nodes.new("GeometryNodeInputNamedAttribute")
        node.data_type = kind  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.inputs["Name"].default_value = name  # type: ignore[attr-defined]  # stub: NodeSocket base class
        return node.outputs["Attribute"]

    def store(self, geometry: Any, name: str, value: Any, kind: str = "FLOAT4X4", selection: Any = None) -> NodeSocket:
        """Store a point attribute (on the selected points); returns the geometry."""
        node = self.nodes.new("GeometryNodeStoreNamedAttribute")
        node.data_type = kind  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.domain = "POINT"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.inputs["Name"].default_value = name  # type: ignore[attr-defined]  # stub: NodeSocket base class
        self.link(geometry, node.inputs["Geometry"])
        self.link(value, node.inputs["Value"])
        if selection is not None:
            self.link(selection, node.inputs["Selection"])
        return node.outputs["Geometry"]

    def multiply(self, a: Any, b: Any) -> NodeSocket:
        """a @ b (b is applied first)."""
        node = self.nodes.new("FunctionNodeMatrixMultiply")
        self.link(a, node.inputs[0])
        self.link(b, node.inputs[1])
        return node.outputs[0]

    def sample(self, geometry: Any, value: Any, index: Any, kind: str = "FLOAT4X4") -> NodeSocket:
        """The value field of `geometry` at the point `index`."""
        node = self.nodes.new("GeometryNodeSampleIndex")
        node.data_type = kind  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.domain = "POINT"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        self.link(geometry, node.inputs["Geometry"])
        self.link(value, node.inputs["Value"])
        self.link(index, node.inputs["Index"])
        return node.outputs[0]

    def transform_point(self, point: Any, matrix: Any) -> NodeSocket:
        """A point moved by a transform."""
        node = self.nodes.new("FunctionNodeTransformPoint")
        self.link(point, node.inputs["Vector"])
        self.link(matrix, node.inputs["Transform"])
        return node.outputs[0]

    def position(self) -> NodeSocket:
        """The position field."""
        return self.nodes.new("GeometryNodeInputPosition").outputs[0]

    def set_position(self, geometry: Any, position: Any) -> NodeSocket:
        """Move every point; returns the geometry."""
        node = self.nodes.new("GeometryNodeSetPosition")
        self.link(geometry, node.inputs["Geometry"])
        self.link(position, node.inputs["Position"])
        return node.outputs["Geometry"]

    def identity(self) -> NodeSocket:
        """The identity transform."""
        return self.nodes.new("FunctionNodeCombineTransform").outputs[0]

    def repeat(self, geometry: Any, iterations: Any) -> RepeatZone:
        """A repeat zone over geometry."""
        start = self.nodes.new("GeometryNodeRepeatInput")
        end = self.nodes.new("GeometryNodeRepeatOutput")
        start.pair_with_output(end)  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        self.link(iterations, start.inputs["Iterations"])
        self.link(geometry, start.inputs["Geometry"])
        return RepeatZone(start.outputs["Geometry"], start.outputs["Iteration"], end)

    def offset_in_curve(self, offset: Any) -> CurveOffset:
        """The point `offset` places further along each point's curve."""
        node = self.nodes.new("GeometryNodeOffsetPointInCurve")
        self.link(offset, node.inputs["Offset"])
        return CurveOffset(node.outputs["Is Valid Offset"], node.outputs["Point Index"])

    def object_geometry(self, object_input: Any) -> NodeSocket:
        """An object's geometry, in the space of the object the modifier runs on (Object Info, Relative)."""
        info = self.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "RELATIVE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        self.link(object_input, info.inputs["Object"])
        return info.outputs["Geometry"]

    def switch(self, condition: Any, if_false: Any, if_true: Any) -> NodeSocket:
        """A geometry switch."""
        node = self.nodes.new("GeometryNodeSwitch")
        node.input_type = "GEOMETRY"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        self.link(condition, node.inputs["Switch"])
        self.link(if_false, node.inputs["False"])
        self.link(if_true, node.inputs["True"])
        return node.outputs[0]

    def interface(self, group: NodeTree, inputs: list[SocketSpec]) -> Any:
        """The group's sockets: a Geometry input, the given inputs, a Geometry output; returns the Group Input
        node's outputs."""
        interface = group.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type typed as 'DEFAULT' only
        for spec in inputs:
            interface.new_socket(spec.name, in_out="INPUT", socket_type=spec.kind)  # type: ignore[union-attr, arg-type]  # stub: as above
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: as above
        return self.nodes.new("NodeGroupInput").outputs
