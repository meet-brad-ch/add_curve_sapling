# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaf geometry: one small mesh (or one instancing point) per leaf sprout, placed for all leaves at once.

Each leaf is a template (in leaf space, growing along +z) scaled and turned by a chain of rotations. The chain
is composed into one matrix per leaf (rotations.py) and applied to every template vertex in one array
operation. The random draws stay per leaf, in leaf order (turn, down angle, scale).
"""

from dataclasses import dataclass
from math import copysign, pi, radians
from random import Random

import numpy as np

from .params import TreeParams
from .rotations import Rotation
from .sprouting import SproutArrays


@dataclass(frozen=True, slots=True)
class LeafTemplate:
    """One leaf's geometry in leaf space: vertices (V, 3) float64 and faces (F, 4) int32 into them."""

    vertices: np.ndarray
    faces: np.ndarray


class LeafShape:
    """Template geometry of one leaf, in leaf space (the leaf grows along +z)."""

    HEX = "hex"
    RECT = "rect"
    INSTANCE_FACES = "dFace"
    INSTANCE_POINTS = "dVert"

    MESH = [HEX, RECT]
    INSTANCED = [INSTANCE_FACES, INSTANCE_POINTS]
    VERTS_PER_LEAF = {HEX: 6, RECT: 4, INSTANCE_FACES: 4, INSTANCE_POINTS: 1}
    # Face instancing scales each instance by its face size times this; leaf faces are made this much smaller
    FACE_INSTANCE_SCALE = 10.0
    _VERTICES = {
        HEX: [[0, 0, 0], [0.5, 0, 1 / 3], [0.5, 0, 2 / 3], [0, 0, 1], [-0.5, 0, 2 / 3], [-0.5, 0, 1 / 3]],
        RECT: [[0.5, 0, 0], [0.5, 0, 1], [-0.5, 0, 1], [-0.5, 0, 0]],
        INSTANCE_FACES: [[0.5, 0.5, 0], [0.5, -0.5, 0], [-0.5, -0.5, 0], [-0.5, 0.5, 0]],
        INSTANCE_POINTS: [[0, 0, 1]],
    }
    _FACES = {
        HEX: [[0, 1, 2, 3], [0, 3, 4, 5]],
        RECT: [[0, 1, 2, 3]],
        INSTANCE_FACES: [[0, 3, 2, 1]],
        INSTANCE_POINTS: [],
    }

    @classmethod
    def template(cls, shape: str) -> LeafTemplate:
        """The vertices and faces of a leaf of the given shape; raises ValueError for an unknown shape."""
        if shape not in cls._VERTICES:
            raise ValueError(f"unknown leaf shape {shape}")
        faces = np.array(cls._FACES[shape], dtype=np.int32).reshape(-1, 4)
        return LeafTemplate(np.array(cls._VERTICES[shape], dtype=np.float64), faces)

    @classmethod
    def verts_per_leaf(cls, shape: str) -> int:
        """How many vertices a leaf of the shape adds (1 for Instance Points); ValueError for an unknown shape."""
        if shape not in cls.VERTS_PER_LEAF:
            raise ValueError(f"unknown leaf shape {shape}")
        return cls.VERTS_PER_LEAF[shape]


class LeafSet:
    """The generated leaves as arrays, and per leaf the parent stem and point it hangs from.

    vertices (V, 3) float32: the leaf meshes' points (one point per leaf for Instance Points); faces (F, 4) int32
    into vertices; normals (L, 3) float32: each leaf's direction (Instance Points only, else empty); sprout_co
    (L, 3) float32; parent_spline/parent_point (L,): the parent's spline and the segment of the sprout (a fan
    repeats its sprout's).
    """

    def __init__(
        self,
        shape: str,
        vertices: np.ndarray,
        faces: np.ndarray,
        normals: np.ndarray,
        sprout_co: np.ndarray,
        parent_spline: np.ndarray,
        parent_point: np.ndarray,
    ) -> None:
        self.shape = shape
        self.vertices = vertices
        self.faces = faces
        self.normals = normals
        self.sprout_co = sprout_co
        self.parent_spline = parent_spline
        self.parent_point = parent_point

    @property
    def count(self) -> int:
        """How many leaves."""
        return len(self.parent_spline)

    @property
    def verts_per_leaf(self) -> int:
        """How many vertices each leaf adds to `vertices` (1 for Instance Points), for per-leaf indexing."""
        return LeafShape.verts_per_leaf(self.shape)


@dataclass(frozen=True, slots=True)
class LeafDraw:
    """What one leaf's random draws and its sprout decided."""

    sprout: int  # the index of the sprout the leaf grows from
    spin: float  # the rotation about the stem the leaf starts from
    rotation: float  # the rotation after this leaf's turn
    down: float
    scale: float


class LeafPlacement:
    """The leaves' draws as arrays of length L, in leaf order, with their sprouts' positions and frames."""

    def __init__(self, sprouts: SproutArrays, draws: list[LeafDraw]) -> None:
        self.index = np.array([draw.sprout for draw in draws], dtype=np.int64)
        self.spin = np.array([draw.spin for draw in draws], dtype=np.float64)
        self.rotation = np.array([draw.rotation for draw in draws], dtype=np.float64)
        self.down = np.array([draw.down for draw in draws], dtype=np.float64)
        self.scale = np.array([draw.scale for draw in draws], dtype=np.float64)
        self.co = sprouts.co[self.index]
        self.frame = sprouts.frame[self.index]
        self.parent_spline = sprouts.parent_spline[self.index]
        self.parent_point = sprouts.parent_point[self.index]


class LeafGenerator:
    """Places the leaves on the sprout points of the last branch level."""

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def generate(self, sprouts: SproutArrays) -> LeafSet:
        """The leaves of all sprouts, in sprout order: one per sprout, or a fan of |leaves| for a negative count."""
        p = self.params
        placement = self._place(sprouts)
        template = LeafShape.template(p.leaf_shape)
        matrices = Rotation.compose(*self._turns(placement))
        scale = placement.scale
        scaled = template.vertices[None, :, :] * np.stack([p.leaf_scale_x * scale, scale, scale], axis=1)[:, None, :]
        placed = np.einsum("lij,lvj->lvi", matrices, scaled)
        count = len(placement.index)
        if p.leaf_shape == LeafShape.INSTANCE_POINTS:
            normals = Rotation.unit(placed[:, 0, :])
            vertices = placement.co
            all_faces = np.zeros((0, 4), dtype=np.int32)
        else:
            vertices = (placed + placement.co[:, None, :]).reshape(-1, 3)
            normals = np.zeros((0, 3), dtype=np.float64)
            offsets = (len(template.vertices) * np.arange(count, dtype=np.int32))[:, None, None]
            all_faces = (template.faces[None, :, :] + offsets).reshape(-1, 4)
        return LeafSet(
            p.leaf_shape,
            vertices.astype(np.float32),
            all_faces.astype(np.int32),
            normals.astype(np.float32),
            placement.co.astype(np.float32),
            placement.parent_spline,
            placement.parent_point,
        )

    def _place(self, sprouts: SproutArrays) -> LeafPlacement:
        """Every leaf's draws, in leaf order; the leaf rotation carries over from one sprout to the next (a fan
        restarts it)."""
        p = self.params
        draws: list[LeafDraw] = []
        rotation = 0.0
        for i, offset in enumerate(sprouts.offset.tolist()):
            if p.leaves < 0:
                rotation = -p.leaf_rotate / 2
                for _ in range(-p.leaves):
                    rotation = self._place_one(i, offset, rotation, draws)
            else:
                rotation = self._place_one(i, offset, rotation, draws)
        return LeafPlacement(sprouts, draws)

    def _place_one(self, sprout: int, offset: float, rotation: float, draws: list[LeafDraw]) -> float:
        """One leaf's draws, in this order: the turn around the stem, the down angle, the scale; returns the
        rotation the next leaf continues from."""
        spin = 0.0 if self.params.leaves == -1 else rotation  # a fan of one leaf does not spin
        rotation = self._turn(rotation)
        down = self._down(offset)
        scale = self._scale(offset, rotation)
        draws.append(LeafDraw(sprout, spin, rotation, down, scale))
        return rotation

    def _fan_step(self) -> float:
        """The angle between the leaves of a palmate fan."""
        return self.params.leaf_rotate / (-self.params.leaves - 1)

    def _turn(self, rotation: float) -> float:
        """The rotation the next leaf continues from."""
        p = self.params
        count = p.leaves
        rotate = p.leaf_rotate
        if rotate < 0.0:
            # a negative rotate angle puts each leaf on the other side of the stem from the last one
            return -copysign(rotate + self.rng.uniform(-p.leaf_rotate_v, p.leaf_rotate_v), rotation)
        if count == -1:
            return rotation
        if count < -1:
            return rotation + self._fan_step()
        return rotation + rotate + self.rng.uniform(-p.leaf_rotate_v, p.leaf_rotate_v)

    def _down(self, offset: float) -> float:
        """The angle away from the stem (Leaf Down Angle); unused by palmate leaves, which draw nothing for it."""
        p = self.params
        if p.leaves < 0:
            return 0.0
        if p.leaf_down_angle_v > 0.0:
            down_v = -p.leaf_down_angle_v * offset
        else:
            down_v = self.rng.uniform(-p.leaf_down_angle_v, p.leaf_down_angle_v)
        return p.leaf_down_angle + down_v

    def _scale(self, offset: float, rotation: float) -> float:
        """Leaf size: tapered along the parent (or across the fan), then randomly varied."""
        p = self.params
        count = p.leaves
        rotate = p.leaf_rotate
        if (count < -1) and (rotate != 0):
            f = 1 - abs((rotation - self._fan_step()) / (rotate / 2))
        else:
            f = offset
        if p.leaf_scale_t < 0:
            scale = p.leaf_scale * (1 - (1 - f) * -p.leaf_scale_t)
        else:
            scale = p.leaf_scale * (1 - f * p.leaf_scale_t)
        scale = scale * self.rng.uniform(1 - p.leaf_scale_v, 1 + p.leaf_scale_v)
        if p.leaf_shape == LeafShape.INSTANCE_FACES:
            scale = scale * (1 / LeafShape.FACE_INSTANCE_SCALE)
        return scale

    def _turns(self, placement: LeafPlacement) -> list[np.ndarray]:
        """The rotations every vertex of each leaf gets, in order (a turn that does not apply is the identity)."""
        p = self.params
        turns = [Rotation.about(np.array(pi), "Z"), Rotation.about(np.array(radians(-p.leaf_angle)), "X")]
        turns += self._alternating_turns(placement)
        turns += self._orientation_turns(placement)
        if (p.leaf_bend != 0.0) and (p.leaves > 0):
            turns.extend(self._bend(placement))
        return turns

    def _alternating_turns(self, placement: LeafPlacement) -> list[np.ndarray]:
        """A negative Leaf Rotate Angle puts the leaves on alternating sides: a quarter turn, then a half turn
        for the leaves whose rotation is negative."""
        if self.params.leaf_rotate >= 0:
            return []
        return [
            Rotation.about(np.array(pi / 2), "Z"),
            Rotation.about(np.where(placement.rotation < 0, pi, 0.0), "Z"),
        ]

    def _orientation_turns(self, placement: LeafPlacement) -> list[np.ndarray]:
        """Horizontal Leaves, the down angle, the spin about the stem and the sprout's frame."""
        p = self.params
        count = p.leaves
        rotate = p.leaf_rotate
        turns = []
        if (count > 0) and (rotate > 0) and p.horizontal_leaves:
            turns.append(Rotation.about(-placement.rotation + rotate, "Z"))
        if count > 0:
            turns.append(Rotation.about(placement.down, "X"))
        turns.append(Rotation.about(placement.spin, "Y" if count < 0 else "Z"))
        turns.append(placement.frame)
        return turns

    def _bend(self, placement: LeafPlacement) -> list[np.ndarray]:
        """Rotations that turn each leaf towards the outside of the tree (Leaf Bend)."""
        bend = self.params.leaf_bend
        normal = placement.frame[:, :, 1]  # the sprout's rotation applied to the y axis
        orientation_vec = placement.frame[:, :, 2]  # and to the z axis
        theta_pos = np.arctan2(placement.co[:, 1], placement.co[:, 0])
        theta_bend = theta_pos - np.arctan2(normal[:, 1], normal[:, 0])
        rotate_z = Rotation.about(bend * theta_bend, "Z")
        normal = Rotation.apply(rotate_z, normal)
        orientation_vec = Rotation.apply(rotate_z, orientation_vec)
        phi_bend = np.arctan2(np.hypot(normal[:, 0], normal[:, 1]), normal[:, 2])
        orientation = np.arctan2(orientation_vec[:, 1], orientation_vec[:, 0])
        return [
            rotate_z,
            Rotation.about(orientation, "X"),
            Rotation.about(bend * phi_bend, "Z"),
            Rotation.about(-orientation, "X"),
        ]
