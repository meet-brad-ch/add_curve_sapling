# SPDX-License-Identifier: GPL-3.0-or-later

"""Growing a stem by one segment, including splitting it into several stems."""

from math import atan2, pi, radians
from random import Random

import numpy as np
from mathutils import Euler, Matrix, Quaternion, Vector

from .curve_data import CurvePoint, CurveSpline
from .geometry import Angles, Axes, Bezier
from .level_grid import LevelGrid, StemRows
from .params import TreeParams
from .randomness import Draw, KeyedRandom, Kind
from .rotations import AttractUp, EulerXYZ, Rotation, TrackFrame, TrunkFrame
from .stem import BoneMap, BoneName, Stem


class StemGrower:
    """Adds one segment to a stem per call; splits create new stems on new splines."""

    # After a segment without a split, a split is this much more likely
    SPLIT_BOOST = 1.33
    # Split angle of a branch pointing sideways: FLATTEN_MIN of the angle, up to 1 when it points up
    FLATTEN_SCALE = 0.67
    FLATTEN_MIN = 0.33

    def __init__(self, params: TreeParams, rng: Random, scale: float) -> None:
        self.params = params
        self.rng = rng
        self.scale = scale

    def split_count(self, stem: Stem, level: int, k: int, split_value: float) -> int:
        """How many stems split off at segment k of `stem` (0, 1, or the trunk's base splits).

        Draws one random number only when the count is left to chance (draw_split).
        """
        p = self.params
        segments = p.curve_res[level]
        value = split_value
        if stem.split_last == 0:
            value = split_value * self.SPLIT_BOOST
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
            length = length / p.length_product(level, 1)
            return self.draw_split(value * length)
        return self.draw_split(value)

    def draw_split(self, probability: float) -> int:
        """0 or 1 split, with the given probability."""
        return 1 if self.rng.random() < probability else 0

    def grow(
        self,
        stem: Stem,
        level: int,
        split_count: int,
        stems: list[Stem],
        bone_map: BoneMap,
        close_tip: bool,
        kp: float,
        base_segment_length: float,
    ) -> None:
        """Grow `stem` by one segment on its spline.

        level: the parameter level (0 = trunk, at most 3).
        split_count: new stems splitting off here; each is appended to `stems` and `bone_map`.
        kp: position of this segment along the stem, 0..1.
        """
        p = self.params
        rng = self.rng
        uniform = rng.uniform

        curvature = stem.curvature
        if (level == 0) and (kp <= p.split_height):
            curvature = 0.0

        curve_angle = curvature + (uniform(0, stem.curvature_v) * kp * stem.curve_sign)
        curve_var = uniform(0, stem.curvature_v) * kp * stem.curve_sign
        stem.curve_sign *= -1

        curve_var_mat = Matrix.Rotation(curve_var, 3, "Y")

        # First find the current direction of the stem
        direction: Quaternion | Euler = stem.quat()

        if level == 0:
            adir = Axes.z()
            adir.rotate(direction)

            ry = atan2(adir[0], adir[2])
            adir.rotate(Euler((0, -ry, 0)))
            rx = atan2(adir[1], adir[2])

            direction = Euler((-rx, ry, 0), "XYZ")

        # Crown taper shortens the trunk splits that grow sideways
        if level == 0:
            dec = Angles.declination(direction) / 180
            dec = dec**2
            taper_factor = 1 - (dec * p.taper_crown * 30)
            taper_factor = max(0.1, taper_factor)
        else:
            taper_factor = 1.0

        # Outward attraction
        attract_out = p.attract_out[level]
        if (level > 0) and (kp > 0) and (attract_out > 0):
            co = stem.point.co.copy()
            d = atan2(co[0], -co[1]) + Angles.TAU
            edir = direction.to_euler("XYZ", Euler((0, 0, d), "XYZ"))  # type: ignore[union-attr]  # direction is an Euler only on level 0; this runs on level > 0
            d = Angles.mean(edir[2], d, (kp * attract_out))
            direction = Euler((edir[0], edir[1], d), "XYZ").to_quaternion()

        if split_count > 0:
            direction_vec = self._split(
                stem, level, split_count, stems, bone_map, close_tip, base_segment_length,
                direction, curve_angle, curve_var_mat, taper_factor,
            )  # fmt: skip
        else:
            # No splits: the growth direction without spreading
            direction_vec = Axes.z()
            direction_vec.rotate(Matrix.Rotation(curve_angle, 3, "X"))
            direction_vec.rotate(curve_var_mat)
            if stem.roll:
                direction_vec.rotate(Matrix.Rotation(stem.roll, 3, "Z"))  # this stem's own curve plane
            direction_vec.rotate(direction)
            stem.split_last = 0

        self._attract_up(stem, direction_vec)

        direction_vec.normalize()
        direction_vec *= stem.segment_length * taper_factor

        new_point = self._append_point(stem.spline, stem.point, direction_vec)
        new_point.radius = 0.0 if self._closes_tip(stem, close_tip) else stem.radius_at(stem.segment + 1)
        # The first point cannot have VECTOR handles before a second point exists
        if len(stem.spline.bezier_points) == 2:
            first = stem.spline.bezier_points[0]
            (first.handle_left_type, first.handle_right_type) = (Bezier.VECTOR, Bezier.VECTOR)
        stem.update_end()

    def _split(
        self, stem: Stem, level: int, split_count: int, stems: list[Stem], bone_map: BoneMap, close_tip: bool,
        base_segment_length: float, direction: Quaternion | Euler, curve_angle: float, curve_var_mat: Matrix,
        taper_factor: float,
    ) -> Vector:  # fmt: skip
        """Start `split_count` new stems at the end of `stem`; return the direction `stem` continues in."""
        p = self.params
        rng = self.rng
        uniform = rng.uniform
        cu = stem.spline.id_data

        split_angle = p.split_angle[level]
        split_angle_v = p.split_angle_v[level]
        angle = rng.choice([-1, 1]) * (split_angle + uniform(-split_angle_v, split_angle_v))
        if level > 0:
            # make branches flatter
            angle *= max(1 - Angles.declination(direction) / 90, 0) * self.FLATTEN_SCALE + self.FLATTEN_MIN
        spread_angle = rng.choice([-1, 1]) * (split_angle + uniform(-split_angle_v, split_angle_v))

        if stem.last_rotation is None:
            stem.last_rotation = radians(uniform(0, 360))
        branch_rot = stem.last_rotation + (p.rotate[0] + uniform(-p.rotate_v[0], p.rotate_v[0]))
        branch_rot_mat = Matrix.Rotation(branch_rot, 3, "Z")
        stem.last_rotation = branch_rot

        length_var = p.length_v[level]
        for i in range(split_count):
            length_scale = uniform(1 - length_var, 1 + length_var)
            radius_scale = min(length_scale * taper_factor, 1)

            new_spline = cu.splines.new(Bezier.SPLINE)
            new_point = new_spline.bezier_points[-1]
            (new_point.co, new_point.handle_left_type, new_point.handle_right_type) = (
                stem.point.co,
                Bezier.VECTOR,
                Bezier.VECTOR,
            )
            new_point.radius = stem.radius_at(stem.segment) * radius_scale

            # The new stem diverges from the current direction
            direction_vec = Axes.z()
            direction_vec.rotate(Matrix.Rotation(angle + curve_angle, 3, "X"))
            direction_vec.rotate(curve_var_mat)
            if level == 0:
                # trunk splits are spread evenly around the trunk
                direction_vec.rotate(branch_rot_mat)
                ang = pi - ((Angles.TAU) / (split_count + 1)) * (i + 1)
                direction_vec.rotate(Matrix.Rotation(ang, 3, "Z"))
            else:
                direction_vec.rotate(Matrix.Rotation(spread_angle, 3, "Y"))
            direction_vec.rotate(direction)

            self._attract_up(stem, direction_vec)

            # Make the growth vector the length of a stem segment
            direction_vec.normalize()
            segment_length = base_segment_length * length_scale
            direction_vec *= segment_length * taper_factor
            offset = stem.offset_length + (stem.segment_length * (len(stem.spline.bezier_points) - 1))

            new_point = self._append_point(new_spline, stem.point, direction_vec)
            closes = self._closes_tip(stem, close_tip)
            new_point.radius = 0.0 if closes else stem.radius_at(stem.segment + 1) * radius_scale

            split = Stem(
                new_spline,
                curvature=stem.curvature,
                curvature_v=stem.curvature_v,
                attract_up=stem.attract_up,
                segment=stem.segment + 1,
                segments=stem.segments,
                segment_length=segment_length,
                children=stem.children,
                radius_start=stem.radius_start * radius_scale,
                radius_end=stem.radius_end * radius_scale,
                index=bone_map.next_index(),
                offset_length=offset,
            )
            split.split_last = 1
            split.last_rotation = branch_rot + pi
            stems.append(split)
            split_point = len(stem.spline.bezier_points) - 2
            bone = BoneName.rounded(BoneName.of(stem.index, split_point), p.bone_step[level])
            bone_map.add_split(bone, split_point)

        # The original stem keeps growing, spread the other way
        direction_vec = Axes.z()
        direction_vec.rotate(Matrix.Rotation(-angle + curve_angle, 3, "X"))
        direction_vec.rotate(curve_var_mat)
        if level == 0:
            direction_vec.rotate(branch_rot_mat)
        else:
            direction_vec.rotate(Matrix.Rotation(-spread_angle, 3, "Y"))
        direction_vec.rotate(direction)

        stem.split_last = 1
        return direction_vec

    def _append_point(self, spline: CurveSpline, from_point: CurvePoint, direction_vec: Vector) -> CurvePoint:
        """A new last point on `spline`, `direction_vec` away from `from_point`, with the tree's handles."""
        end_co = from_point.co.copy()  # before add(): adding points can move the point array
        spline.bezier_points.add(1)
        point = spline.bezier_points[-1]
        handles = self.params.handles
        (point.co, point.handle_left_type, point.handle_right_type) = (end_co + direction_vec, handles, handles)
        return point

    @staticmethod
    def _closes_tip(stem: Stem, close_tip: bool) -> bool:
        """Whether this segment ends the stem and Close Tip makes its radius 0."""
        return close_tip and stem.segment == stem.segments - 1

    @staticmethod
    def _attract_up(stem: Stem, direction_vec: Vector) -> None:
        """Bend the growth direction up (attractUp > 0) or down."""
        track = direction_vec.to_track_quat("Z", "Y")
        up_axis = Axes.x()
        up_axis.rotate(track)
        angle = Angles.curve_up(stem.attract_up, track, stem.segments)
        direction_vec.rotate(Matrix.Rotation(-angle, 3, up_axis))  # type: ignore[arg-type]  # stub: Vector is not typed as a Sequence


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

    def grow(self, grid: LevelGrid, close_tip: bool) -> None:
        """Grow the grid's stems to full length (Close Tip ends the last segment at radius 0)."""
        stems = grid.stems
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
