# SPDX-License-Identifier: GPL-3.0-or-later

"""Where child stems and leaves sprout along the grown stems of a level."""

from dataclasses import dataclass
from math import floor

import numpy as np

from .curve_data import FlatCurve
from .level_grid import LevelGrid
from .params import BranchingMode, TreeParams
from .randomness import Draw, KeyedRandom, Kind
from .rotations import BezierBatch, TrackFrame


class SproutArrays:
    """The sprout points of a level, one row each: where child stems or leaves grow next.

    co (M, 3); frame (M, 3, 3) the stem direction's TrackFrame there; radius_parent (M, 2) the parent's start
    radius and its radius at the sprout; offset and stem_offset (M,) the position along the parent (offset as
    the children see it, stem_offset the raw fraction of the family's length); length_parent (M,); parent_spline
    and parent_point (M,) the parent's spline and the segment the sprout is on; parent_key (M,) the parent's
    lineage key; position (M,) the sprout's index among its family's positions (-1 for a tip); family (M,) the
    row of the parent's family root in its level.
    """

    FIELDS = [
        "co",
        "frame",
        "radius_parent",
        "offset",
        "stem_offset",
        "length_parent",
        "parent_spline",
        "parent_point",
        "parent_key",
        "position",
        "family",
    ]

    def __init__(
        self,
        co: np.ndarray,
        frame: np.ndarray,
        radius_parent: np.ndarray,
        offset: np.ndarray,
        stem_offset: np.ndarray,
        length_parent: np.ndarray,
        parent_spline: np.ndarray,
        parent_point: np.ndarray,
        parent_key: np.ndarray,
        position: np.ndarray,
        family: np.ndarray,
    ) -> None:
        self.co = co
        self.frame = frame
        self.radius_parent = radius_parent
        self.offset = offset
        self.stem_offset = stem_offset
        self.length_parent = length_parent
        self.parent_spline = parent_spline
        self.parent_point = parent_point
        self.parent_key = parent_key
        self.position = position
        self.family = family

    @property
    def count(self) -> int:
        """How many sprouts."""
        return len(self.offset)

    @property
    def is_end(self) -> np.ndarray:
        """Sprouts at the very end of their stem: a child there continues the parent's tip."""
        return self.offset == 1.0

    @property
    def is_tip(self) -> np.ndarray:
        """The tip sprout of each stem (after its positions)."""
        return self.position < 0

    def take(self, order: np.ndarray) -> "SproutArrays":
        """The sprouts at `order`, in that order."""
        return SproutArrays(*(getattr(self, name)[order] for name in self.FIELDS))

    @classmethod
    def concatenate(cls, a: "SproutArrays", b: "SproutArrays") -> "SproutArrays":
        """a's sprouts, then b's."""
        return cls(*(np.concatenate([getattr(a, name), getattr(b, name)]) for name in cls.FIELDS))


@dataclass(frozen=True, slots=True)
class PositionCounts:
    """How many sprout positions each root row has, and where its first one is in the positions."""

    counts: np.ndarray
    starts: np.ndarray


class FamilyPositions:
    """Where along each family (a root stem with its splits) the sprouts go: fractions of the family's length.

    root (P,) the family's root row, t (P,) the fraction, index (P,) the position's number in its family; sorted
    by root.
    """

    def __init__(self, root: np.ndarray, t: np.ndarray, index: np.ndarray) -> None:
        self.root = root
        self.t = t
        self.index = index

    def counts(self, rows: int) -> PositionCounts:
        """Positions per root row, and the first position of each root row."""
        counts = np.bincount(self.root, minlength=rows)
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        return PositionCounts(counts, starts)


@dataclass(frozen=True, slots=True)
class PlacedSprouts:
    """Sprouts placed on stems: the row of each sprout's stem, and the sprouts themselves."""

    rows: np.ndarray
    sprouts: SproutArrays


@dataclass(frozen=True, slots=True)
class PositionsOnRows:
    """The family positions that fall on a stem row: the row, the position's fraction of the family, its index,
    and the stem's own span of the family (bottom..top fractions)."""

    rows: np.ndarray
    t: np.ndarray
    index: np.ndarray
    bottom: np.ndarray
    top: np.ndarray


class LevelSprouts:
    """Places the sprout points of a whole grown level for the next level."""

    # Branch Rings: each ring's height varies randomly within this factor range
    RING_JITTER_LOW = 0.995
    RING_JITTER_HIGH = 1.005

    def __init__(self, params: TreeParams, root_key: np.ndarray) -> None:
        self.params = params
        self.root_key = root_key

    def plan(self, grid: LevelGrid, flat: FlatCurve, level: int, base_size: float) -> SproutArrays:
        """Sprout points of every family, in order: along each stem of the family (the root, then its splits),
        then the stem's tip."""
        stems = grid.stems
        sizes = flat.sizes
        positions = self._positions(grid, flat, level, base_size)
        stem_length = stems.segment_length * (sizes - 1)
        family_max = np.zeros(grid.rows)
        np.maximum.at(family_max, stems.root, stems.offset_length + stem_length)
        body = self._along(grid, flat, positions, family_max, base_size)
        tips = self._tips(grid, flat)
        rows = np.concatenate([body.rows, tips.rows])
        sprouts = SproutArrays.concatenate(body.sprouts, tips.sprouts)
        is_tip = sprouts.is_tip
        order = np.lexsort((np.where(is_tip, np.iinfo(np.int64).max, sprouts.position), is_tip, rows, stems.root[rows]))
        if not np.isfinite(sprouts.co[order]).all():
            raise RuntimeError("a sprout point is not finite: the stem it sits on has no length")
        return sprouts.take(order)

    def _positions(self, grid: LevelGrid, flat: FlatCurve, level: int, base_size: float) -> FamilyPositions:
        """Every family's positions (0..1 along the family) that are not on its bare base."""
        stems = grid.stems
        roots = np.flatnonzero(~stems.is_split & ~stems.removed)
        if level == 0:
            return self._trunk_positions(grid, flat, roots, base_size)
        sizes = flat.sizes
        points = np.bincount(stems.root, weights=sizes, minlength=grid.rows)[roots]
        members = np.bincount(stems.root, minlength=grid.rows)[roots]
        children = stems.children[roots]
        # every kept stem has two or more points, so a family has at least as many segments as members
        count = np.round(children / (points - members) * grid.segments).astype(np.int64)
        count = np.where(children > 0, count, 1)  # no children: one position at the tip, which never sprouts
        total = int(count.sum())
        root = np.repeat(roots, count)
        index = np.arange(total) - np.repeat(np.cumsum(count) - count, count)
        repeated = np.repeat(count, count)
        t = np.where(np.repeat(children > 0, count), (index + 1) / repeated, 1.0)
        keep = index >= (base_size * (repeated + 1)).astype(np.int64)  # nothing sprouts on the bare base
        return FamilyPositions(root[keep], t[keep], index[keep])

    def _trunk_positions(
        self, grid: LevelGrid, flat: FlatCurve, roots: np.ndarray, base_size: float
    ) -> FamilyPositions:
        """The trunks' positions: even or per segment, rings, and the Branch Distribution (a few trunks: a loop)."""
        p = self.params
        stems = grid.stems
        sizes = flat.sizes
        root_list: list[int] = []
        t_list: list[float] = []
        index_list: list[int] = []
        for root in roots.tolist():
            members = np.flatnonzero(stems.root == root)
            children = float(stems.children[root])
            if p.rotate_mode != BranchingMode.ORIGINAL:
                positions = [(a + 1) / children for a in range(int(children))]
            else:
                per_segment = children / (int(sizes[members].sum()) - len(members))
                count = round(per_segment * grid.segments, 0)
                positions = [(a + 1) / count for a in range(int(count))]
            if not children:
                positions = [1.0]
            positions = positions[int(base_size * (len(positions) + 1)) :]
            positions = self._rings(positions, root, base_size)
            positions = self._distribute(positions, base_size)
            root_list += [root] * len(positions)
            t_list += positions
            index_list += list(range(len(positions)))
        return FamilyPositions(
            np.array(root_list, dtype=np.int64), np.array(t_list), np.array(index_list, dtype=np.int64)
        )

    def _distribute(self, positions: list[float], base_size: float) -> list[float]:
        """Branch Distribution: crowd trunk branches towards the base (< 1) or the top (> 1)."""
        dist = self.params.branch_dist
        positions = [((t - base_size) / (1 - base_size)) for t in positions]
        if dist < 1.0:
            positions = [t ** (1 / dist) for t in positions]
        else:
            positions = [1 - (1 - t) ** dist for t in positions]
        return [t * (1 - base_size) + base_size for t in positions]

    def _rings(self, positions: list[float], root: int, base_size: float) -> list[float]:
        """Branch Rings: the positions snap to rings, each ring at a slightly random height."""
        rings = self.params.rings
        if rings <= 0:
            return positions
        keys = KeyedRandom.derive(self.root_key, Kind.RING, root, np.arange(max(len(positions) - 1, 0)))
        jitter = KeyedRandom.between(keys, 0, Draw.RING, self.RING_JITTER_LOW, self.RING_JITTER_HIGH)
        snapped = [(floor(t * rings) / rings) * j for t, j in zip(positions[:-1], jitter.tolist(), strict=True)]
        snapped.append(1.0)
        return [t for t in snapped if t > base_size]

    def _along(
        self, grid: LevelGrid, flat: FlatCurve, positions: FamilyPositions, family_max: np.ndarray, base_size: float
    ) -> PlacedSprouts:
        """The sprouts of every position that falls on a stem of its family."""
        stems = grid.stems
        sizes = flat.sizes
        on = self._positions_on_rows(grid, flat, positions, family_max)
        rows = on.rows
        scaled = (on.t - on.bottom) / (on.top - on.bottom)
        offset = ((on.t - base_size) / (on.top - base_size)) * (1 - base_size) + base_size
        segments = sizes[rows] - 1
        length = segments * scaled
        segment = np.minimum(np.floor(length).astype(np.int64), segments - 1)  # scaled can round to exactly 1.0
        local_t = length - segment
        first = flat.start[rows] + segment
        co = flat.co.astype(np.float64)
        p1 = co[first]
        h1 = flat.right.astype(np.float64)[first]
        h2 = flat.left.astype(np.float64)[first + 1]
        p2 = co[first + 1]
        radius = (1 - local_t) * flat.radius[first] + local_t * flat.radius[first + 1]
        sprouts = SproutArrays(
            BezierBatch.points(p1, h1, h2, p2, local_t),
            TrackFrame.matrices(BezierBatch.tangents(p1, h1, h2, p2, local_t)),
            np.stack([stems.radius_start[rows], radius], axis=1),
            offset,
            on.t,
            grid.segments * stems.segment_length[rows],
            stems.spline[rows],
            segment,
            stems.key[rows],
            on.index,
            stems.root[rows],
        )
        return PlacedSprouts(rows, sprouts)

    @staticmethod
    def _positions_on_rows(
        grid: LevelGrid, flat: FlatCurve, positions: FamilyPositions, family_max: np.ndarray
    ) -> PositionsOnRows:
        """Every family position paired with the stem row of its family it falls on (not past the tip)."""
        stems = grid.stems
        sizes = flat.sizes
        counts = positions.counts(grid.rows)
        per_row = np.where(stems.removed, 0, counts.counts[stems.root])
        rows = np.repeat(np.arange(grid.rows), per_row)
        slot = np.arange(len(rows)) - np.repeat(np.cumsum(per_row) - per_row, per_row)
        at = counts.starts[stems.root[rows]] + slot
        t = positions.t[at]
        index = positions.index[at]
        scale = family_max[stems.root[rows]]
        bottom = stems.offset_length[rows] / scale
        top = bottom + stems.segment_length[rows] * (sizes[rows] - 1) / scale
        keep = (t >= bottom) & (t <= top) & (t < 1.0)
        return PositionsOnRows(rows[keep], t[keep], index[keep], bottom[keep], top[keep])

    @staticmethod
    def _tips(grid: LevelGrid, flat: FlatCurve) -> PlacedSprouts:
        """The sprout at the tip of every stem."""
        stems = grid.stems
        rows = np.flatnonzero(~stems.removed)  # a removed stem has no tip to sprout from
        last = (flat.start[1:] - 1)[rows]
        co = flat.co[last].astype(np.float64)
        ones = np.ones(len(rows))
        sprouts = SproutArrays(
            co,
            TrackFrame.matrices(flat.right[last].astype(np.float64) - co),
            np.stack([stems.radius_start[rows], flat.radius[last].astype(np.float64)], axis=1),
            ones,
            ones,
            grid.segments * stems.segment_length[rows],
            stems.spline[rows],
            flat.sizes[rows] - 2,
            stems.key[rows],
            np.full(len(rows), -1, dtype=np.int64),
            stems.root[rows],
        )
        return PlacedSprouts(rows, sprouts)
