# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing each stem to full length, shortened by the pruning envelope when pruning is on."""

from .geometry import CrownShape
from .growth import StemGrower
from .sprouting import SproutPlanner


class SplineCopier:
    """Exact copies of bezier splines."""

    ATTRIBUTES = (("co", 3), ("handle_left", 3), ("handle_right", 3), ("radius", 1), ("tilt", 1))

    @staticmethod
    def copy_points(source, target):
        """Make the points of target (at least one) an exact copy of the points of source."""
        count = len(source.bezier_points)
        if count > len(target.bezier_points):
            target.bezier_points.add(count - len(target.bezier_points))
        for s, t in zip(source.bezier_points, target.bezier_points, strict=False):
            t.handle_left_type = s.handle_left_type
            t.handle_right_type = s.handle_right_type
        # foreach_set stores the values without recalculating the handles, so the copy is exact
        for attribute, width in SplineCopier.ATTRIBUTES:
            values = [0.0] * (count * width)
            source.bezier_points.foreach_get(attribute, values)
            target.bezier_points.foreach_set(attribute, values)


class PruningSearch:
    """Binary search state of the stem length scale that keeps the stem inside the envelope."""

    def __init__(self):
        self.low = 0.0
        self.high = 1.0
        self.scale = 1.0
        self.old_high = 1.0

    @property
    def converged(self):
        return (self.high - self.low) < 0.005

    def outside(self):
        self.old_high = self.high
        self.high = self.scale
        self.scale = 0.5 * (self.high + self.low)

    def inside(self):
        if self.scale != 1:
            self.low = self.scale
            self.high = self.old_high
            self.scale = 0.5 * (self.high + self.low)
        if (self.high - self.low) == 1:
            self.low = 1


class StemPruner:
    """Grows the stems of one level segment by segment and plans their sprouts.

    With pruning, the stem length is found by a binary search. The search passes grow in a scratch
    curve; the final pass is copied into the tree curve, where the stem keeps its own spline and its
    splits are appended at the end. So spline indices, stem indices and the bone map stay aligned.
    """

    def __init__(self, params, rng, curve, scratch, scale, bone_map):
        self.params = params
        self.rng = rng
        self.curve = curve
        self.scratch = scratch
        self.scale = scale
        self.bone_map = bone_map
        self.grower = StemGrower(params, rng)
        self.sprouts = SproutPlanner(params, rng)
        self.prune_base = min(params.prune_base, params.base_size)

    def grow(self, stem, level, close_tip, base_size):
        """Grow `stem` (and its splits) to full length; return the sprout points for the next level."""
        p = self.params
        rng = self.rng
        # Every pass starts from the same random state, so the search is deterministic
        rng_state = rng.getstate()
        search = PruningSearch()
        restart = False
        original = _StemStart(stem)
        bones = self.bone_map.snapshot()
        tree_spline = stem.spline
        index_offset = len(self.curve.splines) - 1 if p.prune else 0

        while True:
            rng.setstate(rng_state)

            # The last pass also applies the pruning ratio
            last_pass = (search.high - search.low) < 0.01
            if last_pass:
                search.scale = (search.scale - 1) * p.prune_ratio + 1
            stem.segment_length = original.segment_length * search.scale
            if p.prune:
                self._restart_in_scratch(stem, original, tree_spline, restart)
                self.bone_map.restore(bones)

            stems = self._grow_segments(stem, level, close_tip, index_offset)
            if not p.prune:
                return self.sprouts.plan(stems, level, base_size)

            self._check_envelope(stems, level, search)
            if search.converged or last_pass:
                self._copy_to_tree(stems, tree_spline)
                return self.sprouts.plan(stems, level, base_size)
            restart = True

    def _restart_in_scratch(self, stem, original, tree_spline, restart):
        """Start the stem again from its first point, in the scratch curve."""
        self.scratch.splines.clear()
        spline = self.scratch.splines.new("BEZIER")
        point = spline.bezier_points[-1]
        if restart:
            point.co = original.co
            point.handle_right = original.handle_right
            point.handle_left = original.handle_left
            (point.handle_left_type, point.handle_right_type) = ("VECTOR", "VECTOR")
            stem.curvature = original.curvature
            stem.curvature_v = original.curvature_v
            stem.segment = original.segment
            point.radius = stem.radius_start
        else:
            SplineCopier.copy_points(tree_spline, spline)
        stem.spline = spline
        stem.point = spline.bezier_points[-1]

    def _grow_segments(self, stem, level, close_tip, index_offset):
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
                split_count = self._split_count(s, level, k, kp, split_value)
                if (k == int(segments / 2 + 0.5)) and (p.curve_back[level] != 0):
                    s.curvature += 2 * (p.curve_back[level] / segments)
                self.grower.grow(
                    s, level, split_count, stems, self.bone_map, close_tip, kp, base_segment_length, index_offset
                )
        return stems

    def _split_count(self, stem, level, k, kp, split_value):
        p = self.params
        segments = p.curve_res[level]
        value = split_value
        if stem.split_last == 0:
            value = split_value * 1.33
        elif stem.split_last == 1:
            value = split_value * split_value

        if k == 0:
            return 0
        if (level == 0) and (k < ((segments - 1) * p.split_height)) and (k != 1):
            return 0
        if (k == 1) and (level == 0):
            return p.base_splits
        # the trunk always splits at the split height
        if (level == 0) and (k == int((segments - 1) * p.split_height) + 1) and (value > 0):
            return 1
        if (level >= 1) and p.split_by_len:
            length = (stem.segment_length * segments) / self.scale
            level_length = 1
            for factor in p.length[: level + 1]:
                level_length *= factor
            length = length / level_length
            return self.grower.split_count(value * length)
        return self.grower.split_count(value)

    def _check_envelope(self, stems, level, search):
        """Narrow the search: is every stem end inside the pruning envelope?"""
        p = self.params
        scale = self.scale
        inside = True
        for s in stems:
            end = s.spline.bezier_points[-1].co
            distance = (end.xy).length
            ratio = (scale - end.z) / (scale * max(1 - self.prune_base, 1e-6))
            if (level == 0) and (end.z < self.prune_base * scale):
                inside = True
            else:
                inside = (distance / scale) < p.prune_width * CrownShape.ratio(
                    CrownShape.ENVELOPE, ratio, p.prune_width_peak, p.prune_power_high, p.prune_power_low
                )
            if not inside:
                search.outside()
                break
        if inside:
            search.inside()

    def _copy_to_tree(self, stems, tree_spline):
        """Move the final pass from the scratch curve into the tree curve."""
        stem = stems[0]
        SplineCopier.copy_points(stem.spline, tree_spline)
        stem.spline = tree_spline
        for split in stems[1:]:
            spline = self.curve.splines.new("BEZIER")
            SplineCopier.copy_points(split.spline, spline)
            split.spline = spline
            assert split.index == len(self.curve.splines) - 1
        for s in stems:
            s.point = s.spline.bezier_points[-1]


class _StemStart:
    """The state a stem starts every pruning pass from."""

    def __init__(self, stem):
        self.segment_length = stem.segment_length
        self.curvature = stem.curvature
        self.curvature_v = stem.curvature_v
        self.segment = stem.segment
        self.handle_right = stem.point.handle_right.copy()
        self.handle_left = stem.point.handle_left.copy()
        self.co = stem.point.co.copy()
