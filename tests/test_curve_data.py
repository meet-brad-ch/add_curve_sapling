# SPDX-License-Identifier: GPL-3.0-or-later

"""The model's curve (CurveData) behaves like a Blender curve, to the bit, for everything the model uses."""

import random
import unittest

import bpy
import helpers
from mathutils import Vector


def curve_data():
    return helpers.module("model.curve_data")


class HandlesMatchBlender(unittest.TestCase):
    """AUTO and VECTOR handles computed in Python equal the ones Blender computes, bit for bit."""

    TYPES = ("FREE", "AUTO", "VECTOR")

    def random_spline_writes(self, rng):
        """A random spline as the model writes it: per point co, then left type, then right type."""
        points = []
        for _ in range(rng.randint(2, 9)):
            co = Vector([rng.uniform(-5, 5) for _ in range(3)])
            points.append((co, rng.choice(self.TYPES), rng.choice(self.TYPES)))
        return points

    @staticmethod
    def write(spline, points):
        for i, (co, left, right) in enumerate(points):
            if i:
                spline.bezier_points.add(1)
            point = spline.bezier_points[-1]
            point.co = co
            point.handle_left_type = left
            point.handle_right_type = right

    def test_random_splines(self):
        rng = random.Random(7)
        blender = bpy.data.curves.new("probe", "CURVE")
        self.addCleanup(bpy.data.curves.remove, blender)
        ours = curve_data().CurveData()
        for _ in range(300):
            points = self.random_spline_writes(rng)
            self.write(blender.splines.new("BEZIER"), points)
            self.write(ours.splines.new("BEZIER"), points)
        for b, o in zip(blender.splines, ours.splines, strict=True):
            for bp, op in zip(b.bezier_points, (o.bezier_points[i] for i in range(len(o.bezier_points))), strict=True):
                self.assertEqual(bp.handle_left.to_tuple(), op.handle_left.to_tuple())
                self.assertEqual(bp.handle_right.to_tuple(), op.handle_right.to_tuple())
                self.assertEqual(bp.co.to_tuple(), op.co.to_tuple())


class BlenderWriteRules(unittest.TestCase):
    """Blender's update rules, which the model's reads depend on."""

    def setUp(self):
        self.curve = curve_data().CurveData()
        self.spline = self.curve.splines.new("BEZIER")

    def test_new_point_is_free_and_zero_with_radius_one(self):
        self.spline.bezier_points.add(1)
        point = self.spline.bezier_points[-1]
        self.assertEqual((point.handle_left_type, point.handle_right_type), ("FREE", "FREE"))
        self.assertEqual(tuple(point.co), (0.0, 0.0, 0.0))
        self.assertEqual(point.radius, 1.0)

    def test_one_point_spline_keeps_its_handles(self):
        point = self.spline.bezier_points[0]
        point.handle_right = Vector((0, 0, 1))
        point.handle_left_type = "VECTOR"
        self.assertEqual(tuple(point.handle_right), (0.0, 0.0, 1.0))

    def test_adding_a_point_recalculates_nothing(self):
        first = self.spline.bezier_points[0]
        first.handle_left_type = first.handle_right_type = "AUTO"
        first.handle_right = Vector((0, 0, 5))
        self.spline.bezier_points.add(1)
        self.assertEqual(tuple(first.handle_right), (0.0, 0.0, 5.0))

    def test_writing_a_position_recalculates_the_whole_spline(self):
        self.spline.bezier_points.add(1)
        first, second = self.spline.bezier_points[0], self.spline.bezier_points[1]
        first.handle_left_type = first.handle_right_type = "VECTOR"
        second.co = Vector((0, 0, 3))
        self.assertEqual(tuple(first.handle_right), (0.0, 0.0, 1.0))

    def test_free_handles_stick(self):
        self.spline.bezier_points.add(1)
        first = self.spline.bezier_points[0]
        first.handle_right = Vector((1, 2, 3))
        self.spline.bezier_points[1].co = Vector((0, 0, 3))
        self.assertEqual(tuple(first.handle_right), (1.0, 2.0, 3.0))

    def test_radius_is_clamped_like_blender(self):
        point = self.spline.bezier_points[0]
        point.radius = float("inf")
        self.assertEqual(point.radius, curve_data().AutoHandles.FLT_MAX)
        point.radius = -1.0
        self.assertEqual(point.radius, 0.0)

    def test_unknown_handle_type_fails(self):
        with self.assertRaisesRegex(ValueError, "ALIGNED"):
            self.spline.bezier_points[0].handle_left_type = "ALIGNED"

    def test_only_bezier_splines(self):
        with self.assertRaisesRegex(ValueError, "POLY"):
            self.curve.splines.new("POLY")

    def test_point_index_out_of_range(self):
        with self.assertRaises(IndexError):
            self.spline.bezier_points[1]

    def test_copy_is_exact_and_recalculates_nothing(self):
        self.spline.bezier_points.add(2)
        for i, z in enumerate((0, 1, 3)):
            point = self.spline.bezier_points[i]
            point.co = Vector((0, i, z))
            point.handle_left_type = point.handle_right_type = "AUTO"
        copy = self.curve.splines.new("BEZIER")
        copy.copy_from(self.spline)
        for i in range(3):
            a, b = self.spline.bezier_points[i], copy.bezier_points[i]
            self.assertEqual(
                (tuple(a.co), tuple(a.handle_left), tuple(a.handle_right), a.radius),
                (tuple(b.co), tuple(b.handle_left), tuple(b.handle_right), b.radius),
            )
            self.assertEqual((a.handle_left_type, a.handle_right_type), (b.handle_left_type, b.handle_right_type))
        self.assertIs(copy.id_data, self.curve)
        self.curve.splines.clear()
        self.assertEqual(len(self.curve.splines), 0)
