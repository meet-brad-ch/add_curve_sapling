# SPDX-License-Identifier: GPL-3.0-or-later

"""Where child stems and leaves sprout along a grown stem."""

from math import floor

from mathutils import Vector

from .branching import BranchingMode
from .geometry import BezierSegment
from .stem import BoneName, ChildPoint


class SproutPlanner:
    """Places the sprout points of one grown stem (with its splits) for the next level."""

    def __init__(self, params, rng):
        self.params = params
        self.rng = rng

    def plan(self, stems, level, base_size):
        """Sprout points of a stem and its splits, in order: along each stem, then its tip."""
        p = self.params
        stem = stems[0]
        if (level == 0) and (p.rotate_mode != BranchingMode.ORIGINAL):
            positions = self._even_positions(stem.children)
        else:
            positions = self._positions_per_segment(stems, stem.children)
        # A negative leaf count only sprouts at the stem tip
        if not stem.children:
            positions = [1.0]
        # Nothing sprouts on the bare base of the stem
        positions = positions[int(base_size * (len(positions) + 1)) :]

        if (level == 0) and (p.rings > 0):
            positions = [(floor(t * p.rings) / p.rings) * self.rng.uniform(0.995, 1.005) for t in positions[:-1]]
            positions.append(1)
            positions = [t for t in positions if t > base_size]

        if level == 0:
            positions = self._distribute(positions, base_size)

        max_offset = max([s.offset_length + (len(s.spline.bezier_points) - 1) * s.segment_length for s in stems])
        points = []
        for s in stems:
            points.extend(self._sample(s, positions, s.segments * s.segment_length, max_offset, base_size))
        return points

    @staticmethod
    def _positions_per_segment(stems, children):
        points = sum([len(s.spline.bezier_points) for s in stems])
        segments = points - len(stems)
        per_segment = children / segments
        count = round(per_segment * stems[0].segments, 0)
        return [(a + 1) / count for a in range(int(count))]

    @staticmethod
    def _even_positions(children):
        return [(a + 1) / children for a in range(int(children))]

    def _distribute(self, positions, base_size):
        """Branch Distribution: crowd trunk branches towards the base (< 1) or the top (> 1)."""
        dist = self.params.branch_dist
        positions = [((t - base_size) / (1 - base_size)) for t in positions]
        if dist < 1.0:
            positions = [t ** (1 / dist) for t in positions]
        else:
            positions = [1 - (1 - t) ** dist for t in positions]
        return [t * (1 - base_size) + base_size for t in positions]

    @staticmethod
    def _sample(stem, positions, length_parent, max_offset, base_size):
        """A ChildPoint at each position that falls on this stem, plus one at its tip."""
        points = stem.spline.bezier_points
        segments = len(points) - 1
        stem_length = stem.segment_length * segments

        bottom = stem.offset_length / max_offset
        top = bottom + (stem_length / max_offset)

        sprouts = []
        for t in positions:
            if (t >= bottom) and (t <= top) and (t < 1.0):
                scaled = (t - bottom) / (top - bottom)
                offset = ((t - base_size) / (top - base_size)) * (1 - base_size) + base_size

                length = segments * scaled
                # scaled can round to exactly 1.0: stay on the last segment
                index = min(int(length), segments - 1)
                local_t = length - index

                segment = BezierSegment.between(points[index], points[index + 1])
                quat = segment.tangent(local_t).to_track_quat("Z", "Y")
                radius = (1 - local_t) * points[index].radius + local_t * points[index + 1].radius
                sprouts.append(
                    ChildPoint(
                        segment.point(local_t),
                        quat,
                        (stem.radius_start, radius),
                        t,
                        offset,
                        length_parent,
                        BoneName.of(stem.index, index),
                    )
                )

        # The tip
        tip = points[-1]
        sprouts.append(
            ChildPoint(
                Vector(tip.co),
                (tip.handle_right - tip.co).to_track_quat("Z", "Y"),
                (stem.radius_start, tip.radius),
                1,
                1,
                length_parent,
                BoneName.of(stem.index, segments - 1),
            )
        )
        return sprouts
