# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing every stem of a level by one segment per step, including splitting them into several stems."""

from math import pi

import numpy as np

from .geometry import Angles
from .level_grid import LevelGrid, StemRows
from .params import TreeParams
from .randomness import Draw, KeyedRandom, Kind
from .rotations import AttractUp, EulerXYZ, Rotation, TrackFrame, TrunkFrame


class LevelGrower:
    """Grows every stem of a level at once, one segment per step, splits included: StemGrower as array maths.

    Each step does what StemGrower.grow does for one stem, for all rows of the LevelGrid: the split decision,
    the curve angles, the growth frame (TrunkFrame on the trunk level, TrackFrame above), Attract Out and
    Attract Up, then the new point. Stems that split get new rows, which grow from the next step on.
    """

    # After a segment without a split, a split is this much more likely
    SPLIT_BOOST = 1.33
    # Split angle of a branch pointing sideways: FLATTEN_MIN of the angle, up to 1 when it points up
    FLATTEN_SCALE = 0.67
    FLATTEN_MIN = 0.33

    def __init__(self, params: TreeParams, scale: float) -> None:
        self.params = params
        self.scale = scale

    def grow(self, grid: LevelGrid, close_tip: bool, scale: np.ndarray | None = None) -> None:
        """Grow the grid's stems to full length (Close Tip ends the last segment at radius 0).

        `scale` shortens each family's stems (the pruning search's trial scales, one per root row).
        """
        stems = grid.stems
        if scale is not None:
            stems.base_length = stems.base_length * scale[stems.root]
        variation = self.params.length_v[grid.level]
        # the root stems' segment lengths vary randomly; their splits keep the base length
        stems.segment_length = stems.base_length * KeyedRandom.between(
            stems.key, 0, Draw.JITTER, 1 - variation, 1 + variation
        )
        for step in range(grid.segments):
            self._step(grid, step, close_tip)

    def _step(self, grid: LevelGrid, k: int, close_tip: bool) -> None:
        """Grow every row by one segment; append the rows that split off here."""
        p = self.params
        level = grid.level
        segments = grid.segments
        stems = grid.stems
        kp = k / (segments - 1) if segments > 1 else 1.0
        if k == int(segments / 2 + 0.5) and p.curve_back[level] != 0:
            stems.curvature = stems.curvature + 2 * (p.curve_back[level] / segments)

        splits = self._split_counts(grid, k, kp)
        has_split = splits > 0
        angle, variation = self._curve_angles(grid, k, kp)
        frames, taper = self._frames(grid.direction(k), level)
        frames = self._attract_out(frames, grid.co[:, k], kp, level)
        split_angle, spread, branch_rot = self._split_angles(grid, k, frames, has_split)

        bend = Rotation.about(variation, "Y")
        plain = Rotation.about(stems.roll, "Z") @ bend @ Rotation.about(angle, "X")
        side = Rotation.about(branch_rot, "Z") if level == 0 else Rotation.about(-spread, "Y")
        continued = side @ bend @ Rotation.about(-split_angle + angle, "X")
        local = np.where(has_split[:, None, None], continued, plain)
        direction = self._segment(grid, frames @ local, stems.segment_length, taper)

        new = self._split_rows(
            grid, k, splits, frames, (angle, variation, split_angle, spread, branch_rot), taper, close_tip
        )
        grid.co[:, k + 1] = grid.co[:, k] + direction
        grid.radius[:, k + 1] = 0.0 if close_tip and k == segments - 1 else grid.radius_at(k + 1)
        stems.split_last = has_split.astype(np.int8)
        if new is not None:
            grid.append_splits(*new)

    def _segment(self, grid: LevelGrid, rotation: np.ndarray, length: np.ndarray, taper: np.ndarray) -> np.ndarray:
        """The segment vectors: the rotated z axis, bent by Attract Up, of the segment length times the taper."""
        direction = AttractUp.apply(rotation[:, :, 2], self.params.attract_up[grid.level], grid.segments)
        return Rotation.unit(direction) * (length * taper)[:, None]

    def _split_counts(self, grid: LevelGrid, k: int, kp: float) -> np.ndarray:
        """How many stems split off each row at this step (StemGrower.split_count)."""
        p = self.params
        level = grid.level
        segments = grid.segments
        stems = grid.stems
        split_value = p.seg_splits[level]
        if level == 0:
            split_value = max(((2 * p.split_bias) * (kp - 0.5) + 1) * split_value, 0.0)
        value = np.where(stems.split_last == 0, split_value * self.SPLIT_BOOST, split_value * split_value)
        none = np.zeros(len(stems), dtype=np.int64)
        if k == 0 or (level == 0 and k < (segments - 1) * p.split_height and k != 1):
            return none
        if k == 1 and level == 0:
            return none + p.base_splits
        if level == 0 and k == int((segments - 1) * p.split_height) + 1:
            return (value > 0).astype(np.int64)  # the trunk always splits at the split height
        probability = value
        if level >= 1 and p.split_by_len:
            probability = value * (stems.segment_length * segments / self.scale) / p.length_product(level, 1)
        return (KeyedRandom.uniform(stems.key, k, Draw.SPLIT) < probability).astype(np.int64)

    def _curve_angles(self, grid: LevelGrid, k: int, kp: float) -> tuple[np.ndarray, np.ndarray]:
        """(curve angle, curve variation) of every row; the variation's sign alternates per segment."""
        p = self.params
        stems = grid.stems
        curvature = stems.curvature
        if grid.level == 0 and kp <= p.split_height:
            curvature = np.zeros_like(curvature)
        sign = stems.curve_sign
        angle = curvature + KeyedRandom.between(stems.key, k, Draw.CURVE_ANGLE, 0.0, stems.curvature_v) * kp * sign
        variation = KeyedRandom.between(stems.key, k, Draw.CURVE_VARIATION, 0.0, stems.curvature_v) * kp * sign
        stems.curve_sign = -sign
        return angle, variation

    def _frames(self, directions: np.ndarray, level: int) -> tuple[np.ndarray, np.ndarray]:
        """(growth frames, taper factors): the trunk's frame keeps no roll and tapers its sideways splits."""
        if level > 0:
            return TrackFrame.matrices(directions), np.ones(len(directions))
        declination = np.arccos(np.clip(directions[:, 2], -1.0, 1.0)) / pi
        taper = np.maximum(0.1, 1 - declination * declination * self.params.taper_crown * 30)
        return TrunkFrame.matrices(directions), taper

    def _attract_out(self, frames: np.ndarray, co: np.ndarray, kp: float, level: int) -> np.ndarray:
        """Turn the frames outward from the tree's axis (Attract Out)."""
        attract_out = self.params.attract_out[level]
        if level == 0 or kp <= 0 or attract_out <= 0:
            return frames
        outward = np.arctan2(co[:, 0], -co[:, 1]) + Angles.TAU
        zeros = np.zeros_like(outward)
        euler = EulerXYZ.compatible(frames, np.stack([zeros, zeros, outward], axis=1))
        turned = Angles.means(euler[:, 2], outward, kp * attract_out)
        return EulerXYZ.matrices(np.stack([euler[:, 0], euler[:, 1], turned], axis=1))

    def _split_angles(
        self, grid: LevelGrid, k: int, frames: np.ndarray, has_split: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(split angle, spread angle, rotation around the parent) of every row's split at this step."""
        p = self.params
        level = grid.level
        stems = grid.stems
        keys = stems.key
        split_angle = p.split_angle[level]
        split_angle_v = p.split_angle_v[level]
        angle = KeyedRandom.sign(keys, k, Draw.SPLIT_SIGN) * (
            split_angle + KeyedRandom.between(keys, k, Draw.SPLIT_ANGLE, -split_angle_v, split_angle_v)
        )
        if level > 0:  # make branches flatter
            declination = np.degrees(np.arccos(np.clip(frames[:, 2, 2], -1.0, 1.0)))
            angle = angle * (np.maximum(1 - declination / 90, 0) * self.FLATTEN_SCALE + self.FLATTEN_MIN)
        spread = KeyedRandom.sign(keys, k, Draw.SPREAD_SIGN) * (
            split_angle + KeyedRandom.between(keys, k, Draw.SPREAD_ANGLE, -split_angle_v, split_angle_v)
        )
        start = np.radians(KeyedRandom.between(keys, k, Draw.ROTATION_START, 0.0, 360.0))
        last = np.where(stems.has_rotation, stems.last_rotation, start)
        branch_rot = last + p.rotate[0] + KeyedRandom.between(keys, k, Draw.ROTATION, -p.rotate_v[0], p.rotate_v[0])
        stems.last_rotation = np.where(has_split, branch_rot, stems.last_rotation)
        stems.has_rotation = stems.has_rotation | has_split
        return angle, spread, branch_rot

    def _split_rows(
        self,
        grid: LevelGrid,
        k: int,
        splits: np.ndarray,
        frames: np.ndarray,
        angles: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
        taper: np.ndarray,
        close_tip: bool,
    ) -> tuple[StemRows, int, np.ndarray, np.ndarray, np.ndarray, np.ndarray] | None:
        """The rows splitting off at this step, with their parents' rows and their second points (StemGrower._split)."""
        p = self.params
        level = grid.level
        segments = grid.segments
        stems = grid.stems
        total = int(splits.sum())
        if total == 0:
            return None
        angle, variation, split_angle, spread, branch_rot = angles
        rows = np.repeat(np.arange(len(stems)), splits)
        slot = np.arange(total) - np.repeat(np.cumsum(splits) - splits, splits)
        keys = KeyedRandom.derive(stems.key[rows], Kind.SPLIT, k, slot)
        length_v = p.length_v[level]
        length_scale = KeyedRandom.between(keys, k, Draw.LENGTH, 1 - length_v, 1 + length_v)
        radius_scale = np.minimum(length_scale * taper[rows], 1.0)
        if level == 0:  # trunk splits are spread evenly around the trunk
            around = pi - (Angles.TAU / (splits[rows] + 1)) * (slot + 1)
            side = Rotation.about(around, "Z") @ Rotation.about(branch_rot[rows], "Z")
        else:
            side = Rotation.about(spread[rows], "Y")
        local = side @ Rotation.about(variation[rows], "Y") @ Rotation.about(split_angle[rows] + angle[rows], "X")
        segment_length = stems.base_length[rows] * length_scale
        direction = self._segment(grid, frames[rows] @ local, segment_length, taper[rows])
        radius_first = grid.radius_at(k)[rows] * radius_scale
        closes = close_tip and k == segments - 1
        radius_second = np.zeros(total) if closes else grid.radius_at(k + 1)[rows] * radius_scale
        new = StemRows(
            {
                "key": keys,
                "spline": grid.next_spline + np.arange(total),
                "parent_stem": stems.spline[rows],
                "parent_point": k - stems.origin[rows] - 1,
                "is_split": np.ones(total, dtype=bool),
                "is_end": np.zeros(total, dtype=bool),
                "removed": np.zeros(total, dtype=bool),
                "root": stems.root[rows],
                "origin": np.full(total, k, dtype=np.int64),
                "base_length": stems.base_length[rows],
                "segment_length": segment_length,
                "curvature": stems.curvature[rows],
                "curvature_v": stems.curvature_v[rows],
                "children": stems.children[rows],
                "radius_start": stems.radius_start[rows] * radius_scale,
                "radius_end": stems.radius_end[rows] * radius_scale,
                "offset_length": stems.offset_length[rows] + stems.segment_length[rows] * (k - stems.origin[rows]),
                "roll": np.zeros(total),
                "curve_sign": np.ones(total),
                "split_last": np.ones(total, dtype=np.int8),
                "last_rotation": branch_rot[rows] + pi,
                "has_rotation": np.ones(total, dtype=bool),
            }
        )
        grid.next_spline += total
        return new, k, rows, grid.co[rows, k] + direction, radius_first, radius_second
