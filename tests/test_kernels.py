# SPDX-License-Identifier: GPL-3.0-or-later

"""The model's batched kernels give what mathutils and the per-item code give, one row at a time."""

import random
import unittest
from math import acos, atan2, pi

import helpers
import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector


def rotations():
    return helpers.module("model.rotations")


def random_directions(rng, count):
    out = np.array([[rng.gauss(0, 1) for _ in range(3)] for _ in range(count)])
    return out / np.linalg.norm(out, axis=1)[:, None]


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

    def test_axis_angle_equals_matrix_rotation(self):
        axes = random_directions(self.rng, self.N)
        ours = rotations().Rotation.axis_angle(axes, self.angles)
        for axis, angle, matrix in zip(axes, self.angles, ours, strict=True):
            np.testing.assert_allclose(matrix, np.array(Matrix.Rotation(angle, 3, axis.tolist())), atol=1e-6)

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


class RotationErrors(unittest.TestCase):
    def test_unknown_axis_and_empty_composition(self):
        with self.assertRaisesRegex(ValueError, "axis"):
            rotations().Rotation.about(np.zeros(2), "W")
        with self.assertRaisesRegex(ValueError, "at least one"):
            rotations().Rotation.compose()


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

    def test_from_matrices_round_trips(self):
        rng = random.Random(7)
        quats = []
        for _ in range(2000):
            q = Quaternion((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
            q.normalize()
            quats.append(q)
        # the four branches: also near-180-degree turns about each axis
        quats += [
            Quaternion((0.001, 1, 0, 0)).normalized(),
            Quaternion((0.001, 0, 1, 0)).normalized(),
            Quaternion((0.001, 0, 0, 1)).normalized(),
        ]
        matrices = np.array([np.array(q.to_matrix()) for q in quats])
        ours = rotations().Quaternions.from_matrices(matrices)
        rebuilt = rotations().Quaternions.to_matrices(ours)
        np.testing.assert_allclose(rebuilt, matrices, atol=1e-6)
        self.assertTrue((ours[:, 0] >= 0).all())

    def test_multiply_equals_blender(self):
        rng = random.Random(6)
        a = [
            Quaternion((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
            for _ in range(500)
        ]
        b = [
            Quaternion((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))).normalized()
            for _ in range(500)
        ]
        ours = rotations().Quaternions.multiply(
            np.array([(q.w, q.x, q.y, q.z) for q in a]), np.array([(q.w, q.x, q.y, q.z) for q in b])
        )
        for qa, qb, row in zip(a, b, ours, strict=True):
            np.testing.assert_allclose(row, np.array(qa @ qb), atol=1e-6)


class TrackFrames(unittest.TestCase):
    """TrackFrame is Blender's to_track_quat, the directions along and near the poles included."""

    SPECIAL = (
        (0, 0, 1),
        (0, 0, -1),
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (1e-5, 0, 1),
        (0, 1e-5, -1),
        (2e-4, 0, 1),
    )

    def directions(self):
        rng = random.Random(8)
        return np.concatenate([random_directions(rng, 3000), np.array(self.SPECIAL, dtype=float)])

    def test_z_up_y(self):
        d = self.directions()
        ours = rotations().TrackFrame.matrices(d, "Z", "Y")
        for v, matrix in zip(d, ours, strict=True):
            expected = np.array(Vector(v).normalized().to_track_quat("Z", "Y").to_matrix())
            np.testing.assert_allclose(matrix, expected, atol=1e-5, err_msg=str(v))

    def test_y_up_z(self):
        # a direction a hair off the up axis Z has no determined twist when Y tracks it: Blender's own answer is
        # float32 noise there (its x column varies by 1e-4 between neighbouring directions), so those two
        # near-pole specials are left out; the exact axes have a determined branch and are kept
        d = np.concatenate([random_directions(random.Random(8), 3000), np.array(self.SPECIAL[:6], dtype=float)])
        ours = rotations().TrackFrame.matrices(d, "Y", "Z")
        for v, matrix in zip(d, ours, strict=True):
            expected = np.array(Vector(v).normalized().to_track_quat("Y", "Z").to_matrix())
            np.testing.assert_allclose(matrix, expected, atol=1e-5, err_msg=str(v))

    def test_x_tracked(self):
        """The X track axis (not used by the model) takes the port's first branch; both up axes."""
        d = np.concatenate([random_directions(random.Random(14), 500), np.array(self.SPECIAL[2:6], dtype=float)])
        for up in ("Y", "Z"):
            ours = rotations().TrackFrame.matrices(d, "X", up)
            for v, matrix in zip(d, ours, strict=True):
                expected = np.array(Vector(v).normalized().to_track_quat("X", up).to_matrix())
                np.testing.assert_allclose(matrix, expected, atol=1e-5, err_msg=f"{up} {v}")

    def test_quaternions_match_too(self):
        d = random_directions(random.Random(9), 500)
        ours = rotations().TrackFrame.quaternions(d, "Z", "Y")
        for v, q in zip(d, ours, strict=True):
            expected = np.array(Vector(v).to_track_quat("Z", "Y"))
            self.assertGreater(abs(float(np.dot(q, expected))), 1 - 1e-6, str(v))  # equal up to the sign

    def test_zero_direction_is_the_identity(self):
        np.testing.assert_array_equal(rotations().TrackFrame.matrices(np.zeros((1, 3)))[0], np.eye(3))

    def test_same_axes_rejected(self):
        with self.assertRaises(ValueError):
            rotations().TrackFrame.matrices(np.zeros((1, 3)), "Z", "Z")


class TrunkFrames(unittest.TestCase):
    def test_equals_the_trunk_euler(self):
        """growth.py level 0: Euler((-rx, ry, 0), "XYZ") from the direction, as the per-stem code computed it."""
        d = random_directions(random.Random(10), 2000)
        ours = rotations().TrunkFrame.matrices(d)
        for v, matrix in zip(d, ours, strict=True):
            adir = Vector((0, 0, 1))
            adir.rotate(Vector(v).to_track_quat("Z", "Y"))
            ry = atan2(adir[0], adir[2])
            adir.rotate(Euler((0, -ry, 0)))
            rx = atan2(adir[1], adir[2])
            np.testing.assert_allclose(matrix, np.array(Euler((-rx, ry, 0), "XYZ").to_matrix()), atol=1e-4)


class CompatibleEulers(unittest.TestCase):
    def test_rebuilt_rotation_and_z_angle_equal_blender(self):
        """Quaternion.to_euler("XYZ", compatible): the same rotation back, and the same z angle (Attract Out uses it).
        The sign of a middle angle of exactly +-pi depends on float rounding, so raw angles are not compared."""
        rng = random.Random(11)
        d = random_directions(rng, 3000)
        reference = np.array([rng.uniform(0, 2 * pi) + 2 * pi for _ in range(3000)])
        frames = rotations().TrackFrame.matrices(d)
        ours = rotations().EulerXYZ.compatible(frames, np.stack([np.zeros(3000), np.zeros(3000), reference], 1))
        rebuilt = rotations().EulerXYZ.matrices(ours)
        for v, c, e, m in zip(d, reference, ours, rebuilt, strict=True):
            expected = Vector(v).to_track_quat("Z", "Y").to_euler("XYZ", Euler((0, 0, c), "XYZ"))
            np.testing.assert_allclose(m, np.array(expected.to_matrix()), atol=1e-4, err_msg=str(v))
            self.assertAlmostEqual(e[2], expected.z, delta=1e-4, msg=str(v))


class AttractUpKernel(unittest.TestCase):
    def test_equals_the_per_stem_bend(self):
        rng = random.Random(12)
        vectors = random_directions(rng, 1500) * np.array([rng.uniform(0.1, 3) for _ in range(1500)])[:, None]
        for attract_up in (-1.0, 0.5, 2.0):
            ours = rotations().AttractUp.apply(vectors, attract_up, 10)
            for v, bent in zip(vectors, ours, strict=True):
                expected = Vector(v)
                track = expected.to_track_quat("Z", "Y")
                up_axis = Vector((1, 0, 0))
                up_axis.rotate(track)
                expected.rotate(Matrix.Rotation(-self.curve_up(attract_up, track, 10), 3, up_axis.to_tuple()))
                np.testing.assert_allclose(bent, np.array(expected), atol=1e-4, err_msg=f"{attract_up} {v}")

    @staticmethod
    def curve_up(attract_up, quat, curve_res):
        """The per-stem add-on's upward rotation angle (geometry.py's curve_up before the array model)."""
        side = Vector((0, 1, 0))
        side.rotate(quat)
        side.normalize()
        direction = Vector((0, 0, 1))
        direction.rotate(quat)
        direction.normalize()
        declination = acos(max(-1.0, min(1.0, direction.z)))
        angle = attract_up * declination * abs(side.z) / curve_res
        if (-declination + angle) < -pi:
            angle = -pi + declination
        if (declination - angle) < 0:
            angle = declination
        return angle

    def test_zero_attraction_changes_nothing(self):
        vectors = random_directions(random.Random(1), 10)
        self.assertIs(rotations().AttractUp.apply(vectors, 0.0, 10), vectors)


class BezierBatches(unittest.TestCase):
    def test_points_and_tangents_equal_the_cubic_formula(self):
        rng = random.Random(13)
        p1, h1, h2, p2 = (np.array([[rng.uniform(-3, 3) for _ in range(3)] for _ in range(300)]) for _ in range(4))
        t = np.array([rng.random() for _ in range(300)])
        points = rotations().BezierBatch.points(p1, h1, h2, p2, t)
        tangents = rotations().BezierBatch.tangents(p1, h1, h2, p2, t)
        for i in range(300):
            a, b, c, d = (Vector(v[i]) for v in (p1, h1, h2, p2))
            u, s = float(1 - t[i]), float(t[i])
            expected = (u**3) * a + (3 * s * u**2) * b + (3 * s**2 * u) * c + (s**3) * d
            derivative = (-3 * u**2) * a + (-6 * s * u + 3 * u**2) * b + (-3 * s**2 + 6 * s * u) * c + (3 * s**2) * d
            np.testing.assert_allclose(points[i], np.array(expected), atol=1e-5)
            np.testing.assert_allclose(tangents[i], np.array(derivative.normalized()), atol=1e-5)


class KeyedDraws(unittest.TestCase):
    def keyed(self):
        return helpers.module("model.randomness").KeyedRandom

    def test_uniform_in_range_and_well_spread(self):
        keyed = self.keyed()
        keys = keyed.derive(keyed.root(7), 2, np.arange(100000), 0)
        u = keyed.uniform(keys, 3, 1)
        self.assertTrue(((u >= 0) & (u < 1)).all())
        self.assertAlmostEqual(float(u.mean()), 0.5, delta=0.005)
        self.assertAlmostEqual(float(u.var()), 1 / 12, delta=0.002)
        self.assertGreater(len(np.unique(u)), 99990)

    def test_deterministic_and_independent_per_key(self):
        keyed = self.keyed()
        keys = keyed.derive(keyed.root(7), 2, np.arange(1000), 0)
        first = keyed.uniform(keys, 1, 2)
        np.testing.assert_array_equal(first, keyed.uniform(keys.copy(), 1, 2))
        changed = keys.copy()
        changed[500] = keyed.derive(keyed.root(8), 2, 500, 0)[0]
        second = keyed.uniform(changed, 1, 2)
        self.assertNotEqual(first[500], second[500])
        np.testing.assert_array_equal(np.delete(first, 500), np.delete(second, 500))
        self.assertFalse(np.array_equal(first, keyed.uniform(keys, 2, 2)), "another step draws other numbers")
        self.assertFalse(np.array_equal(first, keyed.uniform(keys, 1, 3)), "another draw id draws other numbers")

    def test_between_sign_and_pick(self):
        keyed = self.keyed()
        keys = keyed.derive(keyed.root(1), 1, np.arange(5000), 0)
        between = keyed.between(keys, 0, 1, -2.0, np.full(5000, 3.0))
        self.assertTrue(((between >= -2.0) & (between < 3.0)).all())
        signs = keyed.sign(keys, 0, 2)
        self.assertEqual(set(np.unique(signs).tolist()), {-1.0, 1.0})
        counts = np.array([1, 2, 3, 7] * 1250)
        picks = keyed.pick(keys, 0, 3, counts)
        self.assertTrue(((picks >= 0) & (picks < counts)).all())
        self.assertEqual(set(picks[counts == 7].tolist()), set(range(7)))

    def test_seed_changes_everything(self):
        keyed = self.keyed()
        a = keyed.uniform(keyed.derive(keyed.root(1), 1, np.arange(100), 0), 0, 0)
        b = keyed.uniform(keyed.derive(keyed.root(2), 1, np.arange(100), 0), 0, 0)
        self.assertFalse(np.isclose(a, b).any())
