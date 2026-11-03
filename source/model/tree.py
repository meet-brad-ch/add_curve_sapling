# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing the whole branch structure, level by level, on the tree curve."""

from collections.abc import Sequence
from dataclasses import dataclass
from random import Random

from .branching import LevelPlace, LevelStarter
from .curve_data import CurveData, FlatCurve
from .growth import LevelGrower
from .level_grid import LevelGrid
from .params import TreeParams
from .pruning import LevelPruning
from .randomness import KeyedRandom
from .sprouting import LevelSprouts, SproutArrays
from .stem import BoneLink, BoneMap


@dataclass(frozen=True, slots=True)
class GrownTree:
    """The result of growing: the curve splines are filled in; this holds what goes with them."""

    sprouts: SproutArrays  # the sprout points of the last level (where the leaves go)
    level_ends: list[int]  # for each level, the number of splines up to and including that level
    bone_map: BoneMap  # for each spline, where it hangs in the armature


class GrownLevels:
    """What the grown levels leave behind for the tree: their flat splines, bone links and level ends."""

    def __init__(self) -> None:
        """No levels yet: add() collects each grown level."""
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


@dataclass(frozen=True, slots=True)
class TreeGrowth:
    """What one growth of the tree works with: the level grower at the tree's scale, the pruning (None without
    Prune), and the grown levels collected so far."""

    grower: LevelGrower
    pruning: LevelPruning | None
    levels: GrownLevels


class TreeGrower:
    """Grows the trunk and all branch levels into a curve, every level as one LevelGrid: all stems of the level
    advance in one operation, and with pruning the search for their lengths runs for all of them at once."""

    def __init__(self, params: TreeParams, rng: Random) -> None:
        """A grower with the model's parameters and the tree's random stream; the root key of the keyed draws comes from
        the seed."""
        self.params = params
        self.rng = rng
        self.root_key = KeyedRandom.root(params.seed)
        self.planner = LevelSprouts(params, self.root_key)

    def grow(self, curve: CurveData, scale: float) -> GrownTree:
        """Fill `curve` with the tree's splines.

        `scale` is the tree's overall size (Scale with its random variation), in Blender units.
        """
        p = self.params
        if p.levels < 1:
            raise ValueError("a tree needs at least one level (Levels)")
        starter = LevelStarter(p, self.rng, self.root_key)
        pruning = None
        if p.prune:
            pruning = LevelPruning(p, scale)
        growth = TreeGrowth(grower=LevelGrower(p, scale), pruning=pruning, levels=GrownLevels())
        levels = growth.levels
        base_size = p.base_size if (p.levels > 1 or p.leaves_above_base) else 0.0
        result = self._finish_level(growth, starter.trunks(scale), 0, base_size, p.levels == 1)
        for depth in range(1, p.levels):
            # Per-level parameters only exist for LEVELS levels; deeper levels reuse the last one
            level = TreeParams.level_index(depth)
            last_level = depth == p.levels - 1
            place = LevelPlace(level=level, depth=depth, base_size=base_size, scale=scale)
            grid = starter.children(result.sprouts, place, levels.ends[-1], result.grid)
            base_size = self._base_size(base_size, level, last_level)
            result = self._finish_level(growth, grid, level, base_size, last_level)
        curve.load(FlatCurve.concatenate(levels.chunks))
        return GrownTree(sprouts=result.sprouts, level_ends=levels.ends, bone_map=BoneMap(levels.links))

    def _base_size(self, parent_base: float, level: int, last_level: bool) -> float:
        """The bare base of a level's stems: Branch Base when set; else its parent level's times Trunk Height Scale.
        The last level's children are leaves, which grow along the whole stem unless Leaves Above Base or Branch
        Base."""
        if self.params.branch_base[level] > 0:
            return self.params.branch_base[level]
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
        self, growth: TreeGrowth, grid: LevelGrid, level: int, base_size: float, last_level: bool
    ) -> LevelResult:
        """Grow a started level (pruned when pruning is on) and plan the next level's sprouts."""
        close_tip = last_level and self.params.close_tip
        if growth.pruning is None:
            growth.grower.grow(grid, close_tip)
        else:
            grid = growth.pruning.grow(grid, growth.grower, close_tip)
        flat = grid.flatten()
        growth.levels.add(grid, flat, self.params.bone_step)
        count_scale = self._count_scale(base_size, last_level)
        return LevelResult(grid, self.planner.plan(grid, flat, level, base_size, count_scale))
