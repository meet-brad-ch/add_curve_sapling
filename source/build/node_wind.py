# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind in Geometry Nodes, for trees without the armature rig.

The motion is the rig's wind (WindModel: per joint two waves and a gust bend on the joint's X and Z axes, from
the same random draws), computed per frame as forward kinematics: each joint's pose is a transform about its
head, composed along every stem and down the branch hierarchy, as an armature composes its bones. Measured
against the armature on the test tree: 5.2 % (wind 1) and 0.9 % (wind 3) relative RMS difference of the bark's
motion, with no more stretch than the armature's envelopes.

The joints are the bones the rig would make (one per Joint Length segments, levels per Joint Levels with Make
Mesh). The transforms are computed once, by the "Sapling Wind" modifier on the tree's curves; the bark, the
leaves and the skin mesh read them ("Sapling Follow Wind").
"""

import math
from random import Random
from typing import Any

import numpy as np
from bpy.types import NodeSocket, NodeTree, Object

from ..model.curve_data import CurveData
from ..model.leaves import LeafSet
from ..model.params import TreeParams
from ..model.rotations import Quaternions, Rotation
from ..model.stem import BoneName
from ..model.tree import GrownTree
from .node_groups import SharedNodeGroup
from .wind import WindModel


class JointFrame:
    """A joint's rest orientation as Blender orients a bone (vec_roll_to_mat3_normalized, roll 0)."""

    SAFE = 6.1e-3
    CRITICAL = 2.5e-4

    @classmethod
    def rests(cls, directions: np.ndarray) -> np.ndarray:
        """rest() for (N, 3) unit directions: (N, 4) quaternions (the sign may differ; the rotation is the same)."""
        d = np.asarray(directions, dtype=np.float64)
        x, y, z = d[:, 0], d[:, 1], d[:, 2]
        theta = 1.0 + y
        theta_alt = x * x + z * z
        regular = (theta > cls.SAFE) | (theta_alt > cls.CRITICAL * cls.CRITICAL)
        theta = np.where(theta <= cls.SAFE, theta_alt * 0.5 + theta_alt * theta_alt * 0.125, theta)
        theta = np.where(theta == 0.0, 1.0, theta)
        x_axis = np.stack([1 - x * x / theta, -x, -x * z / theta], axis=1)
        z_axis = np.stack([-x * z / theta, -z, 1 - z * z / theta], axis=1)
        x_axis[~regular] = (-1.0, 0.0, 0.0)
        z_axis[~regular] = (0.0, 0.0, 1.0)
        return Quaternions.from_matrices(np.stack([x_axis, d, z_axis], axis=2))


class WindJoints:
    """Per point of the grown curve, the wind of the joint that starts there; per curve its place in the tree.

    Everything is computed from the curve's flat arrays at once; only the two phase offsets per curve are drawn
    one by one, in the rig's order, so the node wind matches the rig's.
    """

    FLOAT_KEYS = ("a1", "a2", "a3", "a4", "f1", "f2", "ox", "oz")

    def __init__(self, params: TreeParams, curve: CurveData, grown: GrownTree) -> None:
        self.params = params
        self.grown = grown
        self.flat = curve.flatten()
        self.sizes = self.flat.sizes
        self.starts = self.flat.start[:-1]
        count = len(self.sizes)
        self.parent_bones = grown.bone_map.bones()
        self.link_spline = np.array([BoneName.spline(b) if b else -1 for b in self.parent_bones], dtype=np.int64)
        self.link_point = np.array([BoneName.point(b) if b else -1 for b in self.parent_bones], dtype=np.int64)
        level = np.minimum(np.searchsorted(np.array(grown.level_ends), np.arange(count), side="right"), 3)
        self.step = np.array(params.bone_step, dtype=np.int64)[level]
        segments = self.sizes - 1
        eligible = segments >= 1  # a stem pruning removed has only its start point
        # Joint Levels: deeper levels follow their parent's joints
        eligible &= np.arange(count) < grown.level_ends[params.bone_levels]
        self.eligible = eligible
        # the joints of a curve: every Joint Length segments from its start
        self.count = np.where(eligible, (segments + self.step - 1) // self.step, 0)
        self.joint_spline = np.repeat(np.arange(count), self.count)
        slot = np.arange(len(self.joint_spline)) - np.repeat(np.cumsum(self.count) - self.count, self.count)
        self.joint_n = slot * self.step[self.joint_spline]
        self.joint_tail = np.minimum(self.joint_n + self.step[self.joint_spline], segments[self.joint_spline])
        self.joint_point = self.starts[self.joint_spline] + self.joint_n
        self.is_joint = np.zeros(int(self.flat.start[-1]), dtype=bool)
        self.is_joint[self.joint_point] = True

    def hierarchy(self) -> tuple[np.ndarray, np.ndarray]:
        """Per curve: its depth below a trunk, and the point its first joint hangs from (-1 for a trunk)."""
        has_parent = self.link_spline >= 0
        parent = np.maximum(self.link_spline, 0)
        depth = np.zeros(len(self.sizes), dtype=np.int64)
        deeper = np.where(has_parent, depth[parent] + 1, 0)
        while not np.array_equal(deeper, depth):  # one pass per level of nesting; parents come before children
            depth = deeper
            deeper = np.where(has_parent, depth[parent] + 1, 0)
        attach = np.where(has_parent, self.starts[parent] + self.link_point, -1)
        return depth.astype(np.int32), attach.astype(np.int32)

    def poses(self, model: WindModel, rng: Random) -> dict[str, np.ndarray]:
        """The wind of every joint, with the rig's random draws in the rig's order (ArmatureBuilder._branch_bones):
        two phases per curve that has joints."""
        p = self.params
        total = int(self.flat.start[-1])
        out: dict[str, np.ndarray] = {key: np.zeros(total, np.float32) for key in self.FLOAT_KEYS}
        rest = np.zeros((total, 4), np.float32)
        rest[:, 0] = 1.0  # identity where no joint starts
        out["bone_rest"] = rest
        co = self.flat.co.astype(np.float64)
        spline = self.joint_spline
        segments = (self.sizes - 1)[spline]
        n = self.joint_n
        head = self.joint_point
        first_length = np.zeros(len(self.sizes))
        starts = self.starts[self.eligible]
        first_length[self.eligible] = np.linalg.norm(co[starts + 1] - co[starts], axis=1)
        spline_length = (self.sizes - 1) * first_length
        offsets = self._offsets(rng)
        frequencies = model.branch_frequency_arrays(spline_length)
        direction = Rotation.unit(co[self.starts[spline] + self.joint_tail] - co[head])
        a0 = (
            2 * (spline_length[spline] / segments) * (1 - n / (segments + 1)) / np.maximum(self.flat.radius[head], 1e-6)
        )
        a0 = a0 * np.minimum(self.step[spline], segments)
        a1 = (p.wind / 50) * a0
        gust = (p.wind * p.gust / 50) * a0
        sway = np.stack([a1, a1 * model.SECOND_WAVE_AMPLITUDE, -direction[:, 0] * gust, direction[:, 2] * gust], axis=1)
        # the first two joints of every trunk hold the tree base still
        sway[(self.link_spline[spline] < 0) & (n <= self.step[spline])] = 0.0
        for key, column in zip(("a1", "a2", "a3", "a4"), np.radians(sway).T, strict=True):
            out[key][head] = column
        out["f1"][head], out["f2"][head] = frequencies[0][spline], frequencies[1][spline]
        out["ox"][head], out["oz"][head] = offsets[0][spline], offsets[1][spline]
        out["bone_rest"][head] = JointFrame.rests(direction)
        return out

    def _offsets(self, rng: Random) -> tuple[np.ndarray, np.ndarray]:
        """The two wind phases of every curve with joints, drawn in curve order as the rig draws them."""
        ox = np.zeros(len(self.sizes))
        oz = np.zeros(len(self.sizes))
        for i in np.flatnonzero(self.eligible).tolist():
            ox[i] = rng.uniform(0, math.tau)
            oz[i] = rng.uniform(0, math.tau)
        return ox, oz

    def nearest_joint(self, spline: np.ndarray, point: np.ndarray) -> np.ndarray:
        """Per (curve, point on it): the point index of the joint the point follows.

        On a curve with joints, the last joint head at or before the point; on a curve without (above the Joint
        Levels, or a stub), the joint its first point hangs from, found through the parents. Raises when a stem
        hangs from no stem with joints.
        """
        spline = np.array(spline, dtype=np.int64)
        point = np.array(point, dtype=np.int64)
        found = self.eligible[spline]
        while not found.all():  # climb to the parent's attach point until a curve with joints
            climb = np.flatnonzero(~found)
            if (self.link_spline[spline[climb]] < 0).any():
                raise RuntimeError("a stem hangs from a stem without a joint below it")
            point[climb] = self.link_point[spline[climb]]
            spline[climb] = self.link_spline[spline[climb]]
            found = self.eligible[spline]
        step = self.step[spline]
        n = np.minimum((point // step) * step, (self.count[spline] - 1) * step)
        return self.starts[spline] + n

    def point_joints(self) -> np.ndarray:
        """Per curve point, the point index of the joint it follows (a stub trunk, which draws nothing, its own)."""
        total = int(self.flat.start[-1])
        spline = np.repeat(np.arange(len(self.sizes)), self.sizes)
        point = np.arange(total) - self.starts[spline]
        joints = np.arange(total)
        stub = ~self.eligible[spline] & (self.link_spline[spline] < 0)
        joints[~stub] = self.nearest_joint(spline[~stub], point[~stub])
        return joints

    def ordinals(self, joints: np.ndarray) -> np.ndarray:
        """The consecutive number of each joint (its index in the joint arrays) for joint point indices."""
        ordinal = np.searchsorted(self.joint_point, joints)
        if (self.joint_point[np.minimum(ordinal, len(self.joint_point) - 1)] != joints).any():
            raise RuntimeError("a point index that is no joint")
        return ordinal

    def leaf_joints(self, leaves: LeafSet) -> np.ndarray:
        """Per leaf vertex, the joint its leaf hangs from (int32)."""
        joints = self.nearest_joint(leaves.parent_spline, leaves.parent_point)
        return np.repeat(joints, leaves.verts_per_leaf).astype(np.int32)

    def passes(self) -> tuple[int, int]:
        """(scan passes along the longest curve, depth passes down the hierarchy) the wind group needs."""
        longest = int(self.sizes.max())
        depth, _attach = self.hierarchy()
        return max(0, math.ceil(math.log2(longest))) if longest > 1 else 0, int(depth.max())


class NodeWind:
    """Writes the joints' wind onto the tree's curves and gives them the "Sapling Wind" modifier."""

    MODIFIER = "Sapling Wind"

    def __init__(self, params: TreeParams, rng: Random, fps: float) -> None:
        self.params = params
        self.rng = rng
        self.model = WindModel(params, fps)

    def build(self, curves_ob: Object, curve: CurveData, grown: GrownTree) -> WindJoints:
        """The wind attributes (drawing from the rng as the rig would) and the modifier; returns the joints."""
        joints = WindJoints(self.params, curve, grown)
        attributes: Any = curves_ob.data.attributes  # type: ignore[union-attr]  # the curves source is a Curves object; Any: attribute data types vary
        for key, values in joints.poses(self.model, self.rng).items():
            if key == "bone_rest":
                attributes.new(key, "QUATERNION", "POINT").data.foreach_set("value", values.ravel())
            else:
                attributes.new(key, "FLOAT", "POINT").data.foreach_set("value", values)
        depth, attach = joints.hierarchy()
        attributes.new("depth", "INT", "POINT").data.foreach_set("value", np.repeat(depth, joints.sizes))
        attributes.new("attach", "INT", "POINT").data.foreach_set("value", np.repeat(attach, joints.sizes))
        scan, levels = joints.passes()
        group = SharedNodeGroup.ensure(WindNodes.GROUP, WindNodes.VERSION, WindNodes.build)
        modifier = SharedNodeGroup.add_modifier(curves_ob, self.MODIFIER, group)
        SharedNodeGroup.set_input(modifier, "Gust", self.model.gust_frequency)
        SharedNodeGroup.set_input(modifier, "Scan Passes", scan)
        SharedNodeGroup.set_input(modifier, "Depth Passes", levels)
        return joints

    @staticmethod
    def follow(ob: Object, curves_ob: Object, joints: np.ndarray | list[int]) -> None:
        """Make ob's points follow the wind of their joints (one joint index per point)."""
        mesh = ob.data
        mesh.attributes.new(FollowWindNodes.JOINT, "INT", "POINT").data.foreach_set("value", joints)  # type: ignore[union-attr]  # a mesh
        group = SharedNodeGroup.ensure(FollowWindNodes.GROUP, FollowWindNodes.VERSION, FollowWindNodes.build)
        modifier = SharedNodeGroup.add_modifier(ob, FollowWindNodes.MODIFIER, group)
        SharedNodeGroup.set_input(modifier, "Curves", curves_ob)


class NodeMath:
    """Small node-building helpers shared by the wind groups."""

    def __init__(self, group: NodeTree) -> None:
        self.group = group
        self.nodes = group.nodes
        self.links = group.links

    def link(self, a: Any, b: Any) -> None:
        """Connect two sockets."""
        self.links.new(a, b)

    def math(self, op: str, a: Any, b: Any = None, vector: bool = False) -> NodeSocket:
        """A Math (or Vector Math) node of a and b: sockets are linked, numbers set; returns its result."""
        node = self.nodes.new("ShaderNodeVectorMath" if vector else "ShaderNodeMath")
        node.operation = op  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        for socket, value in zip([s for s in node.inputs if s.enabled], (a, b), strict=False):
            if value is None:
                continue
            if isinstance(value, int | float):
                socket.default_value = value  # type: ignore[attr-defined]  # stub: NodeSocket base class
            else:
                self.link(value, socket)
        if vector and op in ("DOT_PRODUCT", "LENGTH", "DISTANCE"):
            return node.outputs["Value"]  # these give a number, on the node's second output
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

    def repeat(self, geometry: Any, iterations: Any) -> tuple[NodeSocket, NodeSocket, Any]:
        """A repeat zone over geometry: (geometry inside, iteration index, the zone's output node)."""
        start = self.nodes.new("GeometryNodeRepeatInput")
        end = self.nodes.new("GeometryNodeRepeatOutput")
        start.pair_with_output(end)  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        self.link(iterations, start.inputs["Iterations"])
        self.link(geometry, start.inputs["Geometry"])
        return start.outputs["Geometry"], start.outputs["Iteration"], end


class WindNodes:
    """The "Sapling Wind" group: per point, the composed transform of every joint above it, stored as attributes.

    fk_s: along the point's curve, the joints up to and including its own (a Hillis-Steele scan, 2^k points per
    pass); fk_a: the ancestors' transform at the curve's attach point (one pass per depth); fk_total = fk_a @ the
    joints before the point (what moves the point); fk_incl = fk_a @ fk_s (what moves things hanging from it).
    """

    GROUP = "Sapling Wind"
    VERSION = 1

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: joint poses, the scan along the curves, the ancestors, the totals."""
        interface = group.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type typed as 'DEFAULT' only
        sockets = (("Gust", "NodeSocketFloat"), ("Scan Passes", "NodeSocketInt"), ("Depth Passes", "NodeSocketInt"))
        for name, kind in sockets:
            interface.new_socket(name, in_out="INPUT", socket_type=kind)  # type: ignore[union-attr, arg-type]  # stub: as above
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: as above
        m = NodeMath(group)
        inputs = m.nodes.new("NodeGroupInput")
        geometry = m.store(inputs.outputs["Geometry"], "fk_s", cls._joint_pose(m, inputs))
        geometry = cls._scan(m, geometry, inputs.outputs["Scan Passes"])
        valid, index = cls._offset(m, -1)
        geometry = m.store(geometry, "fk_l", m.identity())
        geometry = m.store(geometry, "fk_l", m.sample(geometry, m.attr("fk_s", "FLOAT4X4"), index), selection=valid)
        geometry = m.store(geometry, "fk_a", m.identity())
        geometry = cls._ancestors(m, geometry, inputs.outputs["Depth Passes"])
        ancestors = m.attr("fk_a", "FLOAT4X4")
        geometry = m.store(geometry, "fk_total", m.multiply(ancestors, m.attr("fk_l", "FLOAT4X4")))
        geometry = m.store(geometry, "fk_incl", m.multiply(ancestors, m.attr("fk_s", "FLOAT4X4")))
        m.link(geometry, m.nodes.new("NodeGroupOutput").inputs["Geometry"])

    @staticmethod
    def _offset(m: NodeMath, offset: Any) -> tuple[NodeSocket, NodeSocket]:
        node = m.nodes.new("GeometryNodeOffsetPointInCurve")
        if isinstance(offset, int):
            node.inputs["Offset"].default_value = offset  # type: ignore[attr-defined]  # stub: NodeSocket base class
        else:
            m.link(offset, node.inputs["Offset"])
        return node.outputs["Is Valid Offset"], node.outputs["Point Index"]

    @classmethod
    def _scan(cls, m: NodeMath, geometry: Any, passes: Any) -> NodeSocket:
        inside, iteration, end = m.repeat(geometry, passes)
        step = m.math("MULTIPLY", m.math("POWER", 2.0, iteration), -1.0)
        valid, index = cls._offset(m, step)
        earlier = m.sample(inside, m.attr("fk_s", "FLOAT4X4"), index)
        stored = m.store(inside, "fk_s", m.multiply(earlier, m.attr("fk_s", "FLOAT4X4")), selection=valid)
        m.link(stored, end.inputs["Geometry"])
        return end.outputs["Geometry"]

    @staticmethod
    def _ancestors(m: NodeMath, geometry: Any, passes: Any) -> NodeSocket:
        inside, iteration, end = m.repeat(geometry, passes)
        level = m.math("ADD", iteration, 1.0)
        inclusive = m.multiply(m.attr("fk_a", "FLOAT4X4"), m.attr("fk_s", "FLOAT4X4"))
        sampled = m.sample(inside, inclusive, m.attr("attach", "INT"))
        selection = m.math("COMPARE", m.attr("depth", "INT"), level)
        m.link(m.store(inside, "fk_a", sampled, selection=selection), end.inputs["Geometry"])
        return end.outputs["Geometry"]

    @classmethod
    def _joint_pose(cls, m: NodeMath, inputs: Any) -> NodeSocket:
        """x -> D (x - h) + h at every joint head h, D = B R B^-1: the pose rotation R (Euler XYZ ax, 0, az, as the
        rig's pose bones) in the bone's rest frame B."""
        frame = m.nodes.new("GeometryNodeInputSceneTime").outputs["Frame"]
        gust = inputs.outputs["Gust"]
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
    """The "Sapling Follow Wind" group: points move with the joint they hang from (leaves, the skin mesh)."""

    GROUP = "Sapling Follow Wind"
    VERSION = 1
    MODIFIER = "Sapling Follow Wind"
    JOINT = "sapling_joint"

    @classmethod
    def build(cls, group: NodeTree) -> None:
        """Fill the empty group: sample each point's joint transform from the curves and move the point."""
        interface = group.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: as in WindNodes
        interface.new_socket("Curves", in_out="INPUT", socket_type="NodeSocketObject")  # type: ignore[union-attr, arg-type]  # stub: as above
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: as above
        m = NodeMath(group)
        inputs = m.nodes.new("NodeGroupInput")
        info = m.nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "RELATIVE"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(inputs.outputs["Curves"], info.inputs["Object"])
        transform = m.sample(info.outputs["Geometry"], m.attr("fk_incl", "FLOAT4X4"), m.attr(cls.JOINT, "INT"))
        moved = m.set_position(inputs.outputs["Geometry"], m.transform_point(m.position(), transform))
        m.link(moved, m.nodes.new("NodeGroupOutput").inputs["Geometry"])
