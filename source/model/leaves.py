# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaf geometry: one small mesh (or one instancing point) per leaf sprout, placed for all leaves at once.

Each leaf is a template (in leaf space, growing along +z) scaled and turned by a chain of rotations. The chain
is composed into one matrix per leaf (rotations.py) and applied to every template vertex in one array
operation; placing 72,000 leaves one vertex at a time took 1.5 s. The random draws stay per leaf, in leaf order
(turn, down angle, scale), so the rest of the tree draws the same numbers as before.
"""

from math import copysign, pi, radians
from random import Random

import numpy as np

from .params import TreeParams
from .rotations import Quaternions, Rotation
from .stem import ChildPoint


class LeafShape:
    """Template geometry of one leaf, in leaf space (the leaf grows along +z)."""

    HEX = "hex"
    RECT = "rect"
    INSTANCE_FACES = "dFace"
    INSTANCE_POINTS = "dVert"

    MESH = (HEX, RECT)
    INSTANCED = (INSTANCE_FACES, INSTANCE_POINTS)
    VERTS_PER_LEAF = {HEX: 6, RECT: 4, INSTANCE_FACES: 4, INSTANCE_POINTS: 1}
    # Face instancing scales each instance by its face size times this; leaf faces are made this much smaller
    FACE_INSTANCE_SCALE = 10.0
    _VERTICES = {
        HEX: ((0, 0, 0), (0.5, 0, 1 / 3), (0.5, 0, 2 / 3), (0, 0, 1), (-0.5, 0, 2 / 3), (-0.5, 0, 1 / 3)),
        RECT: ((0.5, 0, 0), (0.5, 0, 1), (-0.5, 0, 1), (-0.5, 0, 0)),
        INSTANCE_FACES: ((0.5, 0.5, 0), (0.5, -0.5, 0), (-0.5, -0.5, 0), (-0.5, 0.5, 0)),
        INSTANCE_POINTS: ((0, 0, 1),),
    }
    _FACES = {
        HEX: ((0, 1, 2, 3), (0, 3, 4, 5)),
        RECT: ((0, 1, 2, 3),),
        INSTANCE_FACES: ((0, 3, 2, 1),),
        INSTANCE_POINTS: (),
    }

    @classmethod
    def template(cls, shape: str) -> tuple[np.ndarray, np.ndarray]:
        """(vertices (V, 3) float64, faces (F, 4) int32) of a leaf of the given shape."""
        if shape not in cls._VERTICES:
            raise ValueError(f"unknown leaf shape {shape}")
        return np.array(cls._VERTICES[shape], dtype=np.float64), np.array(cls._FACES[shape], dtype=np.int32).reshape(
            -1, 4
        )


class LeafSet:
    """The generated leaves as arrays, and per leaf the sprout it grows from.

    vertices (V, 3) float32: the leaf meshes' points (one point per leaf for Instance Points); faces (F, 4) int32
    into vertices; normals (L, 3) float32: each leaf's direction (Instance Points only, else empty); sprout_co
    (L, 3) float32; sprouts: one ChildPoint per leaf, in leaf order (a fan repeats its sprout).
    """

    def __init__(
        self,
        shape: str,
        vertices: np.ndarray,
        faces: np.ndarray,
        normals: np.ndarray,
        sprout_co: np.ndarray,
        sprouts: list[ChildPoint],
    ) -> None:
        self.shape = shape
        self.vertices = vertices
        self.faces = faces
        self.normals = normals
        self.sprout_co = sprout_co
        self.sprouts = sprouts

    @property
    def verts_per_leaf(self) -> int:
        """How many vertices each leaf adds to `vertices` (1 for Instance Points), for per-leaf indexing."""
        return LeafShape.VERTS_PER_LEAF[self.shape]


class LeafPlacement:
    """Per leaf, what its random draws and its sprout decided: arrays of length L, in leaf order."""

    def __init__(self, sprouts: list[ChildPoint], rows: list[tuple[float, float, float, float]]) -> None:
        self.sprouts = sprouts
        values = np.array(rows, dtype=np.float64).reshape(-1, 4)
        self.spin = values[:, 0]  # the rotation about the stem the leaf starts from
        self.rotation = values[:, 1]  # the rotation after this leaf's turn
        self.down = values[:, 2]
        self.scale = values[:, 3]
        self.co = np.array([s.co.to_tuple() for s in sprouts], dtype=np.float64).reshape(-1, 3)
        self.quat = np.array([(s.quat.w, s.quat.x, s.quat.y, s.quat.z) for s in sprouts], dtype=np.float64).reshape(
            -1, 4
        )


class LeafGenerator:
    """Places the leaves on the sprout points of the last branch level."""

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def generate(self, sprouts: list[ChildPoint]) -> LeafSet:
        """The leaves of all sprouts, in sprout order: one per sprout, or a fan of |leaves| for a negative count."""
        p = self.params
        placement = self._place(sprouts)
        verts, faces = LeafShape.template(p.leaf_shape)
        matrices = Rotation.compose(*self._turns(placement))
        scale = placement.scale
        scaled = verts[None, :, :] * np.stack([p.leaf_scale_x * scale, scale, scale], axis=1)[:, None, :]
        placed = np.einsum("lij,lvj->lvi", matrices, scaled)
        count = len(placement.sprouts)
        if p.leaf_shape == LeafShape.INSTANCE_POINTS:
            direction = placed[:, 0, :]
            normals = direction / np.linalg.norm(direction, axis=1)[:, None]
            vertices = placement.co
            all_faces = np.zeros((0, 4), dtype=np.int32)
        else:
            vertices = (placed + placement.co[:, None, :]).reshape(-1, 3)
            normals = np.zeros((0, 3), dtype=np.float64)
            offsets = (len(verts) * np.arange(count, dtype=np.int32))[:, None, None]
            all_faces = (faces[None, :, :] + offsets).reshape(-1, 4)
        return LeafSet(
            p.leaf_shape,
            vertices.astype(np.float32),
            all_faces.astype(np.int32),
            normals.astype(np.float32),
            placement.co.astype(np.float32),
            placement.sprouts,
        )

    def _place(self, sprouts: list[ChildPoint]) -> LeafPlacement:
        """Every leaf's draws, in leaf order; the leaf rotation carries over from one sprout to the next (a fan
        restarts it)."""
        p = self.params
        leaves: list[ChildPoint] = []
        rows: list[tuple[float, float, float, float]] = []
        rotation = 0.0
        for sprout in sprouts:
            if p.leaves < 0:
                rotation = -p.leaf_rotate / 2
                for _ in range(-p.leaves):
                    rotation = self._place_one(sprout, rotation, leaves, rows)
            else:
                rotation = self._place_one(sprout, rotation, leaves, rows)
        return LeafPlacement(leaves, rows)

    def _place_one(
        self,
        sprout: ChildPoint,
        rotation: float,
        leaves: list[ChildPoint],
        rows: list[tuple[float, float, float, float]],
    ) -> float:
        """One leaf's draws, in this order: the turn around the stem, the down angle, the scale."""
        spin = 0.0 if self.params.leaves == -1 else rotation  # a fan of one leaf does not spin
        rotation = self._turn(rotation)
        down = self._down(sprout)
        scale = self._scale(sprout, rotation)
        leaves.append(sprout)
        rows.append((spin, rotation, down, scale))
        return rotation

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
            return rotation + rotate / (-count - 1)
        return rotation + rotate + self.rng.uniform(-p.leaf_rotate_v, p.leaf_rotate_v)

    def _down(self, sprout: ChildPoint) -> float:
        """The angle away from the stem (Leaf Down Angle); unused by palmate leaves, which draw nothing for it."""
        p = self.params
        if p.leaves < 0:
            return 0.0
        if p.leaf_down_angle_v > 0.0:
            down_v = -p.leaf_down_angle_v * sprout.offset
        else:
            down_v = self.rng.uniform(-p.leaf_down_angle_v, p.leaf_down_angle_v)
        return p.leaf_down_angle + down_v

    def _scale(self, sprout: ChildPoint, rotation: float) -> float:
        """Leaf size: tapered along the parent (or across the fan), then randomly varied."""
        p = self.params
        count = p.leaves
        rotate = p.leaf_rotate
        if (count < -1) and (rotate != 0):
            f = 1 - abs((rotation - (rotate / (-count - 1))) / (rotate / 2))
        else:
            f = sprout.offset
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
        count = p.leaves
        rotate = p.leaf_rotate
        turns = [Rotation.about(np.array(pi), "Z"), Rotation.about(np.array(radians(-p.leaf_angle)), "X")]
        if rotate < 0:
            turns.append(Rotation.about(np.array(pi / 2), "Z"))
            turns.append(Rotation.about(np.where(placement.rotation < 0, pi, 0.0), "Z"))
        if (count > 0) and (rotate > 0) and p.horizontal_leaves:
            turns.append(Rotation.about(-placement.rotation + rotate, "Z"))
        if count > 0:
            turns.append(Rotation.about(placement.down, "X"))
        turns.append(Rotation.about(placement.spin, "Y" if count < 0 else "Z"))
        sprout_rotation = Quaternions.to_matrices(placement.quat)
        turns.append(sprout_rotation)
        if (p.leaf_bend != 0.0) and (count > 0):
            turns.extend(self._bend(placement, sprout_rotation))
        return turns

    def _bend(self, placement: LeafPlacement, sprout_rotation: np.ndarray) -> list[np.ndarray]:
        """Rotations that turn each leaf towards the outside of the tree (Leaf Bend)."""
        bend = self.params.leaf_bend
        normal = sprout_rotation[:, :, 1]  # the sprout's rotation applied to the y axis
        orientation_vec = sprout_rotation[:, :, 2]  # and to the z axis
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
