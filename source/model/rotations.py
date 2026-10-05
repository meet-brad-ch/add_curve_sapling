# SPDX-License-Identifier: GPL-3.0-or-later

"""Rotations for many points at once: (N, 3, 3) matrices with mathutils' conventions.

A row's matrix R rotates a vector as `v.rotate(R)` does: v' = R @ v. Composing turns in the order they are
applied, `Rotation.compose(a, b)` @ v == v.rotate(a); v.rotate(b). Angles are radians, maths in float64 (the
per-item model used float32 mathutils; the rows agree to about 1e-6). The ports of Blender's own routines
(vec_to_quat, quat_to_mat3, mat3_normalized_to_eul2, compatible_eul) follow math_rotation_c.cc line by line.
"""

from math import pi

import numpy as np


class Rotation:
    """(N, 3, 3) rotation matrices about the fixed axes, as Matrix.Rotation(angle, 3, axis) builds them."""

    @staticmethod
    def about(angle: np.ndarray, axis: str) -> np.ndarray:
        """One matrix per angle, about "X", "Y" or "Z"; raises ValueError for another axis."""
        angle = np.asarray(angle, dtype=np.float64)
        c = np.cos(angle)
        s = np.sin(angle)
        one = np.ones_like(c)
        zero = np.zeros_like(c)
        if axis == "X":
            rows = ((one, zero, zero), (zero, c, -s), (zero, s, c))
        elif axis == "Y":
            rows = ((c, zero, s), (zero, one, zero), (-s, zero, c))
        elif axis == "Z":
            rows = ((c, -s, zero), (s, c, zero), (zero, zero, one))
        else:
            raise ValueError(f"rotation axis must be X, Y or Z, not {axis!r}")
        return np.stack([np.stack(row, axis=-1) for row in rows], axis=-2)

    @staticmethod
    def axis_angle(axes: np.ndarray, angle: np.ndarray) -> np.ndarray:
        """One matrix per row: the rotation about the row's unit axis by the row's angle (Rodrigues)."""
        x, y, z = axes[:, 0], axes[:, 1], axes[:, 2]
        c = np.cos(angle)
        s = np.sin(angle)
        t = 1.0 - c
        return np.stack(
            [
                np.stack([t * x * x + c, t * x * y - s * z, t * x * z + s * y], axis=-1),
                np.stack([t * x * y + s * z, t * y * y + c, t * y * z - s * x], axis=-1),
                np.stack([t * x * z - s * y, t * y * z + s * x, t * z * z + c], axis=-1),
            ],
            axis=-2,
        )

    @staticmethod
    def compose(*turns: np.ndarray) -> np.ndarray:
        """The rotation that applies `turns` in order: the first given is applied first, so R = t_n @ ... @ t_1.

        A turn is (N, 3, 3) or a single (3, 3) matrix, which applies to every row.
        """
        if not turns:
            raise ValueError("compose needs at least one turn")
        result = turns[0]
        for turn in turns[1:]:
            result = turn @ result
        return result

    @staticmethod
    def apply(matrices: np.ndarray, vectors: np.ndarray) -> np.ndarray:
        """Row i of the result is matrices[i] @ vectors[i]."""
        return np.einsum("nij,nj->ni", matrices, vectors)

    @staticmethod
    def unit(vectors: np.ndarray) -> np.ndarray:
        """Each row scaled to length 1 (a zero row stays zero)."""
        length = np.linalg.norm(vectors, axis=1)
        return vectors / np.where(length == 0.0, 1.0, length)[:, None]


class Quaternions:
    """Quaternions as (N, 4) rows of w, x, y, z, with Blender's conventions."""

    SQRT2 = np.sqrt(2.0)

    @classmethod
    def to_matrices(cls, quaternions: np.ndarray) -> np.ndarray:
        """(N, 3, 3) rotation matrices of unit quaternions, Blender's quat_to_mat3 row for row (double maths)."""
        q = np.asarray(quaternions, dtype=np.float64) * cls.SQRT2
        q0, q1, q2, q3 = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
        qda, qdb, qdc = q0 * q1, q0 * q2, q0 * q3
        qaa, qab, qac = q1 * q1, q1 * q2, q1 * q3
        qbb, qbc, qcc = q2 * q2, q2 * q3, q3 * q3
        # Blender stores m[column][row]; these are the rows of R = the matrix that rotates v as R @ v
        return np.stack(
            [
                np.stack([1.0 - qbb - qcc, -qdc + qab, qdb + qac], axis=-1),
                np.stack([qdc + qab, 1.0 - qaa - qcc, -qda + qbc], axis=-1),
                np.stack([-qdb + qac, qda + qbc, 1.0 - qaa - qbb], axis=-1),
            ],
            axis=-2,
        )

    @staticmethod
    def multiply(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        """Row-wise a * b (Blender's mul_qt_qtqt)."""
        a0, a1, a2, a3 = a[:, 0], a[:, 1], a[:, 2], a[:, 3]
        b0, b1, b2, b3 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
        return np.stack(
            [
                a0 * b0 - a1 * b1 - a2 * b2 - a3 * b3,
                a0 * b1 + a1 * b0 + a2 * b3 - a3 * b2,
                a0 * b2 + a2 * b0 + a3 * b1 - a1 * b3,
                a0 * b3 + a3 * b0 + a1 * b2 - a2 * b1,
            ],
            axis=-1,
        )


class TrackFrame:
    """Blender's Vector.to_track_quat: the rotation that points one of an object's axes along a direction with
    another axis up, for many directions at once (a port of vec_to_quat: the degenerate directions and the
    half-angle twist included)."""

    EPS = 1e-4
    AXES = {"X": 0, "Y": 1, "Z": 2}

    @classmethod
    def quaternions(cls, directions: np.ndarray, track: str = "Z", up: str = "Y") -> np.ndarray:
        """(N, 4) quaternions (w, x, y, z) of to_track_quat(track, up) for each row of `directions`."""
        axis = cls.AXES[track]
        upflag = cls.AXES[up]
        if axis == upflag:
            raise ValueError("the track axis and the up axis must differ")
        # Blender's vectors are float32: the length of a direction a hair's breadth off a pole rounds to 1 there,
        # which decides between the regular and the degenerate branch below
        d = np.asarray(directions, dtype=np.float32).reshape(-1, 3)
        length = np.sqrt(d[:, 0] * d[:, 0] + d[:, 1] * d[:, 1] + d[:, 2] * d[:, 2])
        safe_length = np.where(length == 0.0, np.float32(1.0), length)
        tvec = d  # mathutils passes the positive axes as vec_to_quat's codes 3..5, which keep the vector's sign
        nor, co = cls._first_turn(tvec, axis)
        angle = np.arccos(np.clip(co / safe_length, -1.0, 1.0))
        q = cls._axis_angle(Rotation.unit(nor.astype(np.float64)), angle.astype(np.float64))
        fp = Quaternions.to_matrices(q)[:, :, 2]  # the image of the z axis
        twist = cls._twist(fp, axis, upflag)
        q2 = np.concatenate(
            [
                np.cos(twist)[:, None],
                tvec.astype(np.float64) * (np.sin(twist) / safe_length.astype(np.float64))[:, None],
            ],
            axis=1,
        )
        q = Quaternions.multiply(q2, q)
        q[length == 0.0] = (1.0, 0.0, 0.0, 0.0)
        return q

    @classmethod
    def matrices(cls, directions: np.ndarray, track: str = "Z", up: str = "Y") -> np.ndarray:
        """(N, 3, 3) matrices of to_track_quat(track, up), the columns being the rotated x, y and z axes."""
        return Quaternions.to_matrices(cls.quaternions(directions, track, up))

    @classmethod
    def _first_turn(cls, tvec: np.ndarray, axis: int) -> tuple[np.ndarray, np.ndarray]:
        """(the axis of the rotation onto the tracked axis, the cosine of its angle times the length)."""
        x, y, z = tvec[:, 0], tvec[:, 1], tvec[:, 2]
        zero = np.zeros_like(x)
        if axis == 0:
            nor = np.stack([zero, -z, y], axis=1)
            nor[np.abs(y) + np.abs(z) < cls.EPS, 1] = 1.0
            return nor, x
        if axis == 1:
            nor = np.stack([z, zero, -x], axis=1)
            nor[np.abs(x) + np.abs(z) < cls.EPS, 2] = 1.0
            return nor, y
        nor = np.stack([-y, x, zero], axis=1)
        nor[np.abs(x) + np.abs(y) < cls.EPS, 0] = 1.0
        return nor, z

    @staticmethod
    def _twist(fp: np.ndarray, axis: int, upflag: int) -> np.ndarray:
        """The half angle of the twist about the tracked axis that puts the up axis up."""
        if axis == 0:
            return 0.5 * np.arctan2(fp[:, 2], fp[:, 1]) if upflag == 1 else -0.5 * np.arctan2(fp[:, 1], fp[:, 2])
        if axis == 1:
            return -0.5 * np.arctan2(fp[:, 2], fp[:, 0]) if upflag == 0 else 0.5 * np.arctan2(fp[:, 0], fp[:, 2])
        return 0.5 * np.arctan2(-fp[:, 1], -fp[:, 0]) if upflag == 0 else -0.5 * np.arctan2(-fp[:, 0], -fp[:, 1])

    @staticmethod
    def _axis_angle(axes: np.ndarray, angle: np.ndarray) -> np.ndarray:
        """Quaternions of rotations about unit axes (axis_angle_normalized_to_quat).

        The half angle's sine and cosine are float32 as in Blender: at the poles cosf(pi / 2) is -4.4e-8, not
        +6e-17, and that sign decides which way the twist below turns (atan2 of signed zeros).
        """
        half = (0.5 * angle).astype(np.float32)
        cos = np.cos(half).astype(np.float64)
        sin = np.sin(half).astype(np.float64)
        return np.concatenate([cos[:, None], axes * sin[:, None]], axis=1)


class TrunkFrame:
    """The trunk's growth frame: the direction as Euler((-rx, ry, 0), "XYZ"), the way the trunk grows (growth.py
    level 0): a frame without the roll that TrackFrame would add around a leaning trunk."""

    @staticmethod
    def matrices(directions: np.ndarray) -> np.ndarray:
        """(N, 3, 3) for unit directions."""
        d = np.asarray(directions, dtype=np.float64)
        ry = np.arctan2(d[:, 0], d[:, 2])
        rx = np.arctan2(d[:, 1], np.hypot(d[:, 0], d[:, 2]))
        return Rotation.about(ry, "Y") @ Rotation.about(-rx, "X")


class EulerXYZ:
    """Blender's compatible XYZ Euler angles of rotation matrices (Quaternion.to_euler("XYZ", compatible))."""

    GIMBAL = 16.0 * float(np.finfo(np.float32).eps)

    @classmethod
    def compatible(cls, matrices: np.ndarray, reference: np.ndarray) -> np.ndarray:
        """(N, 3) angles: of the two solutions, the one closer to the reference angles after wrapping.

        Where the middle angle is exactly +-pi the two solutions coincide as rotations; Blender's sign of that
        angle depends on float rounding, so compare rebuilt matrices (EulerXYZ.matrices), not raw angles.
        """
        first, second = cls._two_solutions(matrices)
        first = cls._wrap(first, reference)
        second = cls._wrap(second, reference)
        prefer_second = np.abs(first - reference).sum(axis=1) > np.abs(second - reference).sum(axis=1)
        return np.where(prefer_second[:, None], second, first)

    @staticmethod
    def matrices(eulers: np.ndarray) -> np.ndarray:
        """(N, 3, 3) of XYZ Euler angles: x first, then y, then z."""
        return Rotation.about(eulers[:, 2], "Z") @ Rotation.about(eulers[:, 1], "Y") @ Rotation.about(eulers[:, 0], "X")

    @classmethod
    def _two_solutions(cls, r: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """mat3_normalized_to_eul2 for XYZ; Blender's mat[c][r] is r[:, r, c]."""
        cy = np.hypot(r[:, 0, 0], r[:, 1, 0])
        regular = cy > cls.GIMBAL
        first = np.stack(
            [np.arctan2(r[:, 2, 1], r[:, 2, 2]), np.arctan2(-r[:, 2, 0], cy), np.arctan2(r[:, 1, 0], r[:, 0, 0])], 1
        )
        second = np.stack(
            [np.arctan2(-r[:, 2, 1], -r[:, 2, 2]), np.arctan2(-r[:, 2, 0], -cy), np.arctan2(-r[:, 1, 0], -r[:, 0, 0])],
            1,
        )
        gimbal = np.stack([np.arctan2(-r[:, 1, 2], r[:, 1, 1]), np.arctan2(-r[:, 2, 0], cy), np.zeros(len(r))], 1)
        return np.where(regular[:, None], first, gimbal), np.where(regular[:, None], second, gimbal)

    @staticmethod
    def _wrap(eul: np.ndarray, old: np.ndarray) -> np.ndarray:
        """compatible_eul: wrap by 2 pi towards the old angles, then flip one axis that turned more than pi."""
        eul = eul.copy()
        tau = 2 * pi
        deul = eul - old
        high = deul > pi
        eul[high] -= np.floor(deul[high] / tau + 0.5) * tau
        low = deul < -pi
        eul[low] += np.floor(-deul[low] / tau + 0.5) * tau
        deul = eul - old
        size = np.abs(deul)
        for i in range(3):
            j, k = (i + 1) % 3, (i + 2) % 3
            flip = (size[:, i] > pi) & (size[:, j] < pi / 2) & (size[:, k] < pi / 2)
            eul[flip, i] -= np.where(deul[flip, i] > 0, tau, -tau)
        return eul


class AttractUp:
    """Bending growth directions up (attractUp > 0) or down, as growth.py's _attract_up with geometry.py's
    curve_up, for many directions at once."""

    @staticmethod
    def apply(vectors: np.ndarray, attract_up: float, segments: int) -> np.ndarray:
        """The bent vectors (lengths kept)."""
        if attract_up == 0.0:
            return vectors
        directions = Rotation.unit(vectors)
        frames = TrackFrame.matrices(directions)
        side_z = np.abs(frames[:, 2, 1])  # the tracked frame's y axis, its z component
        declination = np.arccos(np.clip(directions[:, 2], -1.0, 1.0))
        angle = attract_up * declination * side_z / segments
        angle = np.where(-declination + angle < -pi, -pi + declination, angle)
        angle = np.where(declination - angle < 0.0, declination, angle)
        return Rotation.apply(Rotation.axis_angle(frames[:, :, 0], -angle), vectors)


class BezierBatch:
    """Points and tangents of many cubic Bezier segments at once (geometry.py's BezierSegment)."""

    @staticmethod
    def points(p1: np.ndarray, h1: np.ndarray, h2: np.ndarray, p2: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Position at parameter t per row (0 = p1, 1 = p2)."""
        t = t[:, None]
        u = 1.0 - t
        return (u**3) * p1 + (3.0 * t * u**2) * h1 + (3.0 * t**2 * u) * h2 + (t**3) * p2

    @staticmethod
    def tangents(p1: np.ndarray, h1: np.ndarray, h2: np.ndarray, p2: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Unit tangent at parameter t per row."""
        t = t[:, None]
        u = 1.0 - t
        derivative = (
            (-3.0 * u**2) * p1 + (-6.0 * t * u + 3.0 * u**2) * h1 + (-3.0 * t**2 + 6.0 * t * u) * h2 + (3.0 * t**2) * p2
        )
        return Rotation.unit(derivative)
