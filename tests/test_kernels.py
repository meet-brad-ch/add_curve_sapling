# SPDX-License-Identifier: GPL-3.0-or-later

"""The model's batched rotation kernels give what mathutils gives, one row at a time."""

import random
import unittest

import helpers
import numpy as np
from mathutils import Matrix, Quaternion, Vector


def rotations():
    return helpers.module("model.rotations")


class RotationMatrices(unittest.TestCase):
    N = 2000

    def setUp(self):
        self.rng = random.Random(3)
        self.angles = np.array([self.rng.uniform(-7, 7) for _ in range(self.N)])

    def test_about_an_axis_equals_matrix_rotation(self):
        for axis in ("X", "Y", "Z"):
            ours = rotations().Rotation.about(self.angles, axis)
            self.assertEqual(ours.shape, (self.N, 3, 3))
            for angle, matrix in zip(self.angles, ours, strict=True):
                expected = np.array(Matrix.Rotation(angle, 3, axis))
                np.testing.assert_allclose(matrix, expected, atol=1e-6, err_msg=axis)

    def test_compose_applies_the_first_turn_first(self):
        """Rotation.compose(a, b, c) @ v == v.rotate(a); v.rotate(b); v.rotate(c)."""
        a = rotations().Rotation.about(self.angles, "X")
        b = rotations().Rotation.about(self.angles[::-1], "Z")
        c = np.array(Matrix.Rotation(0.4, 3, "Y"))  # a constant turn broadcasts over the rows
        composed = rotations().Rotation.compose(a, b, c)
        for i in range(0, self.N, 97):
            v = Vector((0.3, -1.2, 2.0))
            v.rotate(Matrix.Rotation(self.angles[i], 3, "X"))
            v.rotate(Matrix.Rotation(self.angles[::-1][i], 3, "Z"))
            v.rotate(Matrix.Rotation(0.4, 3, "Y"))
            ours = rotations().Rotation.apply(composed[i : i + 1], np.array([[0.3, -1.2, 2.0]]))[0]
            np.testing.assert_allclose(ours, np.array(v), atol=1e-5)


class QuaternionMatrices(unittest.TestCase):
    def test_to_matrices_equals_blender(self):
        rng = random.Random(5)
        quats = []
        for _ in range(2000):
            q = Quaternion((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
            q.normalize()
            quats.append(q)
        ours = rotations().Quaternions.to_matrices(np.array([(q.w, q.x, q.y, q.z) for q in quats], np.float32))
        for q, matrix in zip(quats, ours, strict=True):
            np.testing.assert_allclose(matrix, np.array(q.to_matrix()), atol=1e-6)
