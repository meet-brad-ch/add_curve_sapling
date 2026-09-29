# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaf geometry: one small mesh (or one instancing point) per leaf sprout."""

from math import atan2, copysign, radians

from mathutils import Euler, Matrix, Vector

from .geometry import Axes


class LeafShape:
    """Template geometry of one leaf, in leaf space (the leaf grows along +z)."""

    HEX = "hex"
    RECT = "rect"
    INSTANCE_FACES = "dFace"
    INSTANCE_POINTS = "dVert"

    MESH = (HEX, RECT)
    INSTANCED = (INSTANCE_FACES, INSTANCE_POINTS)
    VERTS_PER_LEAF = {HEX: 6, RECT: 4, INSTANCE_FACES: 4, INSTANCE_POINTS: 1}

    @staticmethod
    def template(shape):
        """(vertices, faces) of a new leaf of the given shape."""
        if shape == LeafShape.HEX:
            verts = [
                Vector((0, 0, 0)),
                Vector((0.5, 0, 1 / 3)),
                Vector((0.5, 0, 2 / 3)),
                Vector((0, 0, 1)),
                Vector((-0.5, 0, 2 / 3)),
                Vector((-0.5, 0, 1 / 3)),
            ]
            return verts, [[0, 1, 2, 3], [0, 3, 4, 5]]
        if shape == LeafShape.RECT:
            verts = [Vector((0.5, 0, 0)), Vector((0.5, 0, 1)), Vector((-0.5, 0, 1)), Vector((-0.5, 0, 0))]
            return verts, [[0, 1, 2, 3]]
        if shape == LeafShape.INSTANCE_FACES:
            verts = [Vector((0.5, 0.5, 0)), Vector((0.5, -0.5, 0)), Vector((-0.5, -0.5, 0)), Vector((-0.5, 0.5, 0))]
            return verts, [[0, 3, 2, 1]]
        if shape == LeafShape.INSTANCE_POINTS:
            return [Vector((0, 0, 1))], []
        raise ValueError(f"unknown leaf shape {shape}")


class LeafSet:
    """The generated leaves: mesh data plus, per leaf, the sprout it grows from and its normal."""

    def __init__(self, shape):
        self.shape = shape
        self.vertices = []
        self.faces = []
        self.normals = []
        self.sprouts = []

    @property
    def verts_per_leaf(self):
        return LeafShape.VERTS_PER_LEAF[self.shape]


class LeafGenerator:
    """Places the leaves on the sprout points of the last branch level."""

    def __init__(self, params, rng):
        self.params = params
        self.rng = rng
        # Rotations that are the same for every vertex of every leaf, built once
        self.half_turn = Euler((0, 0, radians(180)))
        self.quarter_turn = Euler((0, 0, radians(90)))
        self.tilt = Matrix.Rotation(radians(-params.leaf_angle), 3, "X")

    def generate(self, sprouts):
        p = self.params
        leaves = LeafSet(p.leaf_shape)
        rotation = 0.0
        for sprout in sprouts:
            # A negative count grows a fan of leaves from each sprout (palmate compound leaves)
            if p.leaves < 0:
                rotation = -p.leaf_rotate / 2
                for _ in range(abs(p.leaves)):
                    rotation = self._add_leaf(leaves, sprout, rotation)
            else:
                rotation = self._add_leaf(leaves, sprout, rotation)
        return leaves

    def _add_leaf(self, leaves, sprout, rotation):
        """Append one leaf; return the rotation the next leaf continues from."""
        p = self.params
        uniform = self.rng.uniform
        count = p.leaves
        rotate = p.leaf_rotate
        rotate_v = p.leaf_rotate_v
        verts, faces = LeafShape.template(p.leaf_shape)
        normal = Axes.z()

        if count < 0:
            rot_mat = Matrix.Rotation(rotation, 3, "Y")
        else:
            rot_mat = Matrix.Rotation(rotation, 3, "Z")

        # A negative rotate angle puts each leaf on the other side of the stem from the last one
        if rotate < 0.0:
            rotation = -copysign(rotate + uniform(-rotate_v, rotate_v), rotation)
        elif count == -1:
            rot_mat = Matrix.Rotation(0, 3, "Y")
        elif count < -1:
            rotation += rotate / (-count - 1)
        else:
            rotation += rotate + uniform(-rotate_v, rotate_v)

        if count >= 0:
            if p.leaf_down_angle_v > 0.0:
                down_v = -p.leaf_down_angle_v * sprout.offset
            else:
                down_v = uniform(-p.leaf_down_angle_v, p.leaf_down_angle_v)
            down_rot = Matrix.Rotation(p.leaf_down_angle + down_v, 3, "X")

        # Scale taper along the parent, then random variation
        if (count < -1) and (rotate != 0):
            f = 1 - abs((rotation - (rotate / (-count - 1))) / (rotate / 2))
        else:
            f = sprout.offset
        if p.leaf_scale_t < 0:
            scale = p.leaf_scale * (1 - (1 - f) * -p.leaf_scale_t)
        else:
            scale = p.leaf_scale * (1 - f * p.leaf_scale_t)
        scale = scale * uniform(1 - p.leaf_scale_v, 1 + p.leaf_scale_v)
        if p.leaf_shape == LeafShape.INSTANCE_FACES:
            scale = scale * 0.1

        bend = p.leaf_bend
        if (bend != 0.0) and (count >= 0):
            bend_rotations = self._bend_rotations(sprout, bend)

        horizontal = None
        if (count > 0) and (rotate > 0) and p.horizontal_leaves:
            horizontal = Matrix.Rotation(-rotation + rotate, 3, "Z")

        for v in verts:
            v.z *= scale
            v.y *= scale
            v.x *= p.leaf_scale_x * scale

            v.rotate(self.half_turn)
            v.rotate(self.tilt)

            if rotate < 0:
                v.rotate(self.quarter_turn)
                if rotation < 0:
                    v.rotate(self.half_turn)

            if horizontal is not None:
                v.rotate(horizontal)

            if count > 0:
                v.rotate(down_rot)

            v.rotate(rot_mat)
            v.rotate(sprout.quat)

            if (bend != 0.0) and (count > 0):
                for bend_rotation in bend_rotations:
                    v.rotate(bend_rotation)

        index = len(leaves.vertices)
        if p.leaf_shape == LeafShape.INSTANCE_POINTS:
            normal = verts[0]
            normal.normalize()
            leaves.vertices.append([sprout.co.x, sprout.co.y, sprout.co.z])
        else:
            for v in verts:
                v += sprout.co
                leaves.vertices.append([v.x, v.y, v.z])
            for face in faces:
                leaves.faces.append([face[0] + index, face[1] + index, face[2] + index, face[3] + index])
        leaves.normals.extend(normal)
        leaves.sprouts.append(sprout)
        return rotation

    @staticmethod
    def _bend_rotations(sprout, bend):
        """Rotations that turn a leaf towards the outside of the tree (Leaf Bend)."""
        normal = Axes.y()
        orientation_vec = Axes.z()
        normal.rotate(sprout.quat)
        orientation_vec.rotate(sprout.quat)

        theta_pos = atan2(sprout.co.y, sprout.co.x)
        theta_bend = theta_pos - atan2(normal.y, normal.x)
        rotate_z = Matrix.Rotation(bend * theta_bend, 3, "Z")
        normal.rotate(rotate_z)
        orientation_vec.rotate(rotate_z)

        phi_bend = atan2((normal.xy).length, normal.z)
        orientation = atan2(orientation_vec.y, orientation_vec.x)
        return (
            rotate_z,
            Matrix.Rotation(orientation, 3, "X"),
            Matrix.Rotation(bend * phi_bend, 3, "Z"),
            Matrix.Rotation(-orientation, 3, "X"),
        )
