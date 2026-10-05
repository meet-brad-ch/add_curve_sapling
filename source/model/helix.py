# SPDX-License-Identifier: GPL-3.0-or-later

"""Helix stems: each segment of a stem is half a turn of a helix around the stem's start direction.

The shape follows tree-gen (parametric/gen.py, calc_helix_points and the helix branch of make_stem): the pitch is
twice the segment length, the radius comes from the helix angle (Curvature Variation), and each half turn is one
Bezier segment with FREE handles 4/3 of the radius long. In the stem's frame, point j is (0, r (1 - s), j p / 2)
and its handles are the point -/+ (s 4 r / 3, 0, p / 4), with s = (-1) ** j.
"""

import numpy as np

from .geometry import Angles
from .level_grid import FreeHandles, LevelGrid
from .params import TreeParams
from .randomness import Draw, KeyedRandom
from .rotations import Rotation, TrackFrame


class HelixPath:
    """Grows every stem of a helix level at once, in closed form: no splits, no curve, no bend, no attraction."""

    # Pitch and radius vary randomly between these factors (tree-gen's rand_in_range(0.8, 1.2))
    LOW = 0.8
    HIGH = 1.2
    # A Bezier segment whose handles are 4/3 of the radius long draws a half circle
    HANDLE = 4.0 / 3.0
    # tree-gen's radius: 3 pitch / (16 tan(90 degrees - helix angle))
    RADIUS_FACTOR = 3.0 / 16.0

    def __init__(self, params: TreeParams) -> None:
        self.params = params

    def grow(self, grid: LevelGrid, close_tip: bool) -> None:
        """Write every row's points 1..K, radii and FREE handles (Close Tip ends the last point at radius 0)."""
        stems = grid.stems
        keys = stems.key
        segments = grid.segments
        pitch = 2 * stems.segment_length * KeyedRandom.between(keys, 0, Draw.HELIX_PITCH, self.LOW, self.HIGH)
        slope = np.tan(np.pi / 2 - abs(self.params.curve_v[grid.level]))
        radius = (
            self.RADIUS_FACTOR * pitch / slope * KeyedRandom.between(keys, 0, Draw.HELIX_RADIUS, self.LOW, self.HIGH)
        )
        spin = KeyedRandom.between(keys, 0, Draw.HELIX_SPIN, 0.0, Angles.TAU)
        frames = TrackFrame.matrices(grid.direction(0)) @ Rotation.about(spin, "Z")
        j = np.arange(segments + 1)
        side = np.where(j % 2 == 0, 1.0, -1.0)
        point = np.zeros((len(stems), segments + 1, 3))
        point[:, :, 1] = radius[:, None] * (1 - side)[None, :]
        point[:, :, 2] = pitch[:, None] * j[None, :] / 2
        handle = np.zeros_like(point)
        handle[:, :, 0] = self.HANDLE * radius[:, None] * side[None, :]
        handle[:, :, 2] = pitch[:, None] / 4
        co = grid.co[:, 0][:, None, :] + np.einsum("sij,skj->ski", frames, point)
        offset = np.einsum("sij,skj->ski", frames, handle)
        grid.co[:] = co
        fraction = j / segments
        grid.radius[:, 1:] = (
            stems.radius_start[:, None] * (1 - fraction[None, 1:]) + stems.radius_end[:, None] * fraction[None, 1:]
        )
        if close_tip:
            grid.radius[:, -1] = 0.0
        grid.free = FreeHandles(co - offset, co + offset)
