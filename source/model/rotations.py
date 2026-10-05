# SPDX-License-Identifier: GPL-3.0-or-later

"""Rotations for many points at once: (N, 3, 3) matrices with mathutils' conventions.

A row's matrix R rotates a vector as `v.rotate(R)` does: v' = R @ v. Composing turns in the order they are
applied, `Rotation.compose(a, b)` @ v == v.rotate(a); v.rotate(b). Angles are radians, maths in float64 (the
per-item model used float32 mathutils; the rows agree to about 1e-6).
"""

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


class Quaternions:
    """Quaternions as (N, 4) rows of w, x, y, z, converted as Blender does (quat_to_mat3: double maths)."""

    SQRT2 = np.sqrt(2.0)

    @classmethod
    def to_matrices(cls, quaternions: np.ndarray) -> np.ndarray:
        """(N, 3, 3) rotation matrices of unit quaternions, Blender's quat_to_mat3 row for row."""
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
