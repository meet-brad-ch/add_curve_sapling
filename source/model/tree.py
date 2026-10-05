# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing the whole branch structure, level by level, on the tree curve."""

from collections.abc import Sequence
from random import Random

from .branching import LevelStarter
from .curve_data import CurveData, FlatCurve
from .growth import LevelGrower
from .level_grid import LevelGrid
from .params import TreeParams
from .pruning import LevelPruning
from .randomness import KeyedRandom
from .sprouting import LevelSprouts, SproutArrays
from .stem import BoneLink, BoneMap


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

    def add(self, grid: LevelGrid, flat: FlatCurve, bone_step: Sequence[int]) -> None:
        """Take a grown level's splines."""
        self.chunks.append(flat)
        self.links += grid.bone_links(bone_step)
        self.ends.append((self.ends[-1] if self.ends else 0) + grid.rows)


class TreeGrower:
    """Grows the trunk and all branch levels into a curve, every level as one LevelGrid: all stems of the level
    advance in one operation, and with pruning the search for their lengths runs for all of them at once."""

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def grow(self, curve: CurveData, scale: float) -> GrownTree:
        """Fill `curve` with the tree's splines.

        `scale` is the tree's overall size (Scale with its random variation), in Blender units.
        """
        p = self.params
        if p.levels < 1:
            raise ValueError("a tree needs at least one level")
        root_key = KeyedRandom.root(p.seed)
        starter = LevelStarter(p, self.rng, root_key)
        grower = LevelGrower(p, scale)
        pruning = LevelPruning(p, scale) if p.prune else None
        planner = LevelSprouts(p, root_key)
        levels = GrownLevels()
        base_size = p.base_size if p.levels > 1 else 0.0
        grid = starter.trunks(scale)
        grid, sprouts = self._finish_level(grid, 0, base_size, p.levels == 1, (grower, pruning, planner), levels)
        for depth in range(1, p.levels):
            # Per-level parameters only exist for 4 levels; deeper levels reuse the last one
            level = min(3, depth)
            last_level = depth == p.levels - 1
            grid = starter.children(sprouts, level, depth, base_size, scale, levels.ends[-1], grid)
            base_size = 0.0 if last_level else base_size * p.base_size_s
            grid, sprouts = self._finish_level(grid, level, base_size, last_level, (grower, pruning, planner), levels)
        curve.load(FlatCurve.concatenate(levels.chunks))
        return GrownTree(sprouts, levels.ends, BoneMap.from_links(levels.links))

    def _finish_level(
        self,
        grid: LevelGrid,
        level: int,
        base_size: float,
        last_level: bool,
        tools: tuple[LevelGrower, LevelPruning | None, LevelSprouts],
        levels: GrownLevels,
    ) -> tuple[LevelGrid, SproutArrays]:
        """Grow a started level (pruned when pruning is on) and plan the next level's sprouts."""
        grower, pruning, planner = tools
        close_tip = last_level and self.params.close_tip
        if pruning is None:
            grower.grow(grid, close_tip)
        else:
            grid = pruning.grow(grid, grower, close_tip)
        flat = grid.flatten()
        levels.add(grid, flat, self.params.bone_step)
        return grid, planner.plan(grid, flat, level, base_size)
