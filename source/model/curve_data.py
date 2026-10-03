# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree's curve while it grows: Bezier splines held in memory, behaving exactly like Blender's.

Writing a Blender curve point by point costs time in proportion to the number of splines (measured: 4.6 µs
per write at 2,000 splines, 70 µs at 32,000), so growing a big tree directly into Blender was quadratic.
The model grows into this curve instead (every write O(1)); build/ writes it to Blender in bulk.

Blender's rules, kept to the bit (Blender 5.2.2, curve.cc calchandleNurb_intern, rna_curve.cc):
- writing a point's position, handle or handle type recalculates the AUTO and VECTOR handles of its whole
  spline, once the spline has two or more points; radius, adding points and copies recalculate nothing;
- the recalculation reads only the neighbours' positions, so doing it once before a handle is read gives
  the same values as doing it after every write;
- all of it is float32 (the coordinates are mathutils Vectors, which are float32 too);
- a radius is clamped to 0..FLT_MAX when written.
"""

from collections.abc import Iterator

import numpy as np
from mathutils import Vector


class HandleType:
    """Blender's handle types the model uses, as Blender numbers them."""

    FREE = 0
    AUTO = 1
    VECTOR = 2
    NAMES = ("FREE", "AUTO", "VECTOR")

    @classmethod
    def code(cls, name: str) -> int:
        """The number of a handle type; raises ValueError for one the model does not use."""
        if name not in cls.NAMES:
            raise ValueError(f"handle type {name} is not used by the model (only {', '.join(cls.NAMES)})")
        return cls.NAMES.index(name)


class AutoHandles:
    """Blender's handle calculation for a non-cyclic Bezier spline (AUTO and VECTOR sides), in float32."""

    FLT_MAX = float(np.finfo(np.float32).max)
    AUTO_SCALE = np.float32(2.5614)
    FIVE = np.float32(5.0)
    TWO = np.float32(2.0)
    ONE = np.float32(1.0)
    THIRD = np.float32(1.0) / np.float32(3.0)
    MINUS_THIRD = np.float32(-1.0) / np.float32(3.0)

    @staticmethod
    def length(v: np.ndarray) -> np.ndarray:
        """len_v3 per row: sqrtf(x*x + y*y + z*z), summed in that order."""
        return np.sqrt((v[:, 0] * v[:, 0] + v[:, 1] * v[:, 1]) + v[:, 2] * v[:, 2])

    @classmethod
    def recalculate(cls, co: np.ndarray, left: np.ndarray, right: np.ndarray, h1: np.ndarray, h2: np.ndarray) -> None:
        """Recalculate in place: co, left and right are (n, 3) float32 with n >= 2; h1, h2 the handle types."""
        n = len(co)
        prev = np.empty_like(co)
        nxt = np.empty_like(co)
        prev[1:] = co[:-1]
        nxt[:-1] = co[1:]
        # a missing neighbour at an end is mirrored through the point
        prev[0] = cls.TWO * co[0] - co[1]
        nxt[n - 1] = cls.TWO * co[n - 1] - co[n - 2]
        dvec_a = co - prev
        dvec_b = nxt - co
        len_a = cls.length(dvec_a)
        len_b = cls.length(dvec_b)
        len_a[len_a == 0] = cls.ONE
        len_b[len_b == 0] = cls.ONE
        auto1 = h1 == HandleType.AUTO
        auto2 = h2 == HandleType.AUTO
        if (auto1 | auto2).any():
            cls._auto(co, left, right, (auto1, auto2), (dvec_a, dvec_b), (len_a, len_b))
        vector1 = h1 == HandleType.VECTOR
        left[vector1] = co[vector1] + dvec_a[vector1] * cls.MINUS_THIRD
        vector2 = h2 == HandleType.VECTOR
        right[vector2] = co[vector2] + dvec_b[vector2] * cls.THIRD

    @classmethod
    def _auto(
        cls,
        co: np.ndarray,
        left: np.ndarray,
        right: np.ndarray,
        auto: tuple[np.ndarray, np.ndarray],
        dvec: tuple[np.ndarray, np.ndarray],
        lengths: tuple[np.ndarray, np.ndarray],
    ) -> None:
        """AUTO sides: along the mean direction of both neighbours, scaled by the neighbour distances."""
        auto1, auto2 = auto
        dvec_a, dvec_b = dvec
        len_a, len_b = lengths
        tvec = dvec_b / len_b[:, None] + dvec_a / len_a[:, None]
        length = cls.length(tvec) * cls.AUTO_SCALE
        usable = length != 0
        safe = np.where(usable, length, cls.ONE)
        limited_a = np.minimum(len_a, cls.FIVE * len_b)
        limited_b = np.minimum(len_b, cls.FIVE * limited_a)
        side1 = usable & auto1
        side2 = usable & auto2
        left[side1] = co[side1] + tvec[side1] * (-(limited_a / safe))[side1, None]
        right[side2] = co[side2] + tvec[side2] * (limited_b / safe)[side2, None]


class CurvePoint:
    """One point of a CurveSpline, read and written like Blender's BezierSplinePoint."""

    __slots__ = ("_index", "_spline")

    def __init__(self, spline: "CurveSpline", index: int) -> None:
        self._spline = spline
        self._index = index

    @property
    def co(self) -> Vector:
        """The position (a copy; assign to change it)."""
        return self._spline.co[self._index].copy()

    @co.setter
    def co(self, value: Vector) -> None:
        self._spline.co[self._index] = value.copy()
        self._spline.touched()

    @property
    def handle_left(self) -> Vector:
        """The handle towards the previous point, recalculated first if a write asked for it."""
        self._spline.ensure_handles()
        return self._spline.left[self._index].copy()

    @handle_left.setter
    def handle_left(self, value: Vector) -> None:
        self._spline.left[self._index] = value.copy()
        self._spline.touched()

    @property
    def handle_right(self) -> Vector:
        """The handle towards the next point, recalculated first if a write asked for it."""
        self._spline.ensure_handles()
        return self._spline.right[self._index].copy()

    @handle_right.setter
    def handle_right(self, value: Vector) -> None:
        self._spline.right[self._index] = value.copy()
        self._spline.touched()

    @property
    def handle_left_type(self) -> str:
        """FREE, AUTO or VECTOR."""
        return HandleType.NAMES[self._spline.h1[self._index]]

    @handle_left_type.setter
    def handle_left_type(self, name: str) -> None:
        self._spline.h1[self._index] = HandleType.code(name)
        self._spline.touched()

    @property
    def handle_right_type(self) -> str:
        """FREE, AUTO or VECTOR."""
        return HandleType.NAMES[self._spline.h2[self._index]]

    @handle_right_type.setter
    def handle_right_type(self, name: str) -> None:
        self._spline.h2[self._index] = HandleType.code(name)
        self._spline.touched()

    @property
    def radius(self) -> float:
        """The branch radius at this point (stored as float32, clamped to 0..FLT_MAX)."""
        return self._spline.radius[self._index]

    @radius.setter
    def radius(self, value: float) -> None:
        self._spline.radius[self._index] = float(np.float32(min(max(value, 0.0), AutoHandles.FLT_MAX)))


class CurvePoints:
    """A spline's points (Blender's spline.bezier_points): indexing, length and add()."""

    def __init__(self, spline: "CurveSpline") -> None:
        self._spline = spline

    def __len__(self) -> int:
        return len(self._spline.co)

    def __getitem__(self, index: int) -> CurvePoint:
        count = len(self._spline.co)
        position = index + count if index < 0 else index
        if not 0 <= position < count:
            raise IndexError(f"point {index} of a spline with {count} points")
        return CurvePoint(self._spline, position)

    def add(self, count: int) -> None:
        """New points as Blender makes them: position and handles zero, FREE, radius 1; nothing recalculated."""
        self._spline.extend(count)


class CurveSpline:
    """One Bezier spline: the point columns, and whether its handles need recalculating before a read."""

    def __init__(self, curve: "CurveData") -> None:
        self.id_data = curve
        self.co: list[Vector] = []
        self.left: list[Vector] = []
        self.right: list[Vector] = []
        self.h1: list[int] = []
        self.h2: list[int] = []
        self.radius: list[float] = []
        self.stale = False
        self.bezier_points = CurvePoints(self)
        self.extend(1)

    def extend(self, count: int) -> None:
        """Append `count` points as Blender makes them: position and handles zero, FREE, radius 1."""
        for _ in range(count):
            self.co.append(Vector((0.0, 0.0, 0.0)))
            self.left.append(Vector((0.0, 0.0, 0.0)))
            self.right.append(Vector((0.0, 0.0, 0.0)))
            self.h1.append(HandleType.FREE)
            self.h2.append(HandleType.FREE)
            self.radius.append(1.0)

    def touched(self) -> None:
        """A position, handle or handle type was written: Blender recalculates when there are 2+ points."""
        if len(self.co) >= 2:
            self.stale = True

    def ensure_handles(self) -> None:
        """Recalculate the AUTO and VECTOR handles now, if a write since the last time asked for it."""
        if not self.stale:
            return
        self.stale = False
        left = np.array(self.left, dtype=np.float32)
        right = np.array(self.right, dtype=np.float32)
        AutoHandles.recalculate(np.array(self.co, dtype=np.float32), left, right, np.array(self.h1), np.array(self.h2))
        self.left = [Vector(v) for v in left.tolist()]
        self.right = [Vector(v) for v in right.tolist()]

    def copy_from(self, source: "CurveSpline") -> None:
        """Become an exact copy of `source`, handles included, without recalculating (as foreach_set copies)."""
        source.ensure_handles()
        self.co = [v.copy() for v in source.co]
        self.left = [v.copy() for v in source.left]
        self.right = [v.copy() for v in source.right]
        self.h1 = list(source.h1)
        self.h2 = list(source.h2)
        self.radius = list(source.radius)
        self.stale = False


class CurveSplines:
    """A curve's splines (Blender's curve.splines): new(), clear(), indexing, length and iteration."""

    SPLINE = "BEZIER"

    def __init__(self, curve: "CurveData") -> None:
        self._curve = curve
        self._splines: list[CurveSpline] = []

    def new(self, spline_type: str) -> CurveSpline:
        """A new spline of one point at the end; only Bezier splines are grown."""
        if spline_type != self.SPLINE:
            raise ValueError(f"only {self.SPLINE} splines are grown, not {spline_type}")
        spline = CurveSpline(self._curve)
        self._splines.append(spline)
        return spline

    def clear(self) -> None:
        """Remove every spline (the pruning scratch is emptied before each pass)."""
        self._splines.clear()

    def __len__(self) -> int:
        return len(self._splines)

    def __getitem__(self, index: int) -> CurveSpline:
        return self._splines[index]

    def __iter__(self) -> Iterator[CurveSpline]:
        return iter(self._splines)


class CurveData:
    """The tree's curve in memory: its splines, in the order they are grown."""

    def __init__(self) -> None:
        self.splines = CurveSplines(self)
