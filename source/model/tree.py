# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing the whole branch structure, level by level, on the tree curve."""

from collections.abc import Sequence
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class LevelResult:
    """A finished level: its grown grid, and the sprout points for the next level."""

    grid: LevelGrid
    sprouts: SproutArrays


class TreeGrower:
    """Grows the trunk and all branch levels into a curve, every level as one LevelGrid: all stems of the level
    advance in one operation, and with pruning the search for their lengths runs for all of them at once."""

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng
        self.grower = LevelGrower(params, 0.0)
        self.pruning: LevelPruning | None = None
        self.planner = LevelSprouts(params, KeyedRandom.root(params.seed))

    def grow(self, curve: CurveData, scale: float) -> GrownTree:
        """Fill `curve` with the tree's splines.

        `scale` is the tree's overall size (Scale with its random variation), in Blender units.
        """
        p = self.params
        if p.levels < 1:
            raise ValueError("a tree needs at least one level (Levels)")
        root_key = KeyedRandom.root(p.seed)
        starter = LevelStarter(p, self.rng, root_key)
        self.grower = LevelGrower(p, scale)
        self.pruning = LevelPruning(p, scale) if p.prune else None
        levels = GrownLevels()
        base_size = p.base_size if (p.levels > 1 or p.leaves_above_base) else 0.0
        result = self._finish_level(starter.trunks(scale), 0, base_size, p.levels == 1, levels)
        for depth in range(1, p.levels):
            # Per-level parameters only exist for LEVELS levels; deeper levels reuse the last one
            level = TreeParams.level_index(depth)
            last_level = depth == p.levels - 1
            grid = starter.children(result.sprouts, level, depth, base_size, scale, levels.ends[-1], result.grid)
            base_size = self._base_size(base_size, last_level)
            result = self._finish_level(grid, level, base_size, last_level, levels)
        curve.load(FlatCurve.concatenate(levels.chunks))
        return GrownTree(result.sprouts, levels.ends, BoneMap(levels.links))

    def _base_size(self, parent_base: float, last_level: bool) -> float:
        """The bare base of a level's stems: its parent level's times Trunk Height Scale. The last level's children
        are leaves, which grow along the whole stem unless Leaves Above Base."""
        if last_level and not self.params.leaves_above_base:
            return 0.0
        return parent_base * self.params.base_size_s

    def _count_scale(self, base_size: float, last_level: bool) -> float:
        """Count Above Base: a level's branch count is for the part of each stem above its bare base, so the count
        along the whole stem is that much larger (tree-gen divides by 1 - base size). Leaf counts stay as they are;
        a base of 1 or more leaves nothing above it to count."""
        if not self.params.count_above_base or last_level or base_size >= 1.0:
            return 1.0
        return 1.0 / (1.0 - base_size)

    def _finish_level(
        self, grid: LevelGrid, level: int, base_size: float, last_level: bool, levels: GrownLevels
    ) -> LevelResult:
        """Grow a started level (pruned when pruning is on) and plan the next level's sprouts."""
        close_tip = last_level and self.params.close_tip
        if self.pruning is None:
            self.grower.grow(grid, close_tip)
        else:
            grid = self.pruning.grow(grid, self.grower, close_tip)
        flat = grid.flatten()
        levels.add(grid, flat, self.params.bone_step)
        count_scale = self._count_scale(base_size, last_level)
        return LevelResult(grid, self.planner.plan(grid, flat, level, base_size, count_scale))
