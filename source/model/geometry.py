# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry of the Weber-Penn model: axes, angles, crown shapes and bezier segments.

Expression shapes are kept exactly as in the original add-on: mathutils works in float32, so
reordering an expression changes the generated trees.
"""

from math import acos, atan2, cos, degrees, pi, radians, sin

from mathutils import Vector


class Axes:
    """Unit axes; each call returns a new vector, so callers may rotate it in place."""

    @staticmethod
    def x():
        return Vector((1, 0, 0))

    @staticmethod
    def y():
        return Vector((0, 1, 0))

    @staticmethod
    def z():
        return Vector((0, 0, 1))


class Angles:
    """Angle arithmetic used by stem growth."""

    TAU = 2 * pi

    @staticmethod
    def to_radians(values):
        return [radians(a) for a in values]

    @staticmethod
    def declination(quat):
        """Angle in degrees between the z axis and the z axis rotated by quat."""
        direction = Axes.z()
        direction.rotate(quat)
        direction.normalize()
        # float32 rounding can push z just outside [-1, 1]
        return degrees(acos(max(-1.0, min(1.0, direction.z))))

    @staticmethod
    def curve_up(attract_up, quat, curve_res):
        """Angle of upward rotation of one segment due to attractUp."""
        side = Axes.y()
        side.rotate(quat)
        side.normalize()

        dec = radians(Angles.declination(quat))
        angle = attract_up * dec * abs(side.z) / curve_res
        if (-dec + angle) < -pi:
            angle = -pi + dec
        if (dec - angle) < 0:
            angle = dec
        return angle

    @staticmethod
    def mean(a1, a2, fac):
        """Interpolate between two angles through their unit vectors."""
        x1 = sin(a1)
        y1 = cos(a1)
        x2 = sin(a2)
        y2 = cos(a2)
        x = x1 + (x2 - x1) * fac
        y = y1 + (y2 - y1) * fac
        return atan2(x, y)


class CrownShape:
    """Shape ratio functions of the Weber-Penn paper, plus custom (8) and pruning envelope (9)."""

    CUSTOM = 8
    ENVELOPE = 9

    @staticmethod
    def ratio(shape, ratio, prune_width_peak=0.0, prune_power_high=0.0, prune_power_low=0.0, custom=None):
        if shape == 0:
            return 0.05 + 0.95 * ratio
        if shape == 1:
            return 0.2 + 0.8 * sin(pi * ratio)
        if shape == 2:
            return 0.2 + 0.8 * sin(0.5 * pi * ratio)
        if shape == 3:
            return 1.0
        if shape == 4:
            return 0.5 + 0.5 * ratio
        if shape == 5:
            if ratio <= 0.7:
                return 0.05 + 0.95 * ratio / 0.7
            return 0.05 + 0.95 * (1.0 - ratio) / 0.3
        if shape == 6:
            return 1.0 - 0.8 * ratio
        if shape == 7:
            if ratio <= 0.7:
                return 0.5 + 0.5 * ratio / 0.7
            return 0.5 + 0.5 * (1.0 - ratio) / 0.3
        if shape == CrownShape.CUSTOM:
            return CrownShape._custom(ratio, custom)
        if shape == CrownShape.ENVELOPE:
            if (ratio < (1 - prune_width_peak)) and (ratio > 0.0):
                return (ratio / (1 - prune_width_peak)) ** prune_power_high
            if (ratio >= (1 - prune_width_peak)) and (ratio < 1.0):
                return ((1 - ratio) / prune_width_peak) ** prune_power_low
            return 0.0
        if shape == 10:
            return 0.5 + 0.5 * (1 - ratio)
        raise ValueError(f"unknown crown shape {shape}")

    @staticmethod
    def _custom(ratio, custom):
        """Two eased segments through (base, custom[0]), (custom[2], custom[1]) and (top, custom[3])."""
        r = 1 - ratio
        if r == 1:
            return custom[3]
        if r >= custom[2]:
            pos = (r - custom[2]) / (1 - custom[2])
            pos = pos * pos
            return (pos * (custom[3] - custom[1])) + custom[1]
        pos = r / custom[2]
        pos = 1 - (1 - pos) * (1 - pos)
        return (pos * (custom[1] - custom[0])) + custom[0]

    @staticmethod
    def auto_taper(length, taper, shape, shape_s, levels, custom_shape):
        """Taper per level so that stems end at the radius their children start with."""
        taper_s = []
        for i, t in enumerate(length):
            if i == 0:
                shp = 1.0
            elif i == 1:
                shp = CrownShape.ratio(shape, 0, custom=custom_shape)
            else:
                shp = CrownShape.ratio(shape_s, 0)
            taper_s.append(t * shp)

        taper_p = []
        for i in range(len(taper_s)):
            pm = 1
            for x in range(i + 1):
                pm *= taper_s[x]
            taper_p.append(pm)

        taper_r = [sum(taper_p[i:levels]) for i in range(len(taper_p))]

        taper_t = []
        for i in range(len(taper_r)):
            try:
                taper_t.append(taper_p[i] / taper_r[i])
            except ZeroDivisionError:
                taper_t.append(1.0)

        return [t * taper[i] for i, t in enumerate(taper_t)]


class BezierSegment:
    """One cubic bezier segment between two curve points."""

    __slots__ = ("h1", "h2", "p1", "p2")

    def __init__(self, p1, h1, h2, p2):
        self.p1 = p1
        self.h1 = h1
        self.h2 = h2
        self.p2 = p2

    @classmethod
    def between(cls, point_a, point_b):
        return cls(point_a.co, point_a.handle_right, point_b.handle_left, point_b.co)

    def point(self, t):
        return (
            ((1 - t) ** 3) * self.p1
            + (3 * t * (1 - t) ** 2) * self.h1
            + (3 * (t**2) * (1 - t)) * self.h2
            + (t**3) * self.p2
        )

    def tangent(self, t):
        """Unit tangent at t."""
        return (
            (-3 * (1 - t) ** 2) * self.p1
            + (-6 * t * (1 - t) + 3 * (1 - t) ** 2) * self.h1
            + (-3 * (t**2) + 6 * t * (1 - t)) * self.h2
            + (3 * t**2) * self.p2
        ).normalized()
