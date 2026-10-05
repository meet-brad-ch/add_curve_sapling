# SPDX-License-Identifier: GPL-3.0-or-later

"""Starting new stems: the trunk, and one child stem per sprout point of the level above."""

from math import atan2, copysign, cos, pi, radians, sin, sqrt
from random import Random
from typing import TYPE_CHECKING

import numpy as np
from mathutils import Euler, Matrix, Vector

from .curve_data import CurveData, CurveSpline, HandleType
from .geometry import Angles, Axes, Bezier, CrownShape
from .level_grid import LevelGrid, StemRows
from .params import TreeParams
from .randomness import Draw, KeyedRandom, Kind
from .rotations import EulerXYZ, Rotation
from .stem import BoneMap, BoneName, ChildPoint, Stem

if TYPE_CHECKING:
    from .sprouting import SproutArrays


class BranchingMode:
    """How branches are placed around their parent (the Branching Mode setting)."""

    ORIGINAL = "original"  # rotate around each branch
    ROTATE = "rotate"  # spread evenly to point outward from the tree's center
    RANDOM = "random"  # a random point at each height


class TrunkClump:
    """Where the further trunks of a clump stand: random points on a disc around the first trunk.

    As tree-gen: the disc's area grows with the number of trunks, the scale and the ratio, and no two trunks
    stand closer than GAP times the trunk radius. The disc is never smaller than the trunks need at that
    distance, so placing them always succeeds.
    """

    # Trunks stand at least this many trunk radii apart
    GAP = 2.5
    # tree-gen's disc: radius squared = trunks * scale * ratio / AREA_DIVISOR
    AREA_DIVISOR = 2.5
    TRIES = 1000

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def positions(self) -> list[Vector]:
        """Ground positions of the trunks after the first (which stands at the origin)."""
        p = self.params
        gap = self.GAP * p.scale * p.length[0] * p.ratio * p.scale0
        radius = max(sqrt(p.trunks * p.scale * p.ratio / self.AREA_DIVISOR), gap * sqrt(p.trunks))
        placed = [Vector((0.0, 0.0, 0.0))]
        for _ in range(p.trunks - 1):
            placed.append(self._free_point(placed, radius, gap))
        return placed[1:]

    def _free_point(self, placed: list[Vector], radius: float, gap: float) -> Vector:
        for _ in range(self.TRIES):
            distance = radius * sqrt(self.rng.random())  # uniform over the disc's area
            angle = self.rng.uniform(0, Angles.TAU)
            point = Vector((distance * cos(angle), distance * sin(angle), 0.0))
            if all((point - other).length >= gap for other in placed):
                return point
        raise RuntimeError(f"No room for trunk {len(placed) + 1} of {self.params.trunks} after {self.TRIES} tries")


class BranchSpawner:
    """Creates the first point of every new stem on the tree curve."""

    # The branching modes choose among the sprouts of the trunk, for the first branch level
    TRUNK_BRANCHES = 1
    # Keeps (1 - base_size) away from zero
    MAX_BASE_SIZE = 0.999

    def __init__(self, params: TreeParams, rng: Random, curve: CurveData) -> None:
        self.params = params
        self.rng = rng
        self.curve = curve

    def start_trunk(self, scale: float, position: Vector | None = None, index: int = 0) -> Stem:
        """A trunk stem standing upright at `position` (the origin by default); draws one random number (the
        radius variation)."""
        p = self.params
        spline = self.curve.splines.new(Bezier.SPLINE)
        point = spline.bezier_points[-1]
        if position is None:
            point.co = Vector((0, 0, 0))
            point.handle_right = Vector((0, 0, 1))
            point.handle_left = Vector((0, 0, -1))
        else:
            point.co = position
            point.handle_right = position + Vector((0, 0, 1))
            point.handle_left = position - Vector((0, 0, 1))
        length = scale * p.length[0]
        children = p.leaves if p.levels == 1 else p.branches[1]
        radius_start = scale * p.ratio * p.scale0 * self.rng.uniform(1 - p.scale_v0, 1 + p.scale_v0)
        radius_start, radius_end = self._radii(0, radius_start)
        point.radius = radius_start * p.root_flare
        return self._stem(spline, 0, length, children, radius_start, radius_end, index=index)

    def start_trunks(self, scale: float, bone_map: BoneMap) -> list[Stem]:
        """The trunk at the origin, then the further trunks of a clump (Trunks above 1).

        Each further trunk draws its own size (Scale with its variation) and its own curve direction; with one
        trunk, nothing more is drawn than before.
        """
        trunks = [self.start_trunk(scale)]
        p = self.params
        for position in TrunkClump(p, self.rng).positions():
            trunk_scale = p.scale + self.rng.uniform(-p.scale_v, p.scale_v)
            trunk = self.start_trunk(trunk_scale, position, bone_map.next_index())
            trunk.roll = self.rng.uniform(0, Angles.TAU)
            bone_map.add_trunk()
            trunks.append(trunk)
        return trunks

    def start_children(
        self, sprouts: list[ChildPoint], level: int, depth: int, base_size: float, scale: float, bone_map: BoneMap
    ) -> list[Stem]:
        """One new stem per sprout point; returns the stems and records their parent bones.

        level: the parameter level (at most 3); depth: the real level, which may be deeper.
        """
        p = self.params
        base_size = min(self.MAX_BASE_SIZE, base_size)
        pick = (level == self.TRUNK_BRANCHES) and (p.rotate_mode != BranchingMode.ORIGINAL)
        rotations = self._pick_trunk_sprouts(sprouts, base_size, bone_map) if pick else None
        if rotations is not None:
            sprouts = [sprout for sprout, _ in rotations]

        stems: list[Stem] = []
        old_rotate = 0.0
        for i, sprout in enumerate(sprouts):
            spline = self.curve.splines.new(Bezier.SPLINE)
            point = spline.bezier_points[-1]
            point.co = sprout.co
            down_rot = self._down_rotation(sprout, level, base_size)
            old_rotate, rotate = self._next_rotation(level, old_rotate)
            if rotations is not None and p.rotate_mode == BranchingMode.ROTATE:
                rotate = rotations[i][1]
            point.handle_right = sprout.co + self._direction(sprout, level, down_rot, rotate)

            length, children = self._length_and_children(sprout, level, depth, base_size, scale)
            radius_start = min(
                (sprout.radius_parent[0] * ((length / sprout.length_parent) ** p.ratio_power)) * p.radius_tweak[level],
                sprout.radius_parent[1],
            )
            if sprout.offset == 1:  # a stem continuing its parent's tip starts with the tip's radius
                radius_start = sprout.radius_parent[1]
            radius_start, radius_end = self._radii(level, radius_start)
            point.radius = radius_start
            stems.append(self._stem(spline, level, length, children, radius_start, radius_end, bone_map.next_index()))
            bone_map.add_stem(BoneName.rounded(sprout.parent_bone, p.bone_step[level - 1]), sprout.offset == 1)
        return stems

    def _stem(
        self,
        spline: CurveSpline,
        level: int,
        length: float,
        children: float,
        radius_start: float,
        radius_end: float,
        index: int,
    ) -> Stem:
        p = self.params
        return Stem(
            spline,
            curvature=p.curve[level] / p.curve_res[level],
            curvature_v=p.curve_v[level] / p.curve_res[level],
            attract_up=p.attract_up[level],
            segment=0,
            segments=p.curve_res[level],
            segment_length=length / p.curve_res[level],
            children=children,
            radius_start=radius_start,
            radius_end=radius_end,
            index=index,
            offset_length=0,
        )

    def _radii(self, level: int, radius_start: float) -> tuple[float, float]:
        """Start and end radius of a stem, tapered, and at least the minimum radius."""
        p = self.params
        radius_end = (radius_start * (1 - p.taper[level])) ** p.ratio_power
        return max(radius_start, p.min_radius), max(radius_end, p.min_radius)

    def _down_rotation(self, sprout: ChildPoint, level: int, base_size: float) -> Matrix:
        """Rotation away from the parent (Down Angle with its variation)."""
        p = self.params
        down_angle_v = p.down_angle_v[level]
        if p.use_old_down_angle:
            if down_angle_v < 0.0:
                down_v = down_angle_v * (1 - 2 * (0.2 + 0.8 * ((1 - sprout.offset) / (1 - base_size))))
            else:
                down_v = self.rng.uniform(-down_angle_v, down_angle_v)
        elif down_angle_v < 0.0:
            down_v = self.rng.uniform(-down_angle_v, down_angle_v)
        else:
            down_v = -down_angle_v * (1 - (1 - sprout.offset) / (1 - base_size)) ** 2

        if sprout.offset == 1:
            return Matrix.Rotation(0, 3, "X")
        return Matrix.Rotation(p.down_angle[level] + down_v, 3, "X")

    def _next_rotation(self, level: int, old_rotate: float) -> tuple[float, float]:
        """(the running rotate angle, this stem's angle): a negative Rotate alternates sides."""
        p = self.params
        if p.rotate[level] < 0.0:
            old_rotate = -copysign(p.rotate[level], old_rotate)
        else:
            old_rotate += p.rotate[level]
        return old_rotate, old_rotate + self.rng.uniform(-p.rotate_v[level], p.rotate_v[level])

    def _direction(self, sprout: ChildPoint, level: int, down_rot: Matrix, rotate: float) -> Vector:
        """The new stem's first direction, relative to its sprout point."""
        p = self.params
        direction = Axes.z()
        direction.rotate(down_rot)
        direction.rotate(Matrix.Rotation(rotate, 3, "Z"))
        if (p.rotate_mode == BranchingMode.ROTATE) and (level == self.TRUNK_BRANCHES) and (sprout.offset != 1):
            if p.use_parent_angle:
                edir = sprout.quat.to_euler("XYZ", Euler((0, 0, rotate), "XYZ"))
                edir[0] = 0
                edir[1] = 0
                edir[2] = -edir[2]
                direction.rotate(edir)
                direction.rotate(Matrix.Rotation(radians(Angles.declination(sprout.quat)), 3, "X"))
                edir[2] = -edir[2]
                direction.rotate(edir)
        else:
            direction.rotate(sprout.quat)
        return direction

    def _length_and_children(
        self, sprout: ChildPoint, level: int, depth: int, base_size: float, scale: float
    ) -> tuple[float, float]:
        """The stem's length, and how many children (branches, or leaves on the last level) it gets."""
        p = self.params
        max_length = p.length_product(level, scale)
        shape = self._shape(level, (1 - sprout.stem_offset) / (1 - base_size))
        length = sprout.length_parent * p.length[level] * shape
        children = p.branches[min(3, level + 1)] * (0.1 + 0.9 * (length / max_length))
        if depth == p.levels - 1:
            # The last level sprouts leaves instead of stems; negative counts only at the tip
            if p.leaves < 0:
                children = False
            else:
                children = (
                    p.leaves * (0.1 + 0.9 * (length / max_length)) * CrownShape.ratio(p.leaf_dist, (1 - sprout.offset))
                )
        return length, children

    def _shape(self, level: int, ratio: float) -> float:
        """Crown shape ratio: the tree's shape for the first branch level, the secondary shape deeper."""
        p = self.params
        if level == self.TRUNK_BRANCHES:
            return CrownShape.ratio(p.shape, ratio, custom=p.custom_shape)
        return CrownShape.ratio(p.shape_s, ratio)

    def _pick_trunk_sprouts(
        self, sprouts: list[ChildPoint], base_size: float, bone_map: BoneMap
    ) -> list[tuple[ChildPoint, float]]:
        """Rotate/random modes: one branch per height on each trunk, picked around that trunk.

        Returns (sprout, growth angle) pairs, trunk by trunk, each trunk's tips last; the angle is only used
        by ROTATE.
        """
        by_trunk: dict[int, list[ChildPoint]] = {}
        for sprout in sprouts:
            by_trunk.setdefault(bone_map.trunk_of(BoneName.spline(sprout.parent_bone)), []).append(sprout)
        chosen: list[tuple[ChildPoint, float]] = []
        for trunk, trunk_sprouts in by_trunk.items():
            center = self.curve.splines[trunk].bezier_points[0].co
            chosen.extend(self._pick_on_trunk(trunk_sprouts, base_size, center))
        return chosen

    def _pick_on_trunk(
        self, sprouts: list[ChildPoint], base_size: float, center: Vector
    ) -> list[tuple[ChildPoint, float]]:
        """One branch per height on one trunk (standing at `center`), with tips last."""
        p = self.params
        level = self.TRUNK_BRANCHES
        by_height: dict[float, list[ChildPoint]] = {}
        tips: list[ChildPoint] = []
        for sprout in sprouts:
            if sprout.offset == 1:
                tips.append(sprout)
            else:
                by_height.setdefault(sprout.offset, []).append(sprout)

        chosen: list[tuple[ChildPoint, float]] = []
        old_rotate = 0.0
        for height in sorted(by_height):
            candidates = by_height[height]
            if p.rotate_mode == BranchingMode.ROTATE:
                old_rotate, rotate = self._next_rotation(level, old_rotate)

                # the candidate whose angle around the trunk is closest to the rotate angle
                target = rotate % Angles.TAU
                distances = []
                for candidate in candidates:
                    angle = atan2(candidate.co[0] - center[0], -(candidate.co[1] - center[1]))
                    distances.append(
                        min((target - angle + Angles.TAU) % Angles.TAU, (angle - target + Angles.TAU) % Angles.TAU)
                    )
                best = candidates[distances.index(min(distances))]

                # the growth angle that makes the branch point in the rotate direction
                co = best.co - center
                aim = Vector((sin(rotate), cos(rotate)))
                trunk_distance = (co[0] * co[0] + co[1] * co[1]) ** 0.5
                reach = best.length_parent * p.length[1] * self._shape(level, (1 - best.offset) / (1 - base_size))
                if p.down_angle_v[1] > 0:
                    down = p.down_angle[level] + (
                        -p.down_angle_v[level] * (1 - (1 - best.offset) / (1 - base_size)) ** 2
                    )
                else:
                    down = p.down_angle[level]
                if down < (0.5 * pi):
                    reach *= sin(down) ** 2
                reach *= 0.33
                aim *= trunk_distance + reach
                to_target = aim - Vector((co[0], -co[1]))
                chosen.append((best, atan2(to_target[0], to_target[1])))
            else:
                chosen.append((candidates[self.rng.randint(0, len(candidates) - 1)], 0))
        chosen.extend((tip, 0) for tip in tips)
        return chosen


class TrunkPick:
    """Rotate/random branching modes at the first branch level: which sprout of each height gets the branch.

    Sprouts are grouped per trunk and height (the offset along the trunk); one candidate per group is chosen,
    the one nearest the rotate angle (ROTATE) or a random one (RANDOM); the trunks' tips come after their
    groups. For ROTATE each chosen sprout also gets the growth angle that aims the branch outward.
    """

    def __init__(self, params: TreeParams, root_key: np.ndarray) -> None:
        self.params = params
        self.root_key = root_key

    def choose(self, sprouts: "SproutArrays", base_size: float, centers: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """(the chosen sprouts' indices in order, their aim angles (0 for RANDOM and for tips))."""
        body = np.flatnonzero(~sprouts.is_end)
        tips = np.flatnonzero(sprouts.is_end)
        pairs = np.stack([sprouts.family[body].astype(np.float64), sprouts.offset[body]], axis=1)
        groups, inverse = np.unique(pairs, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        trunk = groups[:, 0].astype(np.int64)
        rank = np.arange(len(groups)) - np.searchsorted(trunk, trunk)
        keys = KeyedRandom.derive(self.root_key, Kind.PICK, trunk, rank)
        if self.params.rotate_mode == BranchingMode.ROTATE:
            rotate = self._rotations(keys, rank)
            best = self._nearest(sprouts, body, inverse, centers, rotate)
            aim = self._aim(sprouts, best, centers[best], rotate, base_size)
        else:
            best = self._random(body, inverse, keys, len(groups))
            aim = np.zeros(len(groups))
        chosen = np.concatenate([best, tips])
        angles = np.concatenate([aim, np.zeros(len(tips))])
        is_tip = np.concatenate([np.zeros(len(best), dtype=bool), np.ones(len(tips), dtype=bool)])
        order = np.lexsort((np.arange(len(chosen)), is_tip, sprouts.family[chosen]))
        return chosen[order], angles[order]

    def _rotations(self, keys: np.ndarray, rank: np.ndarray) -> np.ndarray:
        """The rotate angle of each height group, as BranchSpawner._next_rotation runs along a trunk."""
        p = self.params
        rotate = p.rotate[BranchSpawner.TRUNK_BRANCHES]
        rotate_v = p.rotate_v[BranchSpawner.TRUNK_BRANCHES]
        running = (-1.0) ** (rank + 1) * abs(rotate) if rotate < 0 else (rank + 1) * rotate
        return running + KeyedRandom.between(keys, 0, Draw.ROTATE, -rotate_v, rotate_v)

    @staticmethod
    def _nearest(
        sprouts: "SproutArrays", body: np.ndarray, inverse: np.ndarray, centers: np.ndarray, rotate: np.ndarray
    ) -> np.ndarray:
        """Per group, the candidate whose angle around the trunk is closest to the group's rotate angle."""
        target = rotate[inverse] % Angles.TAU
        relative = sprouts.co[body] - centers[body]
        angle = np.arctan2(relative[:, 0], -relative[:, 1])
        distance = np.minimum((target - angle + Angles.TAU) % Angles.TAU, (angle - target + Angles.TAU) % Angles.TAU)
        order = np.lexsort((body, distance, inverse))  # by group, then distance; the first candidate wins ties
        _, first = np.unique(inverse[order], return_index=True)
        return body[order][first]

    @staticmethod
    def _random(body: np.ndarray, inverse: np.ndarray, keys: np.ndarray, groups: int) -> np.ndarray:
        """Per group, a random candidate."""
        order = np.lexsort((body, inverse))
        sorted_groups = inverse[order]
        counts = np.bincount(sorted_groups, minlength=groups)
        start = np.searchsorted(sorted_groups, np.arange(groups))
        return body[order][start + KeyedRandom.pick(keys, 0, Draw.PICK, counts)]

    def _aim(
        self, sprouts: "SproutArrays", best: np.ndarray, centers: np.ndarray, rotate: np.ndarray, base_size: float
    ) -> np.ndarray:
        """The growth angle that makes each chosen branch point in its rotate direction."""
        p = self.params
        level = BranchSpawner.TRUNK_BRANCHES
        co = sprouts.co[best] - centers
        aim = np.stack([np.sin(rotate), np.cos(rotate)], axis=1)
        trunk_distance = np.hypot(co[:, 0], co[:, 1])
        offset = sprouts.offset[best]
        shape = LevelStarter.shapes(p, level, (1 - offset) / (1 - base_size))
        reach = sprouts.length_parent[best] * p.length[level] * shape
        if p.down_angle_v[level] > 0:
            down = p.down_angle[level] + (-p.down_angle_v[level] * (1 - (1 - offset) / (1 - base_size)) ** 2)
        else:
            down = np.full(len(best), p.down_angle[level])
        reach = np.where(down < 0.5 * pi, reach * np.sin(down) ** 2, reach) * 0.33
        aim = aim * (trunk_distance + reach)[:, None]
        to_target = aim - np.stack([co[:, 0], -co[:, 1]], axis=1)
        return np.arctan2(to_target[:, 0], to_target[:, 1])


class LevelStarter:
    """Starts the stems of a level as a LevelGrid: the trunks of the clump, or one child per sprout point.

    BranchSpawner as array maths: the same lengths, radii, down angles, rotations and directions, for every
    sprout at once. The trunks still draw from the tree's random stream (a handful of numbers).
    """

    def __init__(self, params: TreeParams, rng: Random, root_key: np.ndarray) -> None:
        self.params = params
        self.rng = rng
        self.root_key = root_key

    def trunks(self, scale: float) -> LevelGrid:
        """The trunk at the origin, then the further trunks of a clump (Trunks above 1)."""
        p = self.params
        scales = [scale]
        positions = [np.zeros(3)]
        radii = [self._trunk_radius(scale)]
        rolls = [0.0]
        for position in TrunkClump(p, self.rng).positions():
            scales.append(p.scale + self.rng.uniform(-p.scale_v, p.scale_v))
            positions.append(np.array(position.to_tuple()))
            radii.append(self._trunk_radius(scales[-1]))
            rolls.append(self.rng.uniform(0, Angles.TAU))
        count = len(scales)
        radius_start, radius_end = self._radii(0, np.array(radii))
        children = p.leaves if p.levels == 1 else p.branches[1]
        rows = self._rows(
            KeyedRandom.derive(self.root_key, Kind.TRUNK, np.arange(count), 0),
            np.arange(count),
            {
                "parent_stem": np.full(count, -1, dtype=np.int64),
                "parent_point": np.zeros(count, dtype=np.int64),
                "is_end": np.zeros(count, dtype=bool),
                "children": np.full(count, float(children)),
                "roll": np.array(rolls),
            },
            0,
            np.array(scales) * p.length[0],
            radius_start,
            radius_end,
        )
        up = np.tile([0.0, 0.0, 1.0], (count, 1))
        return LevelGrid(
            0, 0, p.curve_res[0], self._handles(), rows, np.array(positions), up, radius_start * p.root_flare, count
        )

    def children(
        self,
        sprouts: "SproutArrays",
        level: int,
        depth: int,
        base_size: float,
        scale: float,
        spline_base: int,
        previous: LevelGrid,
    ) -> LevelGrid:
        """One new stem per sprout point of the level above.

        level: the parameter level (at most 3); depth: the real level, which may be deeper.
        """
        p = self.params
        base_size = min(BranchSpawner.MAX_BASE_SIZE, base_size)
        aim = None
        if level == BranchSpawner.TRUNK_BRANCHES and p.rotate_mode != BranchingMode.ORIGINAL:
            order, aim = TrunkPick(p, self.root_key).choose(sprouts, base_size, previous.co[sprouts.family, 0])
            sprouts = sprouts.take(order)
        count = sprouts.count
        keys = KeyedRandom.derive(sprouts.parent_key, Kind.CHILD, sprouts.position + 1, 0)
        rotate = self._rotations(level, keys)
        if aim is not None and p.rotate_mode == BranchingMode.ROTATE:
            rotate = aim
        direction = self._directions(sprouts, level, self._down_angles(sprouts, level, base_size, keys), rotate)
        length, children = self._lengths_and_children(sprouts, level, depth, base_size, scale)
        radius_start = np.minimum(
            sprouts.radius_parent[:, 0] * (length / sprouts.length_parent) ** p.ratio_power * p.radius_tweak[level],
            sprouts.radius_parent[:, 1],
        )
        # a stem continuing its parent's tip starts with the tip's radius
        radius_start = np.where(sprouts.is_end, sprouts.radius_parent[:, 1], radius_start)
        radius_start, radius_end = self._radii(level, radius_start)
        rows = self._rows(
            keys,
            spline_base + np.arange(count),
            {
                "parent_stem": sprouts.parent_spline,
                "parent_point": sprouts.parent_point,
                "is_end": sprouts.is_end,
                "children": children,
                "roll": np.zeros(count),
            },
            level,
            length,
            radius_start,
            radius_end,
        )
        return LevelGrid(
            level,
            depth,
            p.curve_res[level],
            self._handles(),
            rows,
            sprouts.co,
            direction,
            radius_start,
            spline_base + count,
        )

    def _handles(self) -> int:
        return HandleType.code(self.params.handles)

    def _trunk_radius(self, scale: float) -> float:
        """A trunk's start radius: draws one random number (the radius variation)."""
        p = self.params
        return scale * p.ratio * p.scale0 * self.rng.uniform(1 - p.scale_v0, 1 + p.scale_v0)

    def _radii(self, level: int, radius_start: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Start and end radius of each stem, tapered, and at least the minimum radius."""
        p = self.params
        radius_end = (radius_start * (1 - p.taper[level])) ** p.ratio_power
        return np.maximum(radius_start, p.min_radius), np.maximum(radius_end, p.min_radius)

    def _rows(
        self,
        keys: np.ndarray,
        spline: np.ndarray,
        given: dict[str, np.ndarray],
        level: int,
        length: np.ndarray,
        radius_start: np.ndarray,
        radius_end: np.ndarray,
    ) -> StemRows:
        """The stems' rows at their start: `given` holds parent_stem, parent_point, is_end, children and roll."""
        p = self.params
        segments = p.curve_res[level]
        count = len(keys)
        values = dict(given)
        values.update(
            {
                "key": keys,
                "spline": spline,
                "is_split": np.zeros(count, dtype=bool),
                "root": np.arange(count),
                "origin": np.zeros(count, dtype=np.int64),
                "base_length": length / segments,
                "segment_length": length / segments,
                "curvature": np.full(count, p.curve[level] / segments),
                "curvature_v": np.full(count, p.curve_v[level] / segments),
                "radius_start": radius_start,
                "radius_end": radius_end,
                "offset_length": np.zeros(count),
                "curve_sign": np.ones(count),
                "split_last": np.zeros(count, dtype=np.int8),
                "last_rotation": np.zeros(count),
                "has_rotation": np.zeros(count, dtype=bool),
            }
        )
        return StemRows(values)

    def _down_angles(self, sprouts: "SproutArrays", level: int, base_size: float, keys: np.ndarray) -> np.ndarray:
        """Each child's angle away from its parent (Down Angle with its variation); none for a tip's continuation."""
        p = self.params
        down_angle_v = p.down_angle_v[level]
        offset = sprouts.offset
        drawn = KeyedRandom.between(keys, 0, Draw.DOWN, -down_angle_v, down_angle_v)
        if p.use_old_down_angle:
            fixed = down_angle_v * (1 - 2 * (0.2 + 0.8 * ((1 - offset) / (1 - base_size))))
            down_v = fixed if down_angle_v < 0.0 else drawn
        else:
            down_v = drawn if down_angle_v < 0.0 else -down_angle_v * (1 - (1 - offset) / (1 - base_size)) ** 2
        return np.where(sprouts.is_end, 0.0, p.down_angle[level] + down_v)

    def _rotations(self, level: int, keys: np.ndarray) -> np.ndarray:
        """Each child's rotation about its parent: the running rotate angle (a negative Rotate alternates
        sides) with its variation."""
        p = self.params
        rotate = p.rotate[level]
        rotate_v = p.rotate_v[level]
        index = np.arange(len(keys))
        running = (-1.0) ** (index + 1) * abs(rotate) if rotate < 0 else (index + 1) * rotate
        return running + KeyedRandom.between(keys, 0, Draw.ROTATE, -rotate_v, rotate_v)

    def _directions(self, sprouts: "SproutArrays", level: int, down: np.ndarray, rotate: np.ndarray) -> np.ndarray:
        """Each new stem's first direction (BranchSpawner._direction for every sprout)."""
        p = self.params
        local = (Rotation.about(rotate, "Z") @ Rotation.about(down, "X"))[:, :, 2]
        frames = sprouts.frame
        direction = Rotation.apply(frames, local)
        if p.rotate_mode == BranchingMode.ROTATE and level == BranchSpawner.TRUNK_BRANCHES:
            if p.use_parent_angle:
                euler = EulerXYZ.compatible(frames, np.stack([np.zeros_like(rotate), np.zeros_like(rotate), rotate], 1))
                declination = np.arccos(np.clip(frames[:, 2, 2], -1.0, 1.0))
                turn = (
                    Rotation.about(euler[:, 2], "Z")
                    @ Rotation.about(declination, "X")
                    @ Rotation.about(-euler[:, 2], "Z")
                )
                adjusted = Rotation.apply(turn, local)
            else:
                adjusted = local
            direction = np.where(sprouts.is_end[:, None], direction, adjusted)
        return direction

    def _lengths_and_children(
        self, sprouts: "SproutArrays", level: int, depth: int, base_size: float, scale: float
    ) -> tuple[np.ndarray, np.ndarray]:
        """Each stem's length, and how many children (branches, or leaves on the last level) it gets."""
        p = self.params
        max_length = p.length_product(level, scale)
        shape = self.shapes(p, level, (1 - sprouts.stem_offset) / (1 - base_size))
        length = sprouts.length_parent * p.length[level] * shape
        children = p.branches[min(3, level + 1)] * (0.1 + 0.9 * (length / max_length))
        if depth == p.levels - 1:
            # The last level sprouts leaves instead of stems; negative counts only at the tip
            if p.leaves < 0:
                children = np.zeros(len(length))
            else:
                children = (
                    p.leaves * (0.1 + 0.9 * (length / max_length)) * CrownShape.ratios(p.leaf_dist, 1 - sprouts.offset)
                )
        return length, children

    @staticmethod
    def shapes(params: TreeParams, level: int, ratio: np.ndarray) -> np.ndarray:
        """Crown shape ratios: the tree's shape for the first branch level, the secondary shape deeper."""
        if level == BranchSpawner.TRUNK_BRANCHES:
            return CrownShape.ratios(params.shape, ratio, custom=params.custom_shape)
        return CrownShape.ratios(params.shape_s, ratio)
