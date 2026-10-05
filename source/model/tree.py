# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing the whole branch structure, level by level, on the tree curve."""

from random import Random

from .branching import BranchSpawner, LevelStarter
from .curve_data import CurveData, FlatCurve
from .growth import LevelGrower
from .level_grid import LevelGrid
from .params import TreeParams
from .randomness import KeyedRandom
from .sprouting import LevelSprouts, SproutArrays
from .stem import BoneLink, BoneMap, ChildPoint
from .stem_builder import StemBuilder


class GrownTree:
    """The result of growing: the curve splines are filled in; this holds what goes with them.

    sprouts: sprout points of the last level (where the leaves go).
    level_ends: for each level, the number of splines up to and including that level.
    bone_map: for each spline, where it hangs in the armature.
    """

    def __init__(self, sprouts: SproutArrays, level_ends: list[int], bone_map: BoneMap) -> None:
        self.sprouts = sprouts
        self.level_ends = level_ends
        self.bone_map = bone_map

    def level_of(self, spline_index: int) -> int:
        """Parameter level (at most 3) of a spline."""
        for level, end in enumerate(self.level_ends):
            if spline_index < end:
                return min(level, 3)
        raise IndexError(f"spline {spline_index} is beyond the {self.level_ends[-1]} grown splines")


class GrownLevels:
    """What the grown levels leave behind for the tree: their flat splines, bone links and level ends."""

    def __init__(self) -> None:
        self.chunks: list[FlatCurve] = []
        self.links: list[BoneLink] = []
        self.ends: list[int] = []

    def add(self, grid: LevelGrid, flat: FlatCurve, bone_step: list[int]) -> None:
        """Take a grown level's splines."""
        self.chunks.append(flat)
        self.links += grid.bone_links(bone_step)
        self.ends.append((self.ends[-1] if self.ends else 0) + grid.rows)


class TreeGrower:
    """Grows the trunk and all branch levels into a curve.

    Without pruning every level grows as arrays (LevelGrid: all stems of the level advance in one operation).
    With pruning each stem is still grown on its own, with the binary search of its length (StemBuilder).
    """

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def grow(self, curve: CurveData, scratch: CurveData | None, scale: float) -> GrownTree:
        """Fill `curve` with the tree's splines; `scratch` is a curve for the pruning search (None without pruning).

        `scale` is the tree's overall size (Scale with its random variation), in Blender units.
        """
        if self.params.prune:
            return self._grow_stems(curve, scratch, scale)
        return self._grow_levels(curve, scale)

    def _grow_levels(self, curve: CurveData, scale: float) -> GrownTree:
        """Every level as one LevelGrid; the curve is loaded from the levels' flat arrays."""
        p = self.params
        if p.levels < 1:
            raise ValueError("a tree needs at least one level")
        root_key = KeyedRandom.root(p.seed)
        starter = LevelStarter(p, self.rng, root_key)
        grower = LevelGrower(p, scale)
        planner = LevelSprouts(p, root_key)
        levels = GrownLevels()
        base_size = p.base_size if p.levels > 1 else 0.0
        grid = starter.trunks(scale)
        sprouts = self._finish_level(grid, 0, base_size, p.levels == 1, grower, planner, levels)
        for depth in range(1, p.levels):
            # Per-level parameters only exist for 4 levels; deeper levels reuse the last one
            level = min(3, depth)
            last_level = depth == p.levels - 1
            grid = starter.children(sprouts, level, depth, base_size, scale, levels.ends[-1], grid)
            base_size = 0.0 if last_level else base_size * p.base_size_s
            sprouts = self._finish_level(grid, level, base_size, last_level, grower, planner, levels)
        curve.load(FlatCurve.concatenate(levels.chunks))
        return GrownTree(sprouts, levels.ends, BoneMap.from_links(levels.links))

    def _finish_level(
        self,
        grid: LevelGrid,
        level: int,
        base_size: float,
        last_level: bool,
        grower: LevelGrower,
        planner: LevelSprouts,
        levels: GrownLevels,
    ) -> SproutArrays:
        """Grow a started level and plan the next level's sprouts."""
        p = self.params
        grower.grow(grid, last_level and p.close_tip)
        flat = grid.flatten()
        levels.add(grid, flat, p.bone_step)
        return planner.plan(grid, flat, level, base_size)

    def _grow_stems(self, curve: CurveData, scratch: CurveData | None, scale: float) -> GrownTree:
        """Stem by stem, with the pruning search."""
        p = self.params
        bone_map = BoneMap()
        spawner = BranchSpawner(p, self.rng, curve)
        builder = StemBuilder(p, self.rng, curve, scratch, scale, bone_map)
        base_size = p.base_size
        sprouts: list[ChildPoint] = []
        level_ends: list[int] = []

        for depth in range(p.levels):
            # Per-level parameters only exist for 4 levels; deeper levels reuse the last one
            level = min(3, depth)
            last_level = depth == p.levels - 1
            close_tip = last_level and p.close_tip

            if level == 0:
                stems = spawner.start_trunks(scale, bone_map)
            else:
                stems = spawner.start_children(sprouts, level, depth, base_size, scale, bone_map)

            if level > 0:
                base_size *= p.base_size_s
            if last_level:
                base_size = 0

            sprouts = []
            for stem in stems:
                sprouts.extend(builder.grow(stem, level, close_tip, base_size))
            level_ends.append(bone_map.next_index())

        if len(bone_map) != len(curve.splines):
            raise RuntimeError(f"{len(bone_map)} bone links for {len(curve.splines)} splines")
        return GrownTree(SproutArrays.from_child_points(sprouts), level_ends, bone_map)
