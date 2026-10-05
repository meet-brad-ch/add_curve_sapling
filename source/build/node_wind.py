# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind in Geometry Nodes, for trees without the armature rig.

The motion is the rig's wind (Joints.sway: per joint two waves and a gust bend on the joint's X and Z axes, from
the same random draws), computed per frame as forward kinematics: each joint's pose is a transform about its
head, composed along every stem and down the branch hierarchy, as an armature composes its bones. The transforms
are computed once per frame by the "Sapling Wind" modifier on a hidden Curves object with one point per joint
("tree_wind": a few thousand points, where the tree has a hundred thousand); the bark's sweep, the leaves and a
baked mesh read their joint's transform from it by joint number ("sapling_joint").
"""

from typing import Any

import bpy
import numpy as np
from bpy.types import Curves, NodeSocket, NodeTree, Object

from ..model.joints import Joints, TreeWind
from .build_params import BuildParams
from .node_groups import SharedNodeGroup
from .node_math import NodeMath, SocketSpec
from .objects import ObjectFactory


class NodeWind:
    """Builds the "tree_wind" curves (one point per joint, carrying the joints' wind) with the "Sapling Wind"
    modifier, and numbers the tree's curve points by their joint."""

    ROLE = "tree_wind"
    MODIFIER = "Sapling Wind"
    JOINT = "sapling_joint"

    def __init__(self, params: BuildParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, root: Object, curves_ob: Object, joints: Joints, wind: TreeWind) -> Object:
        """The hidden wind curves under the root: a poly curve per curve with joints, a point per joint at its head,
        the wind attributes and the modifier. `curves_ob` gets each point's joint number, by which the sweep reads
        its transform."""
        self._number_points(curves_ob, joints)
        data: Curves = bpy.data.hair_curves.new(self.ROLE)
        data.add_curves(joints.count[joints.eligible].tolist())
        data.set_types(type="POLY")
        data.position_data.foreach_set("vector", joints.heads().ravel())
        attributes: Any = data.attributes  # Any: attribute data types vary
        for attribute in wind.sway.attributes():
            attributes.new(attribute.name, attribute.kind, "POINT").data.foreach_set("value", attribute.values.ravel())
        hierarchy = joints.joint_hierarchy()
        attributes.new("depth", "INT", "POINT").data.foreach_set("value", hierarchy.depth)
        attributes.new("attach", "INT", "POINT").data.foreach_set("value", hierarchy.attach)
        ob = self.objects.new(self.ROLE, data, parent=root)
        # a part the root reads: hidden itself, still evaluated for the root (Object > Visibility shows it again)
        ob.hide_viewport = True
        ob.hide_render = True
        passes = joints.passes()
        group = SharedNodeGroup.ensure(WindNodes.GROUP, WindNodes.VERSION, WindNodes.build)
        modifier = SharedNodeGroup.add_modifier(ob, self.MODIFIER, group)
        SharedNodeGroup.set_input(modifier, "Gust", wind.sway.gust_frequency)
        SharedNodeGroup.set_input(modifier, "Scan Passes", passes.scan)
        SharedNodeGroup.set_input(modifier, "Depth Passes", passes.depth)
        return ob

    @classmethod
    def _number_points(cls, curves_ob: Object, joints: Joints) -> None:
        """Every point of the tree's curves gets the number of the joint it follows."""
        attributes: Any = curves_ob.data.attributes  # type: ignore[union-attr]  # a Curves object; Any: as above
        attributes.new(cls.JOINT, "INT", "POINT").data.foreach_set("value", joints.point_ordinals().astype(np.int32))

    @staticmethod
    def follow(ob: Object, wind_ob: Object, joints: np.ndarray) -> None:
        """Make ob's mesh points follow the wind of their joints (one joint number per point) from `wind_ob`."""
        mesh: Any = ob.data  # a mesh; Any: the attribute's data type depends on its kind
        if FollowWindNodes.JOINT in mesh.attributes:  # attributes.new would quietly make a ".001" twin
            raise RuntimeError(f"{ob.name} already has a '{FollowWindNodes.JOINT}' attribute")
        mesh.attributes.new(FollowWindNodes.JOINT, "INT", "POINT").data.foreach_set("value", joints)
        group = SharedNodeGroup.ensure(FollowWindNodes.GROUP, FollowWindNodes.VERSION, FollowWindNodes.build)
        modifier = SharedNodeGroup.add_modifier(ob, FollowWindNodes.MODIFIER, group)
        SharedNodeGroup.set_input(modifier, "Curves", wind_ob)


class WindNodes:
    """The "Sapling Wind" group: per joint point of the wind curves, the composed transform of every joint above
    it, stored as attributes.

    fk_s: along the joint's curve, the joints up to and including its own (a Hillis-Steele scan, 2^k joints per
    pass); fk_a: the ancestors' transform at the curve's attach joint (one pass per depth); fk_incl = fk_a @ fk_s:
    what moves everything the joint carries (the curve points up to the next joint, the leaves hanging there).
    """

    GROUP = "Sapling Wind"
    VERSION = 2
    INPUTS = [
        SocketSpec("Gust", "NodeSocketFloat"),
        SocketSpec("Scan Passes", "NodeSocketInt"),
        SocketSpec("Depth Passes", "NodeSocketInt"),
    ]

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: joint poses, the scan along the curves, the ancestors, the totals."""
        m = NodeMath(group)
        inputs = m.interface(group, cls.INPUTS)
        geometry = m.store(inputs["Geometry"], "fk_s", cls._joint_pose(m, inputs["Gust"]))
        geometry = cls._scan(m, geometry, inputs["Scan Passes"])
        geometry = m.store(geometry, "fk_a", m.identity())
        geometry = cls._ancestors(m, geometry, inputs["Depth Passes"])
        geometry = m.store(geometry, "fk_incl", m.multiply(m.attr("fk_a", "FLOAT4X4"), m.attr("fk_s", "FLOAT4X4")))
        m.link(geometry, m.nodes.new("NodeGroupOutput").inputs["Geometry"])

    @staticmethod
    def _scan(m: NodeMath, geometry: Any, passes: Any) -> NodeSocket:
        zone = m.repeat(geometry, passes)
        step = m.math("MULTIPLY", m.math("POWER", 2.0, zone.iteration), -1.0)
        offset = m.offset_in_curve(step)
        earlier = m.sample(zone.inside, m.attr("fk_s", "FLOAT4X4"), offset.index)
        stored = m.store(zone.inside, "fk_s", m.multiply(earlier, m.attr("fk_s", "FLOAT4X4")), selection=offset.valid)
        m.link(stored, zone.end.inputs["Geometry"])
        return zone.end.outputs["Geometry"]

    @staticmethod
    def _ancestors(m: NodeMath, geometry: Any, passes: Any) -> NodeSocket:
        zone = m.repeat(geometry, passes)
        level = m.math("ADD", zone.iteration, 1.0)
        inclusive = m.multiply(m.attr("fk_a", "FLOAT4X4"), m.attr("fk_s", "FLOAT4X4"))
        sampled = m.sample(zone.inside, inclusive, m.attr("attach", "INT"))
        selection = m.math("COMPARE", m.attr("depth", "INT"), level)
        m.link(m.store(zone.inside, "fk_a", sampled, selection=selection), zone.end.inputs["Geometry"])
        return zone.end.outputs["Geometry"]

    @classmethod
    def _joint_pose(cls, m: NodeMath, gust: Any) -> NodeSocket:
        """x -> D (x - h) + h at every joint head h, D = B R B^-1: the pose rotation R (Euler XYZ ax, 0, az, as the
        rig's pose bones) in the bone's rest frame B."""
        frame = m.nodes.new("GeometryNodeInputSceneTime").outputs["Frame"]
        ax = cls._angle(m, frame, gust, "ox", "a4")
        az = cls._angle(m, frame, gust, "oz", "a3")
        euler = m.nodes.new("ShaderNodeCombineXYZ")
        m.link(ax, euler.inputs["X"])
        m.link(az, euler.inputs["Z"])
        local = m.nodes.new("FunctionNodeEulerToRotation")
        m.link(euler.outputs[0], local.inputs[0])
        rest = m.attr("bone_rest", "QUATERNION")
        inverse = m.nodes.new("FunctionNodeInvertRotation")
        m.link(rest, inverse.inputs[0])
        pose = cls._rotate(m, cls._rotate(m, inverse.outputs[0], local.outputs[0]), rest)
        head = m.position()
        turned = m.nodes.new("FunctionNodeRotateVector")
        m.link(head, turned.inputs["Vector"])
        m.link(pose, turned.inputs["Rotation"])
        combine = m.nodes.new("FunctionNodeCombineTransform")
        m.link(m.math("SUBTRACT", head, turned.outputs[0], vector=True), combine.inputs["Translation"])
        m.link(pose, combine.inputs["Rotation"])
        return combine.outputs[0]

    @staticmethod
    def _rotate(m: NodeMath, rotation: Any, by: Any) -> NodeSocket:
        """by * rotation."""
        node = m.nodes.new("FunctionNodeRotateRotation")
        node.rotation_space = "GLOBAL"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(rotation, node.inputs["Rotation"])
        m.link(by, node.inputs["Rotate By"])
        return node.outputs[0]

    @staticmethod
    def _angle(m: NodeMath, frame: Any, gust: Any, offset: str, bend: str) -> NodeSocket:
        """a1 sin(f1 t + o) + a2 sin(f2 t + 0.7 o) + bend sin(g t) + 0.6 bend: the rig's F-curve generators."""
        o = m.attr(offset)
        phase1 = m.math("ADD", m.math("MULTIPLY", m.attr("f1"), frame), o)
        wave1 = m.math("MULTIPLY", m.attr("a1"), m.math("SINE", phase1))
        phase2 = m.math("ADD", m.math("MULTIPLY", m.attr("f2"), frame), m.math("MULTIPLY", o, 0.7))
        wave2 = m.math("MULTIPLY", m.attr("a2"), m.math("SINE", phase2))
        amount = m.attr(bend)
        gusts = m.math("MULTIPLY", amount, m.math("SINE", m.math("MULTIPLY", gust, frame)))
        return m.math("ADD", m.math("ADD", wave1, wave2), m.math("ADD", gusts, m.math("MULTIPLY", amount, 0.6)))


class FollowWindNodes:
    """The "Sapling Follow Wind" group: mesh points move with the joint they hang from (leaves, a baked mesh),
    read from the wind curves by joint number."""

    GROUP = "Sapling Follow Wind"
    VERSION = 1
    MODIFIER = "Sapling Follow Wind"
    JOINT = "sapling_joint"
    INPUTS = [SocketSpec("Curves", "NodeSocketObject")]

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: sample each point's joint transform from the wind curves and move the point."""
        m = NodeMath(group)
        inputs = m.interface(group, cls.INPUTS)
        wind = m.object_geometry(inputs["Curves"])
        transform = m.sample(wind, m.attr("fk_incl", "FLOAT4X4"), m.attr(cls.JOINT, "INT"))
        moved = m.set_position(inputs["Geometry"], m.transform_point(m.position(), transform))
        m.link(moved, m.nodes.new("NodeGroupOutput").inputs["Geometry"])
