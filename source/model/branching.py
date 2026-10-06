# SPDX-License-Identifier: GPL-3.0-or-later

"""Starting the stems of a level: the trunks, and one child stem per sprout point of the level above."""

from dataclasses import dataclass
from math import atan2, cos, pi, sin, sqrt
from random import Random
from typing import TYPE_CHECKING

import numpy as np

from .geometry import Angles, CrownShape
from .level_grid import LevelGrid, StemRows
from .params import BranchingMode, TreeParams
from .randomness import Draw, KeyedRandom, Kind
from .rotations import EulerXYZ, Rotation

if TYPE_CHECKING:
    from .sprouting import SproutArrays


@dataclass(frozen=True, slots=True)
class TrunkPicks:
    """The sprouts a branching mode chose at the first branch level, and the growth angle aiming each branch."""

    order: np.ndarray  # the chosen sprouts' indices, in order
    aim: np.ndarray  # the aim angle per chosen sprout (0 for RANDOM and for tips)


@dataclass(frozen=True, slots=True)
class Radii:
    """Every stem's start and end radius."""

    start: np.ndarray
    end: np.ndarray


@dataclass(frozen=True, slots=True)
class LengthsAndChildren:
    """Every stem's length, and how many children (branches, or leaves on the last level) it gets."""

    length: np.ndarray
    children: np.ndarray


@dataclass(frozen=True, slots=True)
class PickedSprouts:
    """The sprouts a level starts from, and the aim angles ROTATE gives them (None in the other modes)."""

    sprouts: "SproutArrays"
    aim: np.ndarray | None


@dataclass(frozen=True, slots=True)
class StemStart:
    """What a level's stems know about their parents when they start."""

    parent_stem: np.ndarray
    parent_point: np.ndarray
    is_end: np.ndarray
    children: np.ndarray
    roll: np.ndarray


class TrunkClump:
    """Where the further trunks of a clump stand: random points on a disc around the first trunk.

    As tree-gen: the disc's area grows with the number of trunks, the scale and the ratio, and no two trunks
    stand closer than GAP times the trunk radius. The disc is never smaller than the trunks need at that
    distance, so placing them always succeeds. The points are float32, as mathutils vectors are, so the clumps
    stay where they were.
    """

    # Trunks stand at least this many trunk radii apart
    GAP = 2.5
    # tree-gen's disc: radius squared = trunks * scale * ratio / AREA_DIVISOR
    AREA_DIVISOR = 2.5
    TRIES = 1000

    def __init__(self, params: TreeParams, rng: Random) -> None:
        self.params = params
        self.rng = rng

    def positions(self) -> list[np.ndarray]:
        """Ground positions of the trunks after the first (which stands at the origin), (3,) float32 each."""
        p = self.params
        gap = self.GAP * p.scale * p.length[0] * p.ratio * p.scale0
        radius = max(sqrt(p.trunks * p.scale * p.ratio / self.AREA_DIVISOR), gap * sqrt(p.trunks))
        placed = [np.zeros(3, dtype=np.float32)]
        for _ in range(p.trunks - 1):
            placed.append(self._free_point(placed, radius, gap))
        return placed[1:]

    def _free_point(self, placed: list[np.ndarray], radius: float, gap: float) -> np.ndarray:
        for _ in range(self.TRIES):
            distance = radius * sqrt(self.rng.random())  # uniform over the disc's area
            angle = self.rng.uniform(0, Angles.TAU)
            point = np.array([distance * cos(angle), distance * sin(angle), 0.0], dtype=np.float32)
            if all(self._apart(point, other) >= gap for other in placed):
                return point
        raise RuntimeError(f"No room for trunk {len(placed) + 1} of {self.params.trunks} after {self.TRIES} tries")

    @staticmethod
    def _apart(a: np.ndarray, b: np.ndarray) -> float:
        """The distance of two float32 points as mathutils measures it (Vector.length, to the bit): a float32
        difference, each square in float32, their sum and its square root in double."""
        d = a - b
        squares = (d * d).astype(np.float64)
        return sqrt(float((squares[2] + squares[1]) + squares[0]))


class TrunkPick:
    """Rotate/random branching modes at the first branch level: which sprout of each height gets the branch.

    Sprouts are grouped per trunk and height (the offset along the trunk); one candidate per group is chosen,
    the one nearest the rotate angle (ROTATE) or a random one (RANDOM); the trunks' tips come after their
    groups. For ROTATE each chosen sprout also gets the growth angle that aims the branch outward.
    """

    def __init__(self, params: TreeParams, root_key: np.ndarray) -> None:
        self.params = params
        self.root_key = root_key

    def choose(self, sprouts: "SproutArrays", base_size: float, centers: np.ndarray) -> TrunkPicks:
        """The chosen sprouts in order, with their aim angles."""
        body = np.flatnonzero(~sprouts.is_end)
        tips = np.flatnonzero(sprouts.is_end)
        # one group per family position: the pieces of a split trunk sprout at the same positions, each at a
        # slightly different offset (measured on its own length), and share one branch per height
        pairs = np.stack([sprouts.family[body], sprouts.position[body]], axis=1)
        groups, inverse = np.unique(pairs, axis=0, return_inverse=True)
        inverse = inverse.reshape(-1)
        trunk = groups[:, 0].astype(np.int64)
        rank = np.arange(len(groups)) - np.searchsorted(trunk, trunk)
        keys = KeyedRandom.derive(self.root_key, Kind.PICK, trunk, rank)
        mode = self.params.rotate_mode
        if mode == BranchingMode.ROTATE:
            picks = self._rotate_choice(sprouts, body, inverse, centers, keys, rank, base_size)
        elif mode == BranchingMode.RANDOM:
            picks = TrunkPicks(self._random(body, inverse, keys, len(groups)), np.zeros(len(groups)))
        else:
            raise ValueError(f"Branching Mode {mode!r} does not choose among the trunk's sprouts")
        chosen = np.concatenate([picks.order, tips])
        angles = np.concatenate([picks.aim, np.zeros(len(tips))])
        is_tip = np.concatenate([np.zeros(len(picks.order), dtype=bool), np.ones(len(tips), dtype=bool)])
        order = np.lexsort((np.arange(len(chosen)), is_tip, sprouts.family[chosen]))
        return TrunkPicks(chosen[order], angles[order])

    def _rotate_choice(
        self,
        sprouts: "SproutArrays",
        body: np.ndarray,
        inverse: np.ndarray,
        centers: np.ndarray,
        keys: np.ndarray,
        rank: np.ndarray,
        base_size: float,
    ) -> TrunkPicks:
        """ROTATE: per group the candidate nearest the running rotate angle, aimed outward."""
        rotate = self._rotations(keys, rank)
        best = self._nearest(sprouts, body, inverse, centers, rotate)
        return TrunkPicks(best, self._aim(sprouts, best, centers[best], rotate, base_size))

    def _rotations(self, keys: np.ndarray, rank: np.ndarray) -> np.ndarray:
        """The rotate angle of each height group, as the running rotate angle goes along a trunk."""
        return LevelStarter.running_rotate(self.params, LevelStarter.TRUNK_BRANCHES, keys, rank)

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
        level = LevelStarter.TRUNK_BRANCHES
        co = sprouts.co[best] - centers
        aim = np.stack([np.sin(rotate), np.cos(rotate)], axis=1)
        trunk_distance = np.hypot(co[:, 0], co[:, 1])
        offset = sprouts.offset[best]
        shape = LevelStarter.shapes(p, level, (1 - offset) / (1 - base_size))
        reach = sprouts.length_parent[best] * p.length[level] * shape
        if p.down_angle_v[level] > 0:
            down = p.down_angle[level] + LevelStarter.down_taper(p, level, offset, base_size)
        else:
            down = np.full(len(best), p.down_angle[level])
        reach = np.where(down < 0.5 * pi, reach * np.sin(down) ** 2, reach) * 0.33
        aim = aim * (trunk_distance + reach)[:, None]
        to_target = aim - np.stack([co[:, 0], -co[:, 1]], axis=1)
        return np.arctan2(to_target[:, 0], to_target[:, 1])


class LevelStarter:
    """Starts the stems of a level as a LevelGrid: the trunks of the clump, or one child per sprout point.

    Every sprout gets its length, radii, down angle, rotation and direction in one array operation; the trunks
    draw a handful of numbers from the tree's random stream.
    """

    # The branching modes choose among the sprouts of the trunk, for the first branch level
    TRUNK_BRANCHES = 1
    # Trunk Height 1 (the whole trunk bare) would divide the position ratio (1 - offset) / (1 - base_size) by
    # zero: the ratio is taken at 0.999 instead, so a tip sprout (offset 1) gets exactly 0 and the branches
    # continue from the trunk's tip only
    MAX_BASE_SIZE = 0.999

    def __init__(self, params: TreeParams, rng: Random, root_key: np.ndarray) -> None:
        self.params = params
        self.rng = rng
        self.root_key = root_key

    def _trunk_roll(self, position: np.ndarray) -> float:
        """A further trunk's roll, which sets the plane it curves in: random, or with Trunks Face Out turned so a
        positive Curvature bends it away from the clump's centre, as tree-gen turns its trunks."""
        if self.params.trunks_face_out:
            return atan2(float(position[1]), float(position[0])) + pi / 2
        return self.rng.uniform(0, Angles.TAU)

    def trunks(self, scale: float) -> LevelGrid:
        """The trunk at the origin, then the further trunks of a clump (Trunks above 1)."""
        p = self.params
        scales = [scale]
        positions = [np.zeros(3)]
        radii = [self._trunk_radius(scale)]
        rolls = [0.0]
        for position in TrunkClump(p, self.rng).positions():
            scales.append(p.scale + self.rng.uniform(-p.scale_v, p.scale_v))
            positions.append(position.astype(np.float64))
            radii.append(self._trunk_radius(scales[-1]))
            rolls.append(self._trunk_roll(position))
        count = len(scales)
        trunk_radii = self._radii(0, np.array(radii))
        children = p.leaves if p.levels == 1 else p.branches[1]
        start = StemStart(
            parent_stem=np.full(count, -1, dtype=np.int64),
            parent_point=np.zeros(count, dtype=np.int64),
            is_end=np.zeros(count, dtype=bool),
            children=np.full(count, float(children)),
            roll=np.array(rolls),
        )
        keys = KeyedRandom.derive(self.root_key, Kind.TRUNK, np.arange(count), 0)
        rows = self._rows(keys, np.arange(count), start, 0, np.array(scales) * p.length[0], trunk_radii)
        up = np.tile([0.0, 0.0, 1.0], (count, 1))
        return LevelGrid(
            0, p.curve_res[0], p.handles, rows, np.array(positions), up, trunk_radii.start * p.root_flare, count
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

        level: the parameter level (at most TreeParams.LEVELS - 1); depth: the real level, which may be deeper.
        """
        p = self.params
        base_size = min(LevelStarter.MAX_BASE_SIZE, base_size)
        picked = self._trunk_pick(sprouts, level, base_size, previous)
        sprouts = picked.sprouts
        count = sprouts.count
        keys = KeyedRandom.derive(sprouts.parent_key, Kind.CHILD, sprouts.position + 1, 0)
        rotate = self._rotations(level, keys) if picked.aim is None else picked.aim
        direction = self._directions(sprouts, level, self._down_angles(sprouts, level, base_size, keys), rotate)
        grown = self._lengths_and_children(sprouts, level, depth, base_size, scale)
        radii = self._start_radii(sprouts, level, grown.length)
        start = StemStart(
            parent_stem=sprouts.parent_spline,
            parent_point=sprouts.parent_point,
            is_end=sprouts.is_end,
            children=grown.children,
            roll=np.zeros(count),
        )
        rows = self._rows(keys, spline_base + np.arange(count), start, level, grown.length, radii)
        return LevelGrid(
            level, p.curve_res[level], p.handles, rows, sprouts.co, direction, radii.start, spline_base + count
        )

    def _trunk_pick(self, sprouts: "SproutArrays", level: int, base_size: float, previous: LevelGrid) -> PickedSprouts:
        """At the first branch level, the Rotate and Random modes choose among the trunk's sprouts (Rotate also
        aims the branches); elsewhere every sprout starts a stem."""
        p = self.params
        if level != LevelStarter.TRUNK_BRANCHES or p.rotate_mode == BranchingMode.ORIGINAL:
            return PickedSprouts(sprouts, None)
        picks = TrunkPick(p, self.root_key).choose(sprouts, base_size, previous.co[sprouts.family, 0])
        aim = picks.aim if p.rotate_mode == BranchingMode.ROTATE else None
        return PickedSprouts(sprouts.take(picks.order), aim)

    def _start_radii(self, sprouts: "SproutArrays", level: int, length: np.ndarray) -> Radii:
        """Every child's start and end radius: from its parent's radius and the length ratio, at most the
        parent's radius at the sprout; a stem continuing its parent's tip starts with the tip's radius."""
        p = self.params
        radius_start = np.minimum(
            sprouts.radius_parent[:, 0] * (length / sprouts.length_parent) ** p.ratio_power * p.radius_tweak[level],
            sprouts.radius_parent[:, 1],
        )
        radius_start = np.where(sprouts.is_end, sprouts.radius_parent[:, 1], radius_start)
        return self._radii(level, radius_start)

    def _trunk_radius(self, scale: float) -> float:
        """A trunk's start radius: draws one random number (the radius variation)."""
        p = self.params
        return scale * p.ratio * p.scale0 * self.rng.uniform(1 - p.scale_v0, 1 + p.scale_v0)

    def _radii(self, level: int, radius_start: np.ndarray) -> Radii:
        """Start and end radius of each stem, tapered, and at least the minimum radius."""
        p = self.params
        radius_end = (radius_start * (1 - p.taper[level])) ** p.ratio_power
        return Radii(np.maximum(radius_start, p.min_radius), np.maximum(radius_end, p.min_radius))

    def _rows(
        self,
        keys: np.ndarray,
        spline: np.ndarray,
        start: StemStart,
        level: int,
        length: np.ndarray,
        radii: Radii,
    ) -> StemRows:
        """The stems' rows at their start."""
        p = self.params
        segments = p.curve_res[level]
        count = len(keys)
        return StemRows(
            key=keys,
            spline=spline,
            parent_stem=start.parent_stem,
            parent_point=start.parent_point,
            is_split=np.zeros(count, dtype=bool),
            is_end=start.is_end,
            removed=np.zeros(count, dtype=bool),
            root=np.arange(count),
            origin=np.zeros(count, dtype=np.int64),
            base_length=length / segments,
            segment_length=length / segments,
            curvature=np.full(count, p.curve[level] / segments),
            curvature_v=np.full(count, p.curve_v[level] / segments),
            children=start.children,
            radius_start=radii.start,
            radius_end=radii.end,
            offset_length=np.zeros(count),
            roll=start.roll,
            curve_sign=np.ones(count),
            split_last=np.zeros(count, dtype=np.int8),
            last_rotation=np.zeros(count),
            has_rotation=np.zeros(count, dtype=bool),
        )

    @staticmethod
    def down_taper(params: TreeParams, level: int, offset: np.ndarray, base_size: float) -> np.ndarray:
        """The Down Angle Variation along the parent: the down angle decreases towards the parent's end."""
        return -params.down_angle_v[level] * (1 - (1 - offset) / (1 - base_size)) ** 2

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
            down_v = drawn if down_angle_v < 0.0 else self.down_taper(p, level, offset, base_size)
        return np.where(sprouts.is_end, 0.0, p.down_angle[level] + down_v)

    @staticmethod
    def running_rotate(params: TreeParams, level: int, keys: np.ndarray, ordinal: np.ndarray) -> np.ndarray:
        """The running rotate angle of the ordinal-th child around its parent (a negative Rotate alternates
        sides), with its random variation."""
        rotate = params.rotate[level]
        rotate_v = params.rotate_v[level]
        running = (-1.0) ** (ordinal + 1) * abs(rotate) if rotate < 0 else (ordinal + 1) * rotate
        return running + KeyedRandom.between(keys, 0, Draw.ROTATE, -rotate_v, rotate_v)

    def _rotations(self, level: int, keys: np.ndarray) -> np.ndarray:
        """Each child's rotation about its parent, in sprout order."""
        return self.running_rotate(self.params, level, keys, np.arange(len(keys)))

    def _directions(self, sprouts: "SproutArrays", level: int, down: np.ndarray, rotate: np.ndarray) -> np.ndarray:
        """Each new stem's first direction for every sprout at once."""
        p = self.params
        local = (Rotation.about(rotate, "Z") @ Rotation.about(down, "X"))[:, :, 2]
        frames = sprouts.frame
        direction = Rotation.apply(frames, local)
        if p.rotate_mode == BranchingMode.ROTATE and level == LevelStarter.TRUNK_BRANCHES:
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
    ) -> LengthsAndChildren:
        """Each stem's length, and how many children (branches, or leaves on the last level) it gets."""
        p = self.params
        max_length = p.length_product(level, scale)
        shape = self.shapes(p, level, (1 - sprouts.stem_offset) / (1 - base_size))
        length = sprouts.length_parent * p.length[level] * shape
        children = p.branches[TreeParams.level_index(level + 1)] * (0.1 + 0.9 * (length / max_length))
        if depth == p.levels - 1:
            # The last level sprouts leaves instead of stems; negative counts only at the tip
            if p.leaves < 0:
                children = np.zeros(len(length))
            else:
                children = (
                    p.leaves * (0.1 + 0.9 * (length / max_length)) * CrownShape.ratios(p.leaf_dist, 1 - sprouts.offset)
                )
        return LengthsAndChildren(length, children)

    @staticmethod
    def shapes(params: TreeParams, level: int, ratio: np.ndarray) -> np.ndarray:
        """Crown shape ratios: the tree's shape for the first branch level, the secondary shape deeper."""
        if level == LevelStarter.TRUNK_BRANCHES:
            return CrownShape.ratios(params.shape, ratio, custom=params.custom_shape)
        return CrownShape.ratios(params.shape_s, ratio)
