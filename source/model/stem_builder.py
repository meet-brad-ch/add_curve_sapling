# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing each stem of a level to full length, shortened by the pruning envelope when pruning is on."""

from random import Random

from .curve_data import CurveData, CurveSpline
from .geometry import Bezier
from .growth import StemGrower
from .params import TreeParams
from .sprouting import SproutPlanner
from .stem import BoneMap, ChildPoint, Stem


class PruningSearch:
    """Binary search state of the stem length scale that keeps the stem inside the envelope."""

    # The search stops when the scale interval is narrower than this
    TOLERANCE = 0.005
    # The pass that starts with an interval narrower than this is the last one
    LAST_PASS = 0.01
    # With the full Prune Ratio, a stem that would keep less than this share of its length is removed (as
    # tree-gen does); a stub that short is invisible but still carries its leaves
    REMOVE_BELOW = 0.15

    def __init__(self) -> None:
        self.low = 0.0
        self.high = 1.0
        self.scale = 1.0
        self.old_high = 1.0

    @property
    def converged(self) -> bool:
        """Whether the scale interval is narrower than TOLERANCE, so the search stops."""
        return (self.high - self.low) < self.TOLERANCE

    @property
    def last_pass(self) -> bool:
        """The pass after which the search stops; it also applies the pruning ratio."""
        return (self.high - self.low) < self.LAST_PASS

    def removes_stem(self, ratio: float) -> bool:
        """Whether the stem is removed: the full Prune Ratio and less than REMOVE_BELOW of its length left."""
        return ratio >= 1 and self.scale < self.REMOVE_BELOW

    def apply_ratio(self, ratio: float) -> None:
        """Prune Ratio: how much of the found shortening is applied (1 = all of it)."""
        self.scale = (self.scale - 1) * ratio + 1

    def outside(self) -> None:
        """A stem end left the envelope: the scale becomes the upper bound; try halfway down to the lower bound."""
        self.old_high = self.high
        self.high = self.scale
        self.scale = 0.5 * (self.high + self.low)

    def inside(self) -> None:
        """Every stem end stayed inside: search between this scale and the previous upper bound; full length ends it."""
        if self.scale != 1:
            self.low = self.scale
            self.high = self.old_high
            self.scale = 0.5 * (self.high + self.low)
        if (self.high - self.low) == 1:
            self.low = 1


class StemBuilder:
    """Grows the stems of one level segment by segment and plans their sprouts.

    With pruning, the stem length is found by a binary search. The search passes grow in a scratch
    curve; the final pass is copied into the tree curve, where the stem keeps its own spline and its
    splits are appended at the end. So spline indices, stem indices and the bone map stay aligned.
    """

    def __init__(
        self,
        params: TreeParams,
        rng: Random,
        curve: CurveData,
        scratch: CurveData | None,
        scale: float,
        bone_map: BoneMap,
    ) -> None:
        self.params = params
        self.rng = rng
        self.curve = curve
        self.scratch = scratch
        self.scale = scale
        self.bone_map = bone_map
        self.grower = StemGrower(params, rng, scale)
        self.planner = SproutPlanner(params, rng)

    def grow(self, stem: Stem, level: int, close_tip: bool, base_size: float) -> list[ChildPoint]:
        """Grow `stem` (and its splits) to full length; return the sprout points for the next level."""
        if not self.params.prune:
            return self.planner.plan(self._grow_segments(stem, level, close_tip), level, base_size)
        return self._grow_pruned(stem, level, close_tip, base_size)

    def _grow_pruned(self, stem: Stem, level: int, close_tip: bool, base_size: float) -> list[ChildPoint]:
        """Binary search of the stem length: every pass restarts from the same state in the scratch curve."""
        p = self.params
        rng = self.rng
        # Every pass starts from the same random state, so the search is deterministic
        rng_state = rng.getstate()
        search = PruningSearch()
        restart = False
        original = _StemStart(stem)
        bones = self.bone_map.snapshot()
        tree_spline = stem.spline

        while True:
            rng.setstate(rng_state)

            last_pass = search.last_pass
            if last_pass:
                search.apply_ratio(p.prune_ratio)
            stem.segment_length = original.segment_length * search.scale
            self._restart_in_scratch(stem, original, tree_spline, restart)
            self.bone_map.restore(bones)

            stems = self._grow_segments(stem, level, close_tip)
            self._check_envelope(stems, level, search)
            if search.converged or last_pass:
                if level > 0 and search.removes_stem(p.prune_ratio):
                    return self._remove(stem, tree_spline, bones)
                self._copy_to_tree(stems, tree_spline)
                return self.planner.plan(stems, level, base_size)
            restart = True

    def _restart_in_scratch(self, stem: Stem, original: "_StemStart", tree_spline: CurveSpline, restart: bool) -> None:
        """Start the stem again from its first point, in the scratch curve."""
        scratch = self.scratch
        if scratch is None:
            raise RuntimeError("Pruning needs a scratch curve")
        scratch.splines.clear()
        spline = scratch.splines.new(Bezier.SPLINE)
        point = spline.bezier_points[-1]
        if restart:
            point.co = original.co
            point.handle_right = original.handle_right
            point.handle_left = original.handle_left
            (point.handle_left_type, point.handle_right_type) = (Bezier.VECTOR, Bezier.VECTOR)
            stem.curvature = original.curvature
            stem.curvature_v = original.curvature_v
            stem.segment = original.segment
            point.radius = stem.radius_start
        else:
            spline.copy_from(tree_spline)
        stem.spline = spline
        stem.point = spline.bezier_points[-1]

    def _grow_segments(self, stem: Stem, level: int, close_tip: bool) -> list[Stem]:
        """Grow the stem segment by segment; return it followed by the stems split off it."""
        p = self.params
        stems = [stem]
        base_segment_length = stems[0].segment_length
        stems[0].segment_length = base_segment_length * self.rng.uniform(1 - p.length_v[level], 1 + p.length_v[level])

        segments = p.curve_res[level]
        for k in range(segments):
            kp = (k / (segments - 1)) if segments > 1 else 1.0

            split_value = p.seg_splits[level]
            if level == 0:
                split_value = ((2 * p.split_bias) * (kp - 0.5) + 1) * split_value
                split_value = max(split_value, 0.0)

            for s in stems[:]:
                split_count = self.grower.split_count(s, level, k, split_value)
                if (k == int(segments / 2 + 0.5)) and (p.curve_back[level] != 0):
                    s.curvature += 2 * (p.curve_back[level] / segments)
                self.grower.grow(s, level, split_count, stems, self.bone_map, close_tip, kp, base_segment_length)
        return stems

    def _check_envelope(self, stems: list[Stem], level: int, search: PruningSearch) -> None:
        """Narrow the search: is every stem end inside the pruning envelope?"""
        p = self.params
        scale = self.scale
        inside = True
        for s in stems:
            end = s.spline.bezier_points[-1].co
            distance = (end.xy).length
            ratio = (scale - end.z) / (scale * max(1 - p.prune_base_clamped, 1e-6))
            if (level == 0) and (end.z < p.prune_base_clamped * scale):
                inside = True
            else:
                inside = (distance / scale) < p.prune_width * p.envelope(ratio)
            if not inside:
                search.outside()
                break
        if inside:
            search.inside()

    def _remove(self, stem: Stem, tree_spline: CurveSpline, bones: int) -> list[ChildPoint]:
        """A stem pruning removes: its tree spline keeps only its start point (so spline indices and the bone map
        stay aligned), its splits are dropped, and it has no sprouts: no children, no leaves."""
        self.bone_map.restore(bones)
        stem.spline = tree_spline
        stem.point = tree_spline.bezier_points[-1]
        return []

    def _copy_to_tree(self, stems: list[Stem], tree_spline: CurveSpline) -> None:
        """Move the final pass from the scratch curve into the tree curve."""
        stem = stems[0]
        tree_spline.copy_from(stem.spline)
        stem.spline = tree_spline
        for split in stems[1:]:
            spline = self.curve.splines.new(Bezier.SPLINE)
            spline.copy_from(split.spline)
            split.spline = spline
        for s in stems:
            s.point = s.spline.bezier_points[-1]


class _StemStart:
    """The state a stem starts every pruning pass from."""

    def __init__(self, stem: Stem) -> None:
        self.segment_length = stem.segment_length
        self.curvature = stem.curvature
        self.curvature_v = stem.curvature_v
        self.segment = stem.segment
        self.handle_right = stem.point.handle_right.copy()
        self.handle_left = stem.point.handle_left.copy()
        self.co = stem.point.co.copy()
