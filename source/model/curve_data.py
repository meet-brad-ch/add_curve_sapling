# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree's curve as flat arrays, with Blender's handle calculation.

Blender's rules, kept to the bit (Blender 5.2.2, curve.cc calchandleNurb_intern, rna_curve.cc): the AUTO and
VECTOR handles of a spline follow from its points' positions (recalculated here once, for every spline at
once); all of it is float32. build/ writes the arrays to Blender in bulk.
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
    """Blender's handle calculation for non-cyclic Bezier splines (AUTO and VECTOR sides), in float32."""

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
    def recalculate_flat(
        cls,
        co: np.ndarray,
        left: np.ndarray,
        right: np.ndarray,
        h1: np.ndarray,
        h2: np.ndarray,
        first: np.ndarray,
        last: np.ndarray,
    ) -> None:
        """Recalculate every spline of a flat point array at once (the arithmetic of calchandleNurb_intern).

        co, left, right are (N, 3) float32 of all splines' points in order; first/last are the index of each
        spline's first and last point. Every spline must have two or more points (one-point splines keep their
        handles in Blender).
        """
        if (first == last).any():
            raise ValueError("recalculate_flat needs splines of two or more points")
        # zeros, not empty: a one-point spline between others has no neighbours set here and must read nothing random
        prev = np.zeros_like(co)
        nxt = np.zeros_like(co)
        prev[1:] = co[:-1]
        nxt[:-1] = co[1:]
        # a missing neighbour at a spline's end is mirrored through the point
        prev[first] = cls.TWO * co[first] - co[first + 1]
        nxt[last] = cls.TWO * co[last] - co[last - 1]
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


class FlatCurve:
    """Every spline's points in one array per column, in spline order, with the splines' start offsets.

    co, left, right: (N, 3) float32; h1, h2: (N,) int8 handle types; radius: (N,) float32;
    start: (S + 1,) int64, spline i holds points start[i]:start[i + 1]. What build/ writes to Blender in bulk.
    """

    def __init__(
        self,
        co: np.ndarray,
        left: np.ndarray,
        right: np.ndarray,
        h1: np.ndarray,
        h2: np.ndarray,
        radius: np.ndarray,
        start: np.ndarray,
    ) -> None:
        self.co = co
        self.left = left
        self.right = right
        self.h1 = h1
        self.h2 = h2
        self.radius = radius
        self.start = start

    @classmethod
    def empty(cls) -> "FlatCurve":
        """A curve of no splines."""
        none = np.zeros((0, 3), dtype=np.float32)
        types = np.zeros(0, dtype=np.int8)
        return cls(none, none.copy(), none.copy(), types, types.copy(), np.zeros(0, np.float32), np.zeros(1, np.int64))

    @property
    def sizes(self) -> np.ndarray:
        """Points per spline."""
        return np.diff(self.start)

    @classmethod
    def concatenate(cls, parts: list["FlatCurve"]) -> "FlatCurve":
        """The parts' splines one after another."""
        if not parts:
            raise ValueError("concatenate needs at least one part")
        offsets = np.cumsum([0] + [part.start[-1] for part in parts[:-1]])
        start = np.concatenate(
            [parts[0].start[:1]] + [part.start[1:] + offset for part, offset in zip(parts, offsets, strict=True)]
        )
        return cls(
            np.concatenate([part.co for part in parts]),
            np.concatenate([part.left for part in parts]),
            np.concatenate([part.right for part in parts]),
            np.concatenate([part.h1 for part in parts]),
            np.concatenate([part.h2 for part in parts]),
            np.concatenate([part.radius for part in parts]),
            start,
        )


class FlatPoint:
    """One point of a spline, read like Blender's BezierSplinePoint (read-only: the arrays are final)."""

    __slots__ = ("_flat", "_index")

    def __init__(self, flat: FlatCurve, index: int) -> None:
        self._flat = flat
        self._index = index

    @property
    def co(self) -> Vector:
        """The position."""
        return Vector(self._flat.co[self._index].tolist())

    @property
    def handle_left(self) -> Vector:
        """The handle towards the previous point."""
        return Vector(self._flat.left[self._index].tolist())

    @property
    def handle_right(self) -> Vector:
        """The handle towards the next point."""
        return Vector(self._flat.right[self._index].tolist())

    @property
    def handle_left_type(self) -> str:
        """FREE, AUTO or VECTOR."""
        return HandleType.NAMES[self._flat.h1[self._index]]

    @property
    def handle_right_type(self) -> str:
        """FREE, AUTO or VECTOR."""
        return HandleType.NAMES[self._flat.h2[self._index]]

    @property
    def radius(self) -> float:
        """The branch radius at this point."""
        return float(self._flat.radius[self._index])


class FlatPoints:
    """A spline's points (Blender's spline.bezier_points): indexing and length."""

    def __init__(self, flat: FlatCurve, start: int, end: int) -> None:
        self._flat = flat
        self._start = start
        self._end = end

    def __len__(self) -> int:
        return self._end - self._start

    def __getitem__(self, index: int) -> FlatPoint:
        count = len(self)
        position = index + count if index < 0 else index
        if not 0 <= position < count:
            raise IndexError(f"point {index} of a spline with {count} points")
        return FlatPoint(self._flat, self._start + position)


class FlatSpline:
    """One spline of the curve: its columns as array slices, and its points."""

    def __init__(self, curve: "CurveData", flat: FlatCurve, index: int) -> None:
        self.id_data = curve
        start, end = int(flat.start[index]), int(flat.start[index + 1])
        self.co = flat.co[start:end]
        self.left = flat.left[start:end]
        self.right = flat.right[start:end]
        self.h1 = flat.h1[start:end]
        self.h2 = flat.h2[start:end]
        self.radius = flat.radius[start:end]
        self.bezier_points = FlatPoints(flat, start, end)


class FlatSplines:
    """The curve's splines (Blender's curve.splines): indexing, length and iteration."""

    def __init__(self, curve: "CurveData", flat: FlatCurve) -> None:
        self._curve = curve
        self._flat = flat

    def __len__(self) -> int:
        return len(self._flat.start) - 1

    def __getitem__(self, index: int) -> FlatSpline:
        count = len(self)
        position = index + count if index < 0 else index
        if not 0 <= position < count:
            raise IndexError(f"spline {index} of a curve with {count} splines")
        return FlatSpline(self._curve, self._flat, position)

    def __iter__(self) -> Iterator[FlatSpline]:
        return (self[i] for i in range(len(self)))


class CurveData:
    """The tree's curve in memory: its splines, in the order they are grown, held as flat arrays."""

    def __init__(self, flat: FlatCurve | None = None) -> None:
        self._flat = flat if flat is not None else FlatCurve.empty()
        self.splines = FlatSplines(self, self._flat)

    def load(self, flat: FlatCurve) -> None:
        """Become the curve the flat arrays describe (only an empty curve can be loaded)."""
        if len(self.splines):
            raise RuntimeError("only an empty curve can be loaded from flat arrays")
        self._flat = flat
        self.splines = FlatSplines(self, flat)

    def flatten(self) -> FlatCurve:
        """The curve's flat arrays, as build/ writes them."""
        return self._flat
