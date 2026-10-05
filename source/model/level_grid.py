# SPDX-License-Identifier: GPL-3.0-or-later

"""One branch level while it grows: arrays with one row per stem, so every stem advances in one operation.

A row's points are the columns from its origin step to the last segment: a root starts at column 0, a split
that left its parent at step k at column k. Rows are appended in creation order, which is also the order of
the level's splines (all roots first, then the splits as they happen). A stem pruning removed keeps its start
point only.
"""

from collections.abc import Sequence

import numpy as np

from .curve_data import AutoHandles, FlatCurve, HandleType
from .rotations import Rotation
from .stem import BoneLink, BoneName


class StemRows:
    """Per-stem values of a level, one entry per row."""

    FIELDS = (
        "key",  # uint64 lineage key (randomness.py)
        "spline",  # the stem's spline index in the tree
        "parent_stem",  # the spline it grew or split from (-1 for a trunk)
        "parent_point",  # the parent's point it hangs from: the sprout's segment, or the point before a split
        "is_split",
        "is_end",  # a child continuing its parent's tip
        "removed",  # pruning removed the stem: only its start point stays
        "root",  # the row of its family's root stem (a split's family is its parent's)
        "origin",  # the step the row's points start at
        "base_length",  # segment length before the random variation (splits inherit it)
        "segment_length",
        "curvature",
        "curvature_v",
        "children",
        "radius_start",
        "radius_end",
        "offset_length",  # length along the family below the row's first point
        "roll",  # the trunk's own curve plane (further trunks of a clump)
        "curve_sign",  # the curvature variation alternates its sign per segment
        "split_last",  # 1 after a segment that split
        "last_rotation",  # the rotation the next split continues from
        "has_rotation",  # whether last_rotation was drawn yet
    )

    key: np.ndarray
    spline: np.ndarray
    parent_stem: np.ndarray
    parent_point: np.ndarray
    is_split: np.ndarray
    is_end: np.ndarray
    removed: np.ndarray
    root: np.ndarray
    origin: np.ndarray
    base_length: np.ndarray
    segment_length: np.ndarray
    curvature: np.ndarray
    curvature_v: np.ndarray
    children: np.ndarray
    radius_start: np.ndarray
    radius_end: np.ndarray
    offset_length: np.ndarray
    roll: np.ndarray
    curve_sign: np.ndarray
    split_last: np.ndarray
    last_rotation: np.ndarray
    has_rotation: np.ndarray

    def __init__(self, values: dict[str, np.ndarray]) -> None:
        missing = [name for name in self.FIELDS if name not in values]
        if missing:
            raise ValueError(f"stem rows need {', '.join(missing)}")
        for name in self.FIELDS:
            setattr(self, name, values[name])

    def __len__(self) -> int:
        return len(self.key)

    def append(self, other: "StemRows") -> None:
        """Add other's rows after these."""
        for name in self.FIELDS:
            setattr(self, name, np.concatenate([getattr(self, name), getattr(other, name)]))

    def take(self, rows: np.ndarray) -> "StemRows":
        """A copy holding the given rows, in that order."""
        return StemRows({name: getattr(self, name)[rows].copy() for name in self.FIELDS})


class LevelGrid:
    """A level's stems and their points while they grow.

    co (S, K + 1, 3), radius (S, K + 1), h1/h2 (S, K + 1) handle types, dir0 (S, 3) the direction a stem starts
    in; a row's valid columns start at its origin step.
    """

    def __init__(
        self,
        level: int,
        depth: int,
        segments: int,
        handles: int,
        stems: StemRows,
        co0: np.ndarray,
        dir0: np.ndarray,
        radius0: np.ndarray,
        next_spline: int,
    ) -> None:
        count = len(stems)
        self.level = level
        self.depth = depth
        self.segments = segments
        self.handles = handles
        self.stems = stems
        self.co = np.zeros((count, segments + 1, 3), dtype=np.float64)
        self.co[:, 0] = co0
        self.radius = np.zeros((count, segments + 1), dtype=np.float64)
        self.radius[:, 0] = radius0
        self.h1 = np.full((count, segments + 1), handles, dtype=np.int8)
        self.h2 = np.full((count, segments + 1), handles, dtype=np.int8)
        self.h1[:, 0] = self.h2[:, 0] = HandleType.VECTOR
        self.dir0 = np.asarray(dir0, dtype=np.float64)
        self.next_spline = next_spline  # the tree's spline index the next split gets

    @property
    def rows(self) -> int:
        """The stems so far, splits included."""
        return len(self.stems)

    @property
    def root_count(self) -> int:
        """The level's root stems (its families)."""
        return int(np.count_nonzero(~self.stems.is_split))

    def copy(self) -> "LevelGrid":
        """An independent copy (the pruning search grows the same start several times)."""
        return self._with(np.arange(self.rows))

    def subset(self, roots: np.ndarray) -> "LevelGrid":
        """A copy holding the given root rows only, renumbered as roots 0..n-1 (before any growth)."""
        if self.stems.is_split.any():
            raise RuntimeError("a subset is taken before the level grows")
        grid = self._with(roots)
        grid.stems.root = np.arange(len(roots))
        return grid

    def _with(self, rows: np.ndarray) -> "LevelGrid":
        grid = LevelGrid.__new__(LevelGrid)
        grid.level = self.level
        grid.depth = self.depth
        grid.segments = self.segments
        grid.handles = self.handles
        grid.stems = self.stems.take(rows)
        grid.co = self.co[rows].copy()
        grid.radius = self.radius[rows].copy()
        grid.h1 = self.h1[rows].copy()
        grid.h2 = self.h2[rows].copy()
        grid.dir0 = self.dir0[rows].copy()
        grid.next_spline = self.next_spline
        return grid

    def direction(self, step: int) -> np.ndarray:
        """Unit direction of every row's last segment at `step` (its start direction at step 0)."""
        if step == 0:
            return Rotation.unit(self.dir0)
        return Rotation.unit(self.co[:, step] - self.co[:, step - 1])

    def radius_at(self, segment: int) -> np.ndarray:
        """Every row's radius at a segment boundary, tapering from its start radius to its end radius."""
        fraction = segment / self.segments
        return self.stems.radius_start * (1 - fraction) + self.stems.radius_end * fraction

    def append_splits(
        self,
        stems: StemRows,
        step: int,
        parent_rows: np.ndarray,
        co_second: np.ndarray,
        radius_first: np.ndarray,
        radius_second: np.ndarray,
    ) -> None:
        """New rows that split off at `step` from `parent_rows`: their first point is the parent's point there."""
        count = len(stems)
        co = np.zeros((count, self.segments + 1, 3), dtype=np.float64)
        co[:, step] = self.co[parent_rows, step]
        co[:, step + 1] = co_second
        radius = np.zeros((count, self.segments + 1), dtype=np.float64)
        radius[:, step] = radius_first
        radius[:, step + 1] = radius_second
        handles = np.full((count, self.segments + 1), self.handles, dtype=np.int8)
        handles[:, step] = HandleType.VECTOR
        self.co = np.concatenate([self.co, co])
        self.radius = np.concatenate([self.radius, radius])
        self.h1 = np.concatenate([self.h1, handles])
        self.h2 = np.concatenate([self.h2, handles.copy()])
        self.dir0 = np.concatenate([self.dir0, np.zeros((count, 3))])
        self.stems.append(stems)

    def remove(self, removed: np.ndarray) -> None:
        """Pruning removed the families of the given roots (one flag per root row): their splits are dropped and
        the roots keep their start point only; the remaining splits are renumbered without gaps."""
        stems = self.stems
        drop = stems.is_split & removed[stems.root]
        keep = np.flatnonzero(~drop)
        old_spline = stems.spline
        new_spline = old_spline.copy()
        kept_splits = np.flatnonzero(stems.is_split[keep])
        first_split = int(old_spline[stems.is_split].min()) if stems.is_split.any() else self.next_spline
        new_spline[keep[kept_splits]] = first_split + np.arange(len(kept_splits))
        parent_rows = np.searchsorted(old_spline, stems.parent_stem)  # a split's parent is in this level
        parent_stem = np.where(
            stems.is_split, new_spline[np.minimum(parent_rows, len(old_spline) - 1)], stems.parent_stem
        )
        stems.spline = new_spline
        stems.parent_stem = parent_stem
        stems.removed = removed[stems.root]
        trimmed = self._with(keep)
        self.stems, self.co, self.radius, self.h1, self.h2, self.dir0 = (
            trimmed.stems,
            trimmed.co,
            trimmed.radius,
            trimmed.h1,
            trimmed.h2,
            trimmed.dir0,
        )
        self.next_spline = first_split + len(kept_splits)

    def flatten(self) -> FlatCurve:
        """The level's splines as flat float32 arrays in spline order, with their handles recalculated.

        A removed stem is one point with the handles it started with (FREE): its start, and its start direction.
        """
        stems = self.stems
        columns = np.arange(self.segments + 1)[None, :]
        valid = (columns >= stems.origin[:, None]) & (~stems.removed[:, None] | (columns == 0))
        sizes = np.where(stems.removed, 1, self.segments + 1 - stems.origin).astype(np.int64)
        start = np.zeros(len(sizes) + 1, dtype=np.int64)
        np.cumsum(sizes, out=start[1:])
        co = self.co[valid].astype(np.float32)
        left = np.zeros_like(co)
        right = np.zeros_like(co)
        h1 = self.h1[valid]
        h2 = self.h2[valid]
        # a removed stem's point keeps FREE handles: set before the recalculation, which skips FREE sides
        at = start[:-1][stems.removed]
        h1[at] = h2[at] = HandleType.FREE
        right[at] = (self.co[stems.removed, 0] + self.dir0[stems.removed]).astype(np.float32)
        grown = sizes >= 2
        AutoHandles.recalculate_flat(co, left, right, h1, h2, start[:-1][grown], (start[1:] - 1)[grown])
        # radii within the float32 range, as Blender's RNA clamps a curve point's radius (absurd settings can
        # grow them past it; an infinite radius would give the swept bark NaN vertices)
        radius = np.clip(self.radius[valid], 0.0, np.finfo(np.float32).max).astype(np.float32)
        return FlatCurve(co, left, right, h1, h2, radius, start)

    def bone_links(self, bone_step: Sequence[int]) -> list[BoneLink]:
        """Where each row hangs in the armature, in row order (BoneMap entries)."""
        stems = self.stems
        own = bone_step[self.level]
        parent_level = bone_step[self.level - 1] if self.level > 0 else own
        links = []
        for parent, point, is_split, is_end in zip(
            stems.parent_stem.tolist(),
            stems.parent_point.tolist(),
            stems.is_split.tolist(),
            stems.is_end.tolist(),
            strict=True,
        ):
            if parent < 0:
                links.append(BoneLink(""))
            else:
                step = own if is_split else parent_level
                bone = BoneName.rounded(BoneName.of(parent, point), step)
                links.append(BoneLink(bone, is_end, is_split, point if is_split else 0))
        return links
