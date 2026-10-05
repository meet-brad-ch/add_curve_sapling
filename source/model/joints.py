# SPDX-License-Identifier: GPL-3.0-or-later

"""The joints of a tree: where its bones start, and how the wind moves them.

A joint is a bone of the armature rig and, at the same time, a point the node wind composes its transforms
at: every Joint Length segments along every stem within the Joint Levels. The rig's F-curves and the node wind's
attributes take the same sway numbers from here (sway()), so both wind paths move the tree the same way. Where
the sway was first computed with mathutils (the spline length and the bone direction are float32 vectors),
the same float32 steps are taken here, so the numbers are bit for bit the ones the rig has always had.
"""

from dataclasses import dataclass
from math import radians
from random import Random

import numpy as np

from .curve_data import CurveData
from .geometry import Angles
from .leaves import LeafSet
from .params import TreeParams, WindParams
from .rotations import Quaternions
from .stem import BoneName
from .tree import GrownTree
from .wind_model import WindModel


class JointFrame:
    """A joint's rest orientation as Blender orients a bone (vec_roll_to_mat3_normalized, roll 0)."""

    SAFE = 6.1e-3
    CRITICAL = 2.5e-4

    @classmethod
    def rests(cls, directions: np.ndarray) -> np.ndarray:
        """(N, 4) quaternions of the rest frames of (N, 3) unit directions (the sign may differ; the rotation is
        the same)."""
        d = np.asarray(directions, dtype=np.float64)
        x, y, z = d[:, 0], d[:, 1], d[:, 2]
        theta = 1.0 + y
        theta_alt = x * x + z * z
        regular = (theta > cls.SAFE) | (theta_alt > cls.CRITICAL * cls.CRITICAL)
        theta = np.where(theta <= cls.SAFE, theta_alt * 0.5 + theta_alt * theta_alt * 0.125, theta)
        theta = np.where(theta == 0.0, 1.0, theta)
        x_axis = np.stack([1 - x * x / theta, -x, -x * z / theta], axis=1)
        z_axis = np.stack([-x * z / theta, -z, 1 - z * z / theta], axis=1)
        x_axis[~regular] = [-1.0, 0.0, 0.0]
        z_axis[~regular] = [0.0, 0.0, 1.0]
        return Quaternions.from_matrices(np.stack([x_axis, d, z_axis], axis=2))


@dataclass(frozen=True, slots=True)
class JointHierarchy:
    """Per joint: how deep its curve hangs below a trunk, and the joint its curve's first joint hangs from (-1
    for a trunk)."""

    depth: np.ndarray
    attach: np.ndarray


@dataclass(frozen=True, slots=True)
class WindPasses:
    """How many passes the wind group needs: along the curve with the most joints, and down the hierarchy."""

    scan: int
    depth: int


@dataclass(frozen=True, slots=True)
class CurveWind:
    """Per curve: the two random phases of its wind, and its two wave frequencies (zeros without joints)."""

    offset_x: np.ndarray
    offset_z: np.ndarray
    frequency1: np.ndarray
    frequency2: np.ndarray


@dataclass(frozen=True, slots=True)
class AttributeValues:
    """One named attribute's values for the wind curves (FLOAT per joint, or a QUATERNION per joint)."""

    name: str
    kind: str
    values: np.ndarray


@dataclass(frozen=True, slots=True)
class JointSway:
    """Every joint's wind, in radians per joint: two waves about both bone axes, the gust bend about each axis,
    the random phases, the wave frequencies, and the bone's rest orientation."""

    wind1: np.ndarray
    wind2: np.ndarray
    gust_z: np.ndarray  # the gust bend on the bone's Z axis
    gust_x: np.ndarray  # the gust bend on the bone's X axis
    offset_x: np.ndarray
    offset_z: np.ndarray
    frequency1: np.ndarray
    frequency2: np.ndarray
    rest: np.ndarray
    gust_frequency: float  # the gust's frequency, the same for every joint

    def attributes(self) -> list[AttributeValues]:
        """The node wind's point attributes (float32), named as the "Sapling Wind" group reads them."""
        floats = [
            AttributeValues("a1", "FLOAT", self.wind1),
            AttributeValues("a2", "FLOAT", self.wind2),
            AttributeValues("a3", "FLOAT", self.gust_z),
            AttributeValues("a4", "FLOAT", self.gust_x),
            AttributeValues("f1", "FLOAT", self.frequency1),
            AttributeValues("f2", "FLOAT", self.frequency2),
            AttributeValues("ox", "FLOAT", self.offset_x),
            AttributeValues("oz", "FLOAT", self.offset_z),
        ]
        out = [AttributeValues(a.name, a.kind, a.values.astype(np.float32)) for a in floats]
        out.append(AttributeValues("bone_rest", "QUATERNION", self.rest.astype(np.float32)))
        return out


@dataclass(frozen=True, slots=True)
class TreeWind:
    """A tree's wind: the model's numbers and every joint's sway from them."""

    model: WindModel
    sway: JointSway


class Joints:
    """The joints of a grown tree, from its flat curve arrays, with what the rig and the node wind need of them.

    Arrays per joint (J): joint_spline, joint_n (the point on its curve the joint starts at), joint_tail (the
    point it ends at), joint_point (its head's index in the flat arrays). Arrays per curve (C): sizes, starts,
    step (Joint Length at the curve's level), eligible (the curve has joints: two or more points and within
    the Joint Levels), count (its joints), link_spline/link_point (where its first point hangs).
    """

    def __init__(self, params: WindParams, curve: CurveData, grown: GrownTree) -> None:
        self.params = params
        self.flat = curve.flatten()
        self.sizes = self.flat.sizes
        self.starts = self.flat.start[:-1]
        count = len(self.sizes)
        parent_bones = grown.bone_map.bones()
        self.link_spline = np.array([BoneName.spline(b) if b else -1 for b in parent_bones], dtype=np.int64)
        self.link_point = np.array([BoneName.point(b) if b else -1 for b in parent_bones], dtype=np.int64)
        depth = np.searchsorted(np.array(grown.level_ends), np.arange(count), side="right")
        self.step = np.array(params.bone_step, dtype=np.int64)[np.minimum(depth, TreeParams.LEVELS - 1)]
        segments = self.sizes - 1
        eligible = segments >= 1  # a stem pruning removed has only its start point
        # Joint Levels: deeper levels follow their parent's joints
        eligible &= np.arange(count) < grown.level_ends[params.bone_levels]
        self.eligible = eligible
        self._layout(segments)

    def _layout(self, segments: np.ndarray) -> None:
        """The joints of every curve: one every Joint Length segments from its start."""
        self.count = np.where(self.eligible, (segments + self.step - 1) // self.step, 0)
        self.joint_spline = np.repeat(np.arange(len(self.sizes)), self.count)
        slot = np.arange(len(self.joint_spline)) - np.repeat(np.cumsum(self.count) - self.count, self.count)
        self.joint_n = slot * self.step[self.joint_spline]
        self.joint_tail = np.minimum(self.joint_n + self.step[self.joint_spline], segments[self.joint_spline])
        self.joint_point = self.starts[self.joint_spline] + self.joint_n

    def names(self) -> list[str]:
        """The rig's bone name of every joint (a bone is named after the point it starts at)."""
        return BoneName.names(self.joint_spline.tolist(), self.joint_n.tolist())

    def heads(self) -> np.ndarray:
        """(J, 3) float32: where every joint starts."""
        return self.flat.co[self.joint_point]

    def tails(self) -> np.ndarray:
        """(J, 3) float32: where every joint ends (the next joint's head, or the curve's last point)."""
        return self.flat.co[self.starts[self.joint_spline] + self.joint_tail]

    def connected(self) -> np.ndarray:
        """(J,) whether the joint continues the joint before it on its curve (all but a curve's first)."""
        return self.joint_n > 0

    def depths(self) -> np.ndarray:
        """Per curve, its depth below a trunk (parents come before children in the arrays)."""
        has_parent = self.link_spline >= 0
        parent = np.maximum(self.link_spline, 0)
        depth = np.zeros(len(self.sizes), dtype=np.int64)
        deeper = np.where(has_parent, depth[parent] + 1, 0)
        while not np.array_equal(deeper, depth):  # one pass per level of nesting
            depth = deeper
            deeper = np.where(has_parent, depth[parent] + 1, 0)
        return depth.astype(np.int32)

    def first_parent(self) -> np.ndarray:
        """Per curve, the joint its first joint hangs from: the nearest joint at or before the point of the parent
        it sprouted or split from (-1 for a trunk and for a curve without joints)."""
        attach = np.full(len(self.sizes), -1, dtype=np.int64)
        linked = np.flatnonzero(self.eligible & (self.link_spline >= 0))
        attach[linked] = self.ordinals(self.nearest_joint(self.link_spline[linked], self.link_point[linked]))
        return attach

    def bone_parents(self) -> np.ndarray:
        """Per joint, the joint its bone hangs from: the joint before it on its curve, or for a curve's first
        joint the joint of the parent stem (-1 for a trunk's first)."""
        previous = np.arange(len(self.joint_point)) - 1
        return np.where(self.connected(), previous, self.first_parent()[self.joint_spline])

    def joint_hierarchy(self) -> JointHierarchy:
        """Per joint, its curve's depth and the joint its curve hangs from (what the wind group's passes read)."""
        return JointHierarchy(self.depths()[self.joint_spline], self.first_parent()[self.joint_spline].astype(np.int32))

    def passes(self) -> WindPasses:
        """The passes the wind group needs: log2 of the most joints on one curve, and the deepest hierarchy."""
        longest = int(self.count.max())
        scan = max(0, int(np.ceil(np.log2(longest)))) if longest > 1 else 0
        return WindPasses(scan, int(self.depths()[self.eligible].max()))

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
            raise RuntimeError("a point index that is not a joint head")
        return ordinal

    def point_ordinals(self) -> np.ndarray:
        """Per curve point, the number of the joint it follows."""
        return self.ordinals(self.point_joints())

    def leaf_joint(self, leaves: LeafSet) -> np.ndarray:
        """Per leaf, the number of the joint it hangs from."""
        return self.ordinals(self.nearest_joint(leaves.parent_spline, leaves.parent_point))

    def leaf_joints(self, leaves: LeafSet) -> np.ndarray:
        """Per leaf vertex, the number of the joint its leaf hangs from (int32)."""
        return np.repeat(self.leaf_joint(leaves), leaves.verts_per_leaf).astype(np.int32)

    def sway(self, model: WindModel, rng: Random) -> JointSway:
        """Every joint's wind, drawing two phases per curve with joints from the rng in curve order (as the rig
        always drew them)."""
        p = self.params
        spline = self.joint_spline
        segments = (self.sizes - 1)[spline]
        n = self.joint_n
        spline_length = (self.sizes - 1) * self._first_segment_lengths()
        per_curve = self._per_curve(model, rng, spline_length)
        direction = self._directions()
        radius = np.maximum(self.flat.radius[self.joint_point].astype(np.float64), 1e-6)
        a0 = 2 * (spline_length[spline] / segments) * (1 - n / (segments + 1)) / radius
        a0 = a0 * np.minimum(self.step[spline], segments)
        a1 = (p.wind / 50) * a0
        gust = (p.wind * p.gust / 50) * a0
        sway = np.stack([a1, a1 * model.SECOND_WAVE_AMPLITUDE, -direction[:, 0] * gust, direction[:, 2] * gust], 1)
        # the first two joints of every trunk hold the tree base still
        sway[(self.link_spline[spline] < 0) & (n <= self.step[spline])] = 0.0
        sway = sway * radians(1.0)
        return JointSway(
            wind1=sway[:, 0],
            wind2=sway[:, 1],
            gust_z=sway[:, 2],
            gust_x=sway[:, 3],
            offset_x=per_curve.offset_x[spline],
            offset_z=per_curve.offset_z[spline],
            frequency1=per_curve.frequency1[spline],
            frequency2=per_curve.frequency2[spline],
            rest=JointFrame.rests(direction),
            gust_frequency=model.gust_frequency,
        )

    @staticmethod
    def _dot(d32: np.ndarray) -> np.ndarray:
        """The squared length of float32 rows as mathutils computes it: each product in float32, the sum in double
        (measured on 20,000 vectors: Vector.length is the square root of this, to the bit)."""
        squares = (d32 * d32).astype(np.float64)
        return (squares[:, 2] + squares[:, 1]) + squares[:, 0]

    def _first_segment_lengths(self) -> np.ndarray:
        """Per curve, the length of its first segment as mathutils measures (P0 - P1).length, to the bit (0 for a
        curve of one point)."""
        lengths = np.zeros(len(self.sizes))
        starts = self.starts[self.eligible]
        lengths[self.eligible] = np.sqrt(self._dot(self.flat.co[starts] - self.flat.co[starts + 1]))
        return lengths

    def _directions(self) -> np.ndarray:
        """Per joint, the float32 unit vector from its head to its tail: the vector times 1.0f / the float32
        length; zero when the squared length is at most 1e-35 (as mathutils' normalize).

        mathutils' own normalize differs from this in the last float32 bit on about 8 % of components (measured
        on 20,000 vectors): its reciprocal is not the correctly rounded one, which no array formula reproduces.
        A gust amplitude of the rig therefore differs from the per-bone code by at most one float32 unit.
        """
        tails = self.starts[self.joint_spline] + self.joint_tail
        d32 = self.flat.co[tails] - self.flat.co[self.joint_point]
        dot = self._dot(d32)
        tiny = dot <= 1.0e-35
        length = np.sqrt(np.where(tiny, 1.0, dot)).astype(np.float32)
        unit = (d32 * (np.float32(1.0) / length)[:, None]).astype(np.float64)
        unit[tiny] = 0.0
        return unit

    def _per_curve(self, model: WindModel, rng: Random, spline_length: np.ndarray) -> CurveWind:
        """The two phases (drawn in curve order) and the frequencies of every curve with joints."""
        count = len(self.sizes)
        offset_x = np.zeros(count)
        offset_z = np.zeros(count)
        frequency1 = np.zeros(count)
        frequency2 = np.zeros(count)
        for i in np.flatnonzero(self.eligible).tolist():
            offset_x[i] = rng.uniform(0, Angles.TAU)
            offset_z[i] = rng.uniform(0, Angles.TAU)
            frequencies = model.branch_frequencies(float(spline_length[i]))
            frequency1[i] = frequencies.first
            frequency2[i] = frequencies.second
        return CurveWind(offset_x, offset_z, frequency1, frequency2)
