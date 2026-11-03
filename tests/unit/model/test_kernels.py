# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: kernels."""

import random
import unittest
from math import acos, atan2, cos, pi, sin

import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector
from support.addon import Addon
from support.model import Model


class KernelFixtures:
    """The kernels' module and random directions for the kernel tests."""

    @staticmethod
    def rotations():
        """The add-on's model.rotations module."""
        return Addon.module("model.rotations")

    @staticmethod
    def random_directions(rng, count):
        """Random unit vectors from the generator (shape: count x 3)."""
        out = np.array([[rng.gauss(0, 1) for _ in range(3)] for _ in range(count)])
        return out / np.linalg.norm(out, axis=1)[:, None]


class RotationMatrices(unittest.TestCase):
    """The rotation matrices (about an axis, about a vector, and composed) equal the mathutils rotations
    for 2000 random angles."""

    N = 2000

    def setUp(self):
        """Make the seeded random generator and N random angles in radians."""
        self.rng = random.Random(3)
        self.angles = np.array([self.rng.uniform(-7, 7) for _ in range(self.N)])

    def test_about_an_axis_equals_matrix_rotation(self):
        for axis in ("X", "Y", "Z"):
            ours = KernelFixtures.rotations().Rotation.about(self.angles, axis)
            self.assertEqual(ours.shape, (self.N, 3, 3))
            for angle, matrix in zip(self.angles, ours, strict=True):
                expected = np.array(Matrix.Rotation(angle, 3, axis))
                np.testing.assert_allclose(matrix, expected, atol=1e-6, err_msg=axis)

    def test_axis_angle_equals_matrix_rotation(self):
        axes = KernelFixtures.random_directions(self.rng, self.N)
        ours = KernelFixtures.rotations().Rotation.axis_angle(axes, self.angles)
        for axis, angle, matrix in zip(axes, self.angles, ours, strict=True):
            np.testing.assert_allclose(matrix, np.array(Matrix.Rotation(angle, 3, axis.tolist())), atol=1e-6)

    def test_compose_applies_the_first_turn_first(self):
        """Rotation.compose(a, b, c) @ v == v.rotate(a); v.rotate(b); v.rotate(c)."""
        a = KernelFixtures.rotations().Rotation.about(self.angles, "X")
        b = KernelFixtures.rotations().Rotation.about(self.angles[::-1], "Z")
        c = np.array(Matrix.Rotation(0.4, 3, "Y"))  # a constant turn broadcasts over the rows
        composed = KernelFixtures.rotations().Rotation.compose(a, b, c)
        for i in range(0, self.N, 97):
            v = Vector((0.3, -1.2, 2.0))
            v.rotate(Matrix.Rotation(self.angles[i], 3, "X"))
            v.rotate(Matrix.Rotation(self.angles[::-1][i], 3, "Z"))
            v.rotate(Matrix.Rotation(0.4, 3, "Y"))
            ours = KernelFixtures.rotations().Rotation.apply(composed[i : i + 1], np.array([[0.3, -1.2, 2.0]]))[0]
            np.testing.assert_allclose(ours, np.array(v), atol=1e-5)


class RotationErrors(unittest.TestCase):
    """An unknown axis and a composition of no rotations are ValueErrors."""

    def test_unknown_axis_and_empty_composition(self):
        with self.assertRaisesRegex(ValueError, "axis"):
            KernelFixtures.rotations().Rotation.about(np.zeros(2), "W")
        with self.assertRaisesRegex(ValueError, "at least one"):
            KernelFixtures.rotations().Rotation.compose()


class QuaternionMatrices(unittest.TestCase):
    """The quaternion arrays convert to matrices and multiply as mathutils does, and from_matrices returns
    the same rotations."""

    def test_to_matrices_equals_blender(self):
        rng = random.Random(5)
        quats = []
        for _ in range(2000):
            q = Quaternion((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1)))
            q.normalize()
            quats.append(q)
        ours = KernelFixtures.rotations().Quaternions.to_matrices(
            np.array([(q.w, q.x, q.y, q.z) for q in quats], np.float32)
        )
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
        ours = KernelFixtures.rotations().Quaternions.from_matrices(matrices)
        rebuilt = KernelFixtures.rotations().Quaternions.to_matrices(ours)
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
        ours = KernelFixtures.rotations().Quaternions.multiply(
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
        """3000 random unit directions and the SPECIAL directions (shape: directions x 3)."""
        rng = random.Random(8)
        return np.concatenate([KernelFixtures.random_directions(rng, 3000), np.array(self.SPECIAL, dtype=float)])

    def test_z_up_y(self):
        d = self.directions()
        ours = KernelFixtures.rotations().TrackFrame.matrices(d)
        for v, matrix in zip(d, ours, strict=True):
            expected = np.array(Vector(v).normalized().to_track_quat("Z", "Y").to_matrix())
            np.testing.assert_allclose(matrix, expected, atol=1e-5, err_msg=str(v))

    def test_quaternions_match_too(self):
        d = KernelFixtures.random_directions(random.Random(9), 500)
        ours = KernelFixtures.rotations().TrackFrame.quaternions(d)
        for v, q in zip(d, ours, strict=True):
            expected = np.array(Vector(v).to_track_quat("Z", "Y"))
            self.assertGreater(abs(float(np.dot(q, expected))), 1 - 1e-6, str(v))  # equal up to the sign

    def test_zero_direction_is_the_identity(self):
        np.testing.assert_array_equal(KernelFixtures.rotations().TrackFrame.matrices(np.zeros((1, 3)))[0], np.eye(3))


class TrunkFrames(unittest.TestCase):
    """TrunkFrame gives the trunk rotation that the per-stem code computed from each direction."""

    def test_equals_the_trunk_euler(self):
        """growth.py level 0: Euler((-rx, ry, 0), "XYZ") from the direction, as the per-stem code computed it."""
        d = KernelFixtures.random_directions(random.Random(10), 2000)
        ours = KernelFixtures.rotations().TrunkFrame.matrices(d)
        for v, matrix in zip(d, ours, strict=True):
            adir = Vector((0, 0, 1))
            adir.rotate(Vector(v).to_track_quat("Z", "Y"))
            ry = atan2(adir[0], adir[2])
            adir.rotate(Euler((0, -ry, 0)))
            rx = atan2(adir[1], adir[2])
            np.testing.assert_allclose(matrix, np.array(Euler((-rx, ry, 0), "XYZ").to_matrix()), atol=1e-4)


class CompatibleEulers(unittest.TestCase):
    """EulerXYZ.compatible gives the same rotation and z angle as mathutils to_euler with a compatible Euler."""

    def test_rebuilt_rotation_and_z_angle_equal_blender(self):
        """Quaternion.to_euler("XYZ", compatible): the same rotation back, and the same z angle (Attract Out uses it).
        The sign of a middle angle of exactly +-pi depends on float rounding, so raw angles are not compared."""
        rng = random.Random(11)
        d = KernelFixtures.random_directions(rng, 3000)
        reference = np.array([rng.uniform(0, 2 * pi) + 2 * pi for _ in range(3000)])
        frames = KernelFixtures.rotations().TrackFrame.matrices(d)
        ours = KernelFixtures.rotations().EulerXYZ.compatible(
            frames, np.stack([np.zeros(3000), np.zeros(3000), reference], 1)
        )
        rebuilt = KernelFixtures.rotations().EulerXYZ.matrices(ours)
        for v, c, e, m in zip(d, reference, ours, rebuilt, strict=True):
            expected = Vector(v).to_track_quat("Z", "Y").to_euler("XYZ", Euler((0, 0, c), "XYZ"))
            np.testing.assert_allclose(m, np.array(expected.to_matrix()), atol=1e-4, err_msg=str(v))
            self.assertAlmostEqual(e[2], expected.z, delta=1e-4, msg=str(v))


class AttractUpKernel(unittest.TestCase):
    """AttractUp bends the vectors as the per-stem code did, and an attraction of 0 returns the vectors unchanged."""

    def test_equals_the_per_stem_bend(self):
        rng = random.Random(12)
        vectors = (
            KernelFixtures.random_directions(rng, 1500) * np.array([rng.uniform(0.1, 3) for _ in range(1500)])[:, None]
        )
        for attract_up in (-1.0, 0.5, 2.0):
            ours = KernelFixtures.rotations().AttractUp.apply(vectors, attract_up, 10)
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
        vectors = KernelFixtures.random_directions(random.Random(1), 10)
        self.assertIs(KernelFixtures.rotations().AttractUp.apply(vectors, 0.0, 10), vectors)


class BezierBatches(unittest.TestCase):
    """The Bezier batch points and unit tangents equal the cubic formula on random segments."""

    def test_points_and_tangents_equal_the_cubic_formula(self):
        rng = random.Random(13)
        p1, h1, h2, p2 = (np.array([[rng.uniform(-3, 3) for _ in range(3)] for _ in range(300)]) for _ in range(4))
        t = np.array([rng.random() for _ in range(300)])
        points = KernelFixtures.rotations().BezierBatch.points(p1, h1, h2, p2, t)
        tangents = KernelFixtures.rotations().BezierBatch.tangents(p1, h1, h2, p2, t)
        for i in range(300):
            a, b, c, d = (Vector(v[i]) for v in (p1, h1, h2, p2))
            u = float(1 - t[i])
            s = float(t[i])
            expected = (u**3) * a + (3 * s * u**2) * b + (3 * s**2 * u) * c + (s**3) * d
            derivative = (-3 * u**2) * a + (-6 * s * u + 3 * u**2) * b + (-3 * s**2 + 6 * s * u) * c + (3 * s**2) * d
            np.testing.assert_allclose(points[i], np.array(expected), atol=1e-5)
            np.testing.assert_allclose(tangents[i], np.array(derivative.normalized()), atol=1e-5)


class KeyedDraws(unittest.TestCase):
    """KeyedRandom draws stay in their ranges and spread evenly, give the same numbers for the same key, step
    and draw, and give other numbers for another key, step, draw or seed."""

    def keyed(self):
        """The add-on's KeyedRandom class."""
        return Addon.module("model.randomness").KeyedRandom

    def test_pick_stays_below_the_count(self):
        keyed = self.keyed()
        keys = keyed.derive(keyed.root(7), 2, np.arange(100000), 0)
        counts = np.arange(100000) % 7 + 1
        picked = keyed.pick(keys, 0, 1, counts)
        self.assertTrue(((picked >= 0) & (picked < counts)).all())

    def test_pick_from_nothing_raises(self):
        keyed = self.keyed()
        keys = keyed.derive(keyed.root(7), 2, np.arange(3), 0)
        with self.assertRaisesRegex(ValueError, "at least one item"):
            keyed.pick(keys, 0, 1, np.array([2, 0, 1]))

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


class SwayMatchesTheScalarFormula(unittest.TestCase):
    """The joints' wind (one array operation) is the rig's per-bone formula computed with mathutils vectors: the
    rig's F-curves and the node wind's attributes take the same numbers. Lengths, waves, phases and frequencies
    are equal to the bit; the gust bends follow a bone's direction, whose last float32 bit mathutils' normalize
    rounds differently on a few bones (Joints._directions), so they agree to two float32 units."""

    CASES = (
        {"levels": 2, "jointStep": (2, 2, 1, 1)},
        {"levels": 3, "branches": (0, 30, 10, 0), "windStrength": 3.0, "gustStrength": 2.0, "loopFrames": 48},
        {"levels": 3, "branches": (0, 30, 10, 0), "prune": True, "jointLevels": 2},
    )

    @staticmethod
    def reference(joints, model, rng):
        """Per bone, in bone order: wind1, wind2, gust_z, gust_x, offset_x, offset_z, frequency1, frequency2."""
        flat = joints.flat
        p = model.params
        rows = []
        for c in np.flatnonzero(joints.eligible).tolist():
            start = int(joints.starts[c])
            size = int(joints.sizes[c])
            points = [Vector(flat.co[start + i].tolist()) for i in range(size)]
            segments = size - 1
            step = int(joints.step[c])
            spline_length = segments * (points[0] - points[1]).length
            offsets = [rng.uniform(0, 2 * pi), rng.uniform(0, 2 * pi)]
            frequencies = model.branch_frequencies(spline_length)
            tail = 0
            for n in range(0, segments, step):
                tail = min(tail + step, segments)
                a0 = (
                    2 * (spline_length / segments) * (1 - n / (segments + 1)) / max(float(flat.radius[start + n]), 1e-6)
                )
                a0 = a0 * min(step, segments)
                a1 = (p.wind / 50) * a0
                direction = points[tail] - points[n]
                direction.normalize()
                gust = (p.wind * p.gust / 50) * a0
                sway = [a1, a1 * model.SECOND_WAVE_AMPLITUDE, -direction[0] * gust, direction[2] * gust]
                if joints.link_spline[c] < 0 and n <= step:  # the trunk base holds still
                    sway = [0.0, 0.0, 0.0, 0.0]
                rows.append([*(v * (pi / 180) for v in sway), *offsets, frequencies.first, frequencies.second])
        return np.array(rows)

    def test_sway_equals_the_per_bone_formula(self):
        wind_model = Addon.module("model.wind_model").WindModel
        for case in self.CASES:
            with self.subTest(case=case):
                settings = Addon.resolve_preset("quaking_aspen.py")
                settings.update(case)
                model = Model.grow(settings)
                joints = Model.joints(settings, model)
                wind = wind_model(Model.wind_params(settings, model.params), 24.0)
                joints_module = Addon.module("model.joints")
                sway = joints_module.JointSwayBuilder(joints).sway(wind, random.Random(5))
                expected = self.reference(joints, wind, random.Random(5))
                ours = np.stack(
                    [
                        sway.wind1, sway.wind2, sway.gust_z, sway.gust_x,
                        sway.offset_x, sway.offset_z, sway.frequency1, sway.frequency2,
                    ],
                    axis=1,
                )  # fmt: skip
                self.assertGreater(len(expected), 20)
                exact = [0, 1, 4, 5, 6, 7]
                np.testing.assert_array_equal(ours[:, exact], expected[:, exact])
                np.testing.assert_allclose(ours[:, 2:4], expected[:, 2:4], rtol=2.4e-7, atol=1e-12)


class TrunkClumpMatchesMathutils(unittest.TestCase):
    """The clump's trunk positions (float32 arrays) are the ones mathutils vectors placed, bit for bit, including
    which candidate points are too close to an earlier trunk."""

    @staticmethod
    def reference(params, rng, tries):
        """The further trunk positions that the mathutils loop placed, as lists of x, y and z."""
        gap = 2.5 * params.scale * params.length[0] * params.ratio * params.scale0
        radius = max((params.trunks * params.scale * params.ratio / 2.5) ** 0.5, gap * params.trunks**0.5)
        placed = [Vector((0.0, 0.0, 0.0))]
        for _ in range(params.trunks - 1):
            for _ in range(tries):
                distance = radius * rng.random() ** 0.5
                angle = rng.uniform(0, 2 * pi)
                point = Vector((distance * cos(angle), distance * sin(angle), 0.0))
                if all((point - other).length >= gap for other in placed):
                    placed.append(point)
                    break
        return [[point.x, point.y, point.z] for point in placed[1:]]

    def test_positions_equal_the_vector_loop(self):
        clump = Addon.module("model.branching").TrunkClump
        for seed in range(200):
            settings = Addon.resolve_preset("quaking_aspen.py")
            settings.update(trunks=2 + seed % 5, ratio=0.02 + 0.01 * (seed % 7), seed=seed)
            params = Model.params(settings)
            ours = [position.tolist() for position in clump(params, random.Random(seed)).positions()]
            expected = self.reference(params, random.Random(seed), clump.TRIES)
            self.assertEqual(ours, expected, f"seed {seed}")
