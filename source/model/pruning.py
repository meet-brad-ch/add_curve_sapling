# SPDX-License-Identifier: GPL-3.0-or-later

"""Pruning: shorten every stem of a level until its family stays inside the pruning envelope.

The length scale of each root stem (with its splits) is found by bisection, all roots of a level at once:
every pass regrows the still unsettled families at their trial scales (the keyed draws make a family's shape
at a scale the same in every pass), checks the stem ends against the envelope, and halves the interval. The
first pass tries the full length; a family that fits keeps it. With the full Prune Ratio, a stem that would
keep less than REMOVE_BELOW of its length is removed: only its start point stays, without splits or sprouts.
"""

import numpy as np

from .growth import LevelGrower
from .level_grid import LevelGrid
from .params import TreeParams


class LevelPruning:
    """The pruning search of one level."""

    # The search stops for a family when its scale interval is narrower than this
    TOLERANCE = 0.01
    # A bisection from [0, 1] reaches TOLERANCE in 7 passes; more means a fault
    MAX_PASSES = 12
    # With the full Prune Ratio, a stem that would keep less than this share of its length is removed (as
    # tree-gen does); a stub that short is invisible but still carries its leaves
    REMOVE_BELOW = 0.15

    def __init__(self, params: TreeParams, tree_scale: float) -> None:
        self.params = params
        self.tree_scale = tree_scale

    @classmethod
    def removes(cls, scale: float, ratio: float) -> bool:
        """Whether a stem shortened to `scale` is removed: the full Prune Ratio and less than REMOVE_BELOW left."""
        return ratio >= 1 and scale < cls.REMOVE_BELOW

    def grow(self, start: LevelGrid, grower: LevelGrower, close_tip: bool) -> LevelGrid:
        """The level grown at the scales the search finds (`start` holds the level's root stems, ungrown)."""
        roots = start.rows
        low = np.zeros(roots)
        high = np.ones(roots)
        grid = start.copy()
        grower.grow(grid, close_tip)
        done = self._inside(grid)  # a family that fits at full length keeps it
        final = np.ones(roots)
        for _ in range(self.MAX_PASSES):
            if done.all():
                break
            active = np.flatnonzero(~done)
            mid = 0.5 * (low + high)
            grid = start.subset(active)
            grower.grow(grid, close_tip, mid[active])
            inside = self._inside(grid)
            low[active] = np.where(inside, mid[active], low[active])
            high[active] = np.where(inside, high[active], mid[active])
            settled = active[(high - low)[active] < self.TOLERANCE]
            final[settled] = (0.5 * (low + high))[settled]
            done[settled] = True
        if not done.all():
            raise RuntimeError(f"the pruning search did not settle in {self.MAX_PASSES} passes")
        # Prune Ratio: how much of the found shortening is applied (1 = all of it)
        final = (final - 1) * self.params.prune_ratio + 1
        grid = start.copy()
        grower.grow(grid, close_tip, final)
        if start.level > 0:
            grid.remove(np.array([self.removes(s, self.params.prune_ratio) for s in final.tolist()]))
        return grid

    def _inside(self, grid: LevelGrid) -> np.ndarray:
        """Per family (root row), whether every stem end stays inside the envelope."""
        p = self.params
        scale = self.tree_scale
        end = grid.co[:, grid.segments]
        distance = np.hypot(end[:, 0], end[:, 1])
        ratio = (scale - end[:, 2]) / (scale * max(1 - p.prune_base_clamped, 1e-6))
        inside = distance / scale < p.prune_width * p.envelopes(ratio)
        if grid.level == 0:
            inside = inside | (end[:, 2] < p.prune_base_clamped * scale)
        outside_per_root = np.bincount(grid.stems.root, weights=~inside, minlength=grid.root_count)
        return outside_per_root == 0
