# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree's curve as flat arrays, with Blender's handle calculation.

Blender's rules, kept to the bit (Blender 5.2.2, curve.cc calchandleNurb_intern, rna_curve.cc): the AUTO and
VECTOR handles of a spline follow from its points' positions (recalculated here once, for every spline at
once); all of it is float32. build/ writes the arrays to Blender in bulk.
"""

from dataclasses import dataclass

import numpy as np


class HandleType:
    """Blender's handle types the model uses, as Blender numbers them."""

    FREE = 0
    AUTO = 1
    VECTOR = 2


@dataclass(frozen=True, slots=True)
class HandleSides:
    """Which points have an AUTO handle on their left (towards the previous point) and right side."""

    left: np.ndarray
    right: np.ndarray


@dataclass(frozen=True, slots=True)
class Neighbours:
    """Every point's vector from the previous point and to the next one, with their lengths."""

    to_point: np.ndarray
    from_point: np.ndarray
    length_to: np.ndarray
    length_from: np.ndarray


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
        auto = HandleSides(h1 == HandleType.AUTO, h2 == HandleType.AUTO)
        if (auto.left | auto.right).any():
            cls._auto(co, left, right, auto, Neighbours(dvec_a, dvec_b, len_a, len_b))
        vector1 = h1 == HandleType.VECTOR
        left[vector1] = co[vector1] + dvec_a[vector1] * cls.MINUS_THIRD
        vector2 = h2 == HandleType.VECTOR
        right[vector2] = co[vector2] + dvec_b[vector2] * cls.THIRD

    @classmethod
    def _auto(
        cls, co: np.ndarray, left: np.ndarray, right: np.ndarray, auto: HandleSides, neighbours: Neighbours
    ) -> None:
        """AUTO sides: along the mean direction of both neighbours, scaled by the neighbour distances."""
        n = neighbours
        tvec = n.from_point / n.length_from[:, None] + n.to_point / n.length_to[:, None]
        length = cls.length(tvec) * cls.AUTO_SCALE
        usable = length != 0
        safe = np.where(usable, length, cls.ONE)
        limited_a = np.minimum(n.length_to, cls.FIVE * n.length_from)
        limited_b = np.minimum(n.length_from, cls.FIVE * limited_a)
        side1 = usable & auto.left
        side2 = usable & auto.right
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


class CurveData:
    """The tree's curve in memory: its splines, in the order they are grown, held as flat arrays."""

    def __init__(self) -> None:
        self._flat = FlatCurve.empty()

    @property
    def spline_count(self) -> int:
        """How many splines the curve has."""
        return len(self._flat.start) - 1

    def load(self, flat: FlatCurve) -> None:
        """Become the curve the flat arrays describe (only an empty curve can be loaded)."""
        if self.spline_count:
            raise RuntimeError("only an empty curve can be loaded from flat arrays")
        self._flat = flat

    def flatten(self) -> FlatCurve:
        """The curve's flat arrays, as build/ writes them."""
        return self._flat
