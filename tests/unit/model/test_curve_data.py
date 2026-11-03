# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: curve data."""

import random
import unittest

import bpy
import numpy as np
from mathutils import Vector
from support.addon import Addon
from support.evaluated import Evaluated


def curve_data():
    return Addon.module("model.curve_data")


def random_splines(rng, count):
    """Random splines as the model makes them: per point a position and the two handle types."""
    types = ("FREE", "AUTO", "VECTOR")
    splines = []
    for _ in range(count):
        points = []
        for _ in range(rng.randint(2, 9)):
            co = Vector([rng.uniform(-5, 5) for _ in range(3)])
            points.append((co, rng.choice(types), rng.choice(types)))
        splines.append(points)
    return splines


def flat_of(splines):
    """The splines as a FlatCurve with recalculated handles (FREE handles stay zero)."""
    module = curve_data()
    co = np.array([tuple(p[0]) for s in splines for p in s], dtype=np.float32).reshape(-1, 3)
    h1 = np.array([getattr(module.HandleType, p[1]) for s in splines for p in s], dtype=np.int8)
    h2 = np.array([getattr(module.HandleType, p[2]) for s in splines for p in s], dtype=np.int8)
    sizes = np.array([len(s) for s in splines], dtype=np.int64)
    start = np.concatenate([[0], np.cumsum(sizes)])
    left = np.zeros_like(co)
    right = np.zeros_like(co)
    points = module.HandleArrays(co=co, left=left, right=right, h1=h1, h2=h2)
    module.AutoHandles.recalculate_flat(points, start[:-1], start[1:] - 1)
    radius = np.ones(len(co), dtype=np.float32)
    return module.FlatCurve(co=co, left=left, right=right, h1=h1, h2=h2, radius=radius, start=start)


def write_to_blender(curve, splines):
    for points in splines:
        spline = curve.splines.new("BEZIER")
        for i, (co, left, right) in enumerate(points):
            if i:
                spline.bezier_points.add(1)
            point = spline.bezier_points[-1]
            point.co = co
            point.handle_left_type = left
            point.handle_right_type = right


class HandlesMatchBlender(unittest.TestCase):
    """AUTO and VECTOR handles computed for all splines at once equal the ones Blender computes, bit for bit."""

    def test_random_splines(self):
        splines = random_splines(random.Random(7), 300)
        blender = bpy.data.curves.new("probe", "CURVE")
        self.addCleanup(bpy.data.curves.remove, blender)
        write_to_blender(blender, splines)
        flat = flat_of(splines)
        for name, column in (("co", flat.co), ("handle_left", flat.left), ("handle_right", flat.right)):
            expected = np.concatenate([Evaluated.floats(s.bezier_points, name, 3) for s in blender.splines]).reshape(
                -1, 3
            )
            # FREE handles are whatever was stored (zero here, Blender's own value there): compare the rest
            kinds = flat.h1 if name == "handle_left" else flat.h2
            computed = (kinds != curve_data().HandleType.FREE) | (name == "co")
            np.testing.assert_array_equal(column[computed], expected[computed], err_msg=name)

    def test_one_point_splines_rejected(self):
        auto = curve_data().AutoHandles
        co = np.zeros((1, 3), np.float32)
        types = np.zeros(1, np.int8)
        points = curve_data().HandleArrays(co=co, left=co.copy(), right=co.copy(), h1=types, h2=types.copy())
        with self.assertRaisesRegex(ValueError, "two or more points"):
            auto.recalculate_flat(points, np.array([0]), np.array([0]))


class FlatCurves(unittest.TestCase):
    """A curve loaded from flat arrays holds them as they are; it loads once, and parts concatenate."""

    def loaded(self):
        splines = random_splines(random.Random(2), 4)
        flat = flat_of(splines)
        curve = curve_data().CurveData()
        curve.load(flat)
        return splines, flat, curve

    def test_loaded_curve_holds_the_arrays(self):
        splines, flat, curve = self.loaded()
        self.assertEqual(curve.spline_count, 4)
        self.assertEqual(flat.sizes.tolist(), [len(s) for s in splines])
        self.assertIs(curve.flatten(), flat)
        self.assertEqual(curve_data().CurveData().spline_count, 0)

    def test_reloading_rejected(self):
        _, flat, curve = self.loaded()
        with self.assertRaisesRegex(RuntimeError, "only an empty curve"):
            curve.load(flat)

    def test_concatenate(self):
        _, flat, _ = self.loaded()
        both = curve_data().FlatCurve.concatenate([flat, flat])
        self.assertEqual(both.start.tolist(), flat.start.tolist() + (flat.start[1:] + flat.start[-1]).tolist())
        np.testing.assert_array_equal(both.co[flat.start[-1] :], flat.co)
        with self.assertRaises(ValueError):
            curve_data().FlatCurve.concatenate([])
