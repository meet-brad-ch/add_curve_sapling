# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing the whole branch structure, level by level, on the tree curve."""

from .branching import BranchSpawner
from .pruning import StemPruner
from .stem import BoneMap


class GrownTree:
    """The result of growing: the curve splines are filled in; this holds what goes with them.

    sprouts: sprout points of the last level (where the leaves go).
    level_ends: for each level, the number of splines up to and including that level.
    bone_map: for each spline, where it hangs in the armature.
    """

    def __init__(self, sprouts, level_ends, bone_map):
        self.sprouts = sprouts
        self.level_ends = level_ends
        self.bone_map = bone_map

    def level_of(self, spline_index):
        """Parameter level (at most 3) of a spline."""
        for level, end in enumerate(self.level_ends):
            if spline_index < end:
                return min(level, 3)
        return 0


class TreeGrower:
    """Grows the trunk and all branch levels into a curve."""

    def __init__(self, params, rng):
        self.params = params
        self.rng = rng

    def grow(self, curve, scratch, scale):
        """Fill `curve` with the tree's splines; `scratch` is a curve for the pruning search."""
        p = self.params
        bone_map = BoneMap()
        spawner = BranchSpawner(p, self.rng, curve)
        pruner = StemPruner(p, self.rng, curve, scratch, scale, bone_map)
        base_size = p.base_size
        sprouts = []
        level_ends = []

        for depth in range(p.levels):
            # Per-level parameters only exist for 4 levels; deeper levels reuse the last one
            level = min(3, depth)
            last_level = depth == p.levels - 1
            close_tip = last_level and p.close_tip

            if level == 0:
                stems = [spawner.start_trunk(scale)]
            else:
                stems = spawner.start_children(sprouts, level, depth, base_size, scale, bone_map)

            if level > 0:
                base_size *= p.base_size_s
            if last_level:
                base_size = 0

            sprouts = []
            for stem in stems:
                sprouts.extend(pruner.grow(stem, level, close_tip, base_size))
            level_ends.append(len(curve.splines))

        return GrownTree(sprouts, level_ends, bone_map)
