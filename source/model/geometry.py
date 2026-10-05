# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry of the Weber-Penn model: axes, angles, crown shapes and bezier segments.

Expression shapes are kept exactly as in the original add-on: mathutils works in float32, so
reordering an expression changes the generated trees.
"""

from collections.abc import Iterable, Sequence
from math import pi, radians, sin
from typing import Final

import numpy as np


class Angles:
    """Angle arithmetic of the tree model (growth directions, wind phases)."""

    TAU = 2 * pi

    @staticmethod
    def to_radians(values: Iterable[float]) -> list[float]:
        """Per-level angles from degrees (as the settings hold them) to radians, as a new list."""
        return [radians(a) for a in values]

    @staticmethod
    def means(a1: np.ndarray, a2: np.ndarray, fac: float) -> np.ndarray:
        """mean() for arrays of angles."""
        x1, y1 = np.sin(a1), np.cos(a1)
        x2, y2 = np.sin(a2), np.cos(a2)
        return np.arctan2(x1 + (x2 - x1) * fac, y1 + (y2 - y1) * fac)


class Bezier:
    """Blender's enum values for bezier splines and their handles."""

    SPLINE: Final = "BEZIER"
    AUTO: Final = "AUTO"
    VECTOR: Final = "VECTOR"


class CrownShape:
    """Shape ratio functions of the Weber-Penn paper (plus a custom shape), and the pruning envelope."""

    CONICAL = 0
    SPHERICAL = 1
    HEMISPHERICAL = 2
    CYLINDRICAL = 3
    TAPERED_CYLINDRICAL = 4
    FLAME = 5
    INVERSE_CONICAL = 6
    TEND_FLAME = 7
    CUSTOM = 8
    INVERSE_TAPERED_CYLINDRICAL = 10

    @staticmethod
    def ratio(shape: int, ratio: float, custom: Sequence[float] | None = None) -> float:
        """The shape's factor at `ratio` (0..1); CUSTOM takes its four control values in `custom`."""
        if shape == CrownShape.CUSTOM:
            return CrownShape._custom(ratio, custom)  # type: ignore[arg-type]  # only the main shape can be CUSTOM, and it always comes with custom
        if shape not in CrownShape._SHAPES:
            raise ValueError(f"unknown crown shape {shape}")
        return CrownShape._SHAPES[shape](ratio)

    @staticmethod
    def ratios(shape: int, ratio: np.ndarray, custom: Sequence[float] | None = None) -> np.ndarray:
        """ratio() for an array of ratios (0..1)."""
        r = np.asarray(ratio, dtype=np.float64)
        if shape == CrownShape.CUSTOM:
            return CrownShape._customs(r, custom)  # type: ignore[arg-type]  # as ratio(): CUSTOM always comes with custom
        if shape not in CrownShape._ARRAY_SHAPES:
            raise ValueError(f"unknown crown shape {shape}")
        return CrownShape._ARRAY_SHAPES[shape](r)

    @staticmethod
    def _flames(ratio: np.ndarray) -> np.ndarray:
        return np.where(ratio <= 0.7, 0.05 + 0.95 * ratio / 0.7, 0.05 + 0.95 * (1.0 - ratio) / 0.3)

    @staticmethod
    def _tend_flames(ratio: np.ndarray) -> np.ndarray:
        return np.where(ratio <= 0.7, 0.5 + 0.5 * ratio / 0.7, 0.5 + 0.5 * (1.0 - ratio) / 0.3)

    @staticmethod
    def _customs(ratio: np.ndarray, custom: Sequence[float]) -> np.ndarray:
        """_custom() for arrays."""
        r = 1.0 - ratio
        upper = (r - custom[2]) / (1 - custom[2])
        upper = upper * upper * (custom[3] - custom[1]) + custom[1]
        lower = r / custom[2]
        lower = (1 - (1 - lower) * (1 - lower)) * (custom[1] - custom[0]) + custom[0]
        return np.where(r == 1.0, custom[3], np.where(r >= custom[2], upper, lower))

    @staticmethod
    def envelope(ratio: float, peak: float, power_high: float, power_low: float) -> float:
        """Pruning envelope width factor: rises to 1 at `peak` from the top, then falls to 0 at both ends."""
        if (ratio < (1 - peak)) and (ratio > 0.0):
            return (ratio / (1 - peak)) ** power_high
        if (ratio >= (1 - peak)) and (ratio < 1.0):
            return ((1 - ratio) / peak) ** power_low
        return 0.0

    @staticmethod
    def envelopes(ratio: np.ndarray, peak: float, power_high: float, power_low: float) -> np.ndarray:
        """envelope() for an array of ratios."""
        r = np.asarray(ratio, dtype=np.float64)
        with np.errstate(invalid="ignore", divide="ignore"):
            rising = (np.clip(r, 0.0, None) / (1 - peak)) ** power_high
            falling = (np.clip(1 - r, 0.0, None) / peak) ** power_low
        return np.where((r < 1 - peak) & (r > 0.0), rising, np.where((r >= 1 - peak) & (r < 1.0), falling, 0.0))

    @staticmethod
    def _flame(ratio: float) -> float:
        if ratio <= 0.7:
            return 0.05 + 0.95 * ratio / 0.7
        return 0.05 + 0.95 * (1.0 - ratio) / 0.3

    @staticmethod
    def _tend_flame(ratio: float) -> float:
        if ratio <= 0.7:
            return 0.5 + 0.5 * ratio / 0.7
        return 0.5 + 0.5 * (1.0 - ratio) / 0.3

    _SHAPES = {
        CONICAL: lambda ratio: 0.05 + 0.95 * ratio,
        SPHERICAL: lambda ratio: 0.2 + 0.8 * sin(pi * ratio),
        HEMISPHERICAL: lambda ratio: 0.2 + 0.8 * sin(0.5 * pi * ratio),
        CYLINDRICAL: lambda ratio: 1.0,
        TAPERED_CYLINDRICAL: lambda ratio: 0.5 + 0.5 * ratio,
        FLAME: _flame,
        INVERSE_CONICAL: lambda ratio: 1.0 - 0.8 * ratio,
        TEND_FLAME: _tend_flame,
        INVERSE_TAPERED_CYLINDRICAL: lambda ratio: 0.5 + 0.5 * (1 - ratio),
    }
    _ARRAY_SHAPES = {
        CONICAL: lambda ratio: 0.05 + 0.95 * ratio,
        SPHERICAL: lambda ratio: 0.2 + 0.8 * np.sin(pi * ratio),
        HEMISPHERICAL: lambda ratio: 0.2 + 0.8 * np.sin(0.5 * pi * ratio),
        CYLINDRICAL: lambda ratio: np.ones_like(ratio),
        TAPERED_CYLINDRICAL: lambda ratio: 0.5 + 0.5 * ratio,
        FLAME: _flames,
        INVERSE_CONICAL: lambda ratio: 1.0 - 0.8 * ratio,
        TEND_FLAME: _tend_flames,
        INVERSE_TAPERED_CYLINDRICAL: lambda ratio: 0.5 + 0.5 * (1 - ratio),
    }

    @staticmethod
    def _custom(ratio: float, custom: Sequence[float]) -> float:
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
    def auto_taper(
        length: Sequence[float],
        taper: Sequence[float],
        shape: int,
        shape_s: int,
        levels: int,
        custom_shape: Sequence[float],
    ) -> list[float]:
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
            pm: float = 1
            for x in range(i + 1):
                pm *= taper_s[x]
            taper_p.append(pm)

        taper_r = [sum(taper_p[i:levels]) for i in range(len(taper_p))]

        taper_t = []
        for i in range(len(taper_r)):
            # levels beyond the tree's own have nothing to taper towards
            taper_t.append(taper_p[i] / taper_r[i] if i < levels else 1.0)

        return [t * taper[i] for i, t in enumerate(taper_t)]
