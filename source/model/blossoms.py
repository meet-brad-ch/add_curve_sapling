# SPDX-License-Identifier: GPL-3.0-or-later

"""Blossoms: some leaf positions grow a flower instead of a leaf (as tree-gen's blossom_rate does).

The flowers are this add-on's own procedural geometry. A blossom is a ring of cupped petals around a centre
vertex, in leaf space: the flower faces along +z, the direction the leaf would grow in, and its diameter is 1
before Blossom Scale. Each petal is five quads over three rings of points: its base, its widest, its rounded end.
"""

from dataclasses import dataclass
from math import pi

import numpy as np

from .geometry import LeafTemplate
from .randomness import Draw, KeyedRandom, Kind


@dataclass(frozen=True, slots=True)
class BlossomForm:
    """One flower's shape: how many petals, how wide each is (a fraction of its share of the circle), where it is
    widest (a fraction of the radius), and its cup (the height of a petal tip above the centre, in diameters;
    negative bends the petals back)."""

    petals: int
    width: float
    widest: float
    cup: float


class BlossomShape:
    """The flower templates (the Blossom Shape setting)."""

    CHERRY = "cherry"
    ORANGE = "orange"
    MAGNOLIA = "magnolia"
    ALL = [CHERRY, ORANGE, MAGNOLIA]
    FORMS = {
        CHERRY: BlossomForm(petals=5, width=0.95, widest=0.65, cup=0.12),
        ORANGE: BlossomForm(petals=5, width=0.5, widest=0.55, cup=-0.1),
        MAGNOLIA: BlossomForm(petals=8, width=0.65, widest=0.6, cup=0.45),
    }
    RADIUS = 0.5  # a template's diameter is 1
    # A petal's three rings of points, as fractions of the radius: its base, its widest, and its rounded end (the
    # end's sides; its middle point is at the full radius); the base and end widths are fractions of the widest
    BASE = 0.25
    BASE_WIDTH = 0.6
    END = 0.9
    END_WIDTH = 0.55
    # A petal's quads (counterclockwise seen from +z): 0 is the centre, then per ring its left, middle and right
    # point (1-3 base, 4-6 widest, 7-9 end)
    PETAL_FACES = [[0, 1, 2, 3], [1, 4, 5, 2], [2, 5, 6, 3], [4, 7, 8, 5], [5, 8, 9, 6]]
    PETAL_POINTS = 9

    @classmethod
    def template(cls, shape: str) -> LeafTemplate:
        """The flower's vertices (1 + 9 per petal) and quads (5 per petal); raises ValueError for an unknown shape."""
        if shape not in cls.FORMS:
            raise ValueError(f"unknown blossom shape {shape}")
        form = cls.FORMS[shape]
        share = 2 * pi / form.petals
        half = share * form.width / 2
        rings = [cls.BASE, form.widest, cls.END]
        widths = [half * cls.BASE_WIDTH, half, half * cls.END_WIDTH]
        points = [[0.0, 0.0, 0.0]]
        faces = []
        for petal in range(form.petals):
            middle = petal * share
            first = len(points) - 1
            for ring, width in zip(rings, widths, strict=True):
                points.append(cls._point(ring, middle - width, form.cup))
                points.append(cls._point(1.0 if ring == cls.END else ring, middle, form.cup))
                points.append(cls._point(ring, middle + width, form.cup))
            faces += [[corner + first if corner else 0 for corner in quad] for quad in cls.PETAL_FACES]
        return LeafTemplate(np.array(points, dtype=np.float64), np.array(faces, dtype=np.int32))

    @classmethod
    def _point(cls, fraction: float, angle: float, cup: float) -> list[float]:
        """A point at `fraction` of the radius in direction `angle`, raised by the cup (growing with the square of
        the distance from the centre)."""
        radius = cls.RADIUS * fraction
        return [radius * np.cos(angle), radius * np.sin(angle), cup * fraction * fraction]


class BlossomPick:
    """Which leaf positions grow a blossom: a keyed draw per position, below the rate."""

    @staticmethod
    def chosen(rate: float, parent_key: np.ndarray, position: np.ndarray, slot: np.ndarray) -> np.ndarray:
        """One flag per leaf (its sprout's parent key and family position, and its place in a fan); nothing is drawn
        at rate 0, and every position is chosen at rate 1. The draws are keyed, so a higher rate keeps every blossom
        of a lower one."""
        if rate <= 0.0:
            return np.zeros(len(parent_key), dtype=bool)
        keys = KeyedRandom.derive(parent_key, Kind.BLOSSOM, position, slot)
        return KeyedRandom.uniform(keys, 0, Draw.BLOSSOM) < rate
