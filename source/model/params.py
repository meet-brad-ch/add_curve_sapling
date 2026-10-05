# SPDX-License-Identifier: GPL-3.0-or-later

"""Generation parameters derived from the operator settings: angles in radians, shapes as numbers, plain values.

Three read-only objects, each copied once from the settings (any object with the operator's property names as
attributes, in practice the operator): TreeParams (how the tree grows), WindParams (the joints the rig and the
node wind share, and the wind), and build/'s BuildParams (what Blender makes of the tree). Every value is a plain
Python number, string or tuple: the operator's property arrays die with the operator, and a model that kept them
would read freed memory when the tree is built or edited later.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import degrees, pi, radians
from typing import Any

import numpy as np

from .blossoms import BlossomShape
from .curve_data import HandleType
from .geometry import Angles, CrownShape


class InvalidSettingError(ValueError):
    """A setting value the model cannot grow a tree from; the operator reports it to the user."""


@dataclass(frozen=True, slots=True)
class Flutter:
    """The leaves' flutter settings: how strong, how fast, and how different the leaves' noise offsets are."""

    strength: float
    speed: float
    randomness: float


class BranchingMode:
    """How branches are placed around their parent (the Branching Mode setting)."""

    ORIGINAL = "original"  # rotate around each branch
    ROTATE = "rotate"  # spread evenly to point outward from the tree's center
    RANDOM = "random"  # a random point at each height
    ALL = [ORIGINAL, ROTATE, RANDOM]


class PlainParams:
    """Settings copied into plain values; read-only once _freeze() has run (at the end of __init__)."""

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_frozen", False):
            raise AttributeError(f"{type(self).__name__} is read-only; cannot set {name}")
        super().__setattr__(name, value)

    def _freeze(self) -> None:
        self._frozen = True

    @staticmethod
    def _floats(values: Iterable[float]) -> list[float]:
        """A per-level vector setting as a list of Python floats."""
        return [float(v) for v in values]

    @staticmethod
    def _bools(values: Iterable[bool]) -> list[bool]:
        """A per-level vector setting as a list of Python bools."""
        return [bool(v) for v in values]

    @staticmethod
    def _ints(values: Iterable[int]) -> list[int]:
        """A per-level vector setting as a list of Python ints."""
        return [int(v) for v in values]

    @staticmethod
    def _choice[T](table: Mapping[str, T], value: str, name: str) -> T:
        """The value an enum setting stands for; raises ValueError for one that is not a choice."""
        if value not in table:
            raise ValueError(f"{name} {value!r} is not one of {sorted(table)}")
        return table[value]


class TreeParams(PlainParams):
    """Everything the model reads to grow the tree, derived once from the settings.

    Vector values are indexed per level (LEVELS entries; deeper levels reuse the last one, see level_index()).
    """

    LEVELS = 4
    HANDLE_TYPES = {"0": HandleType.AUTO, "1": HandleType.VECTOR}

    def __init__(self, settings: Any) -> None:
        s = settings
        self.seed = int(s.seed)
        self.levels = int(s.levels)
        self._shape(s)
        self._branching(s)
        self._growth(s)
        self._pruning(s)
        self._leaves(s)
        self.handles: int = self._choice(self.HANDLE_TYPES, str(s.handleType), "Handle Type")
        # Joint Length: stem segments per joint, per level (the model names the bones the splines hang from)
        self.bone_step = self._ints(s.jointStep)
        # The envelope's base cannot be above the bare trunk
        self.prune_base_clamped = min(self.prune_base, self.base_size)
        if s.autoTaper:
            self.taper = CrownShape.auto_taper(
                self.length, self._floats(s.taper), self.shape, self.shape_s, self.levels, self.custom_shape
            )
        else:
            self.taper = self._floats(s.taper)
        self._freeze()

    def _shape(self, s: Any) -> None:
        self.scale = float(s.scale)
        self.scale_v = float(s.scaleV)
        self.shape = int(s.shape)
        self.shape_s = int(s.shapeS)
        self.custom_shape = self._floats(s.customShape)
        self.branch_dist = float(s.branchDist)
        self.rings = int(s.nrings)
        self.base_size = float(s.baseSize)
        self.base_size_s = float(s.baseSize_s)
        self.ratio = float(s.ratio)
        self.min_radius = float(s.minRadius)
        self.close_tip = bool(s.closeTip)
        self.root_flare = float(s.rootFlare)
        self.radius_tweak = self._floats(s.radiusTweak)
        self.ratio_power = float(s.ratioPower)
        self.scale0 = float(s.scale0)
        self.scale_v0 = float(s.scaleV0)

    def _branching(self, s: Any) -> None:
        self.branches = self._ints(s.branches)
        self.trunks = int(s.trunks)
        self.base_splits = int(s.baseSplits)
        self.seg_splits = self._floats(s.segSplits)
        self.split_by_len = bool(s.splitByLen)
        self.count_above_base = bool(s.countAboveBase)
        self.rotate_mode: str = self._choice({mode: mode for mode in BranchingMode.ALL}, str(s.rMode), "Branching Mode")
        self.split_angle = Angles.to_radians(s.splitAngle)
        self.split_angle_v = Angles.to_radians(s.splitAngleV)
        self.split_height = float(s.splitHeight)
        self.split_bias = float(s.splitBias)
        self.rotate = Angles.to_radians(s.rotate)
        self.rotate_v = Angles.to_radians(s.rotateV)
        self.down_angle = Angles.to_radians(s.downAngle)
        self.down_angle_v = Angles.to_radians(s.downAngleV)
        self.use_old_down_angle = bool(s.useOldDownAngle)
        self.use_parent_angle = bool(s.useParentAngle)

    def _growth(self, s: Any) -> None:
        self.length = self._floats(s.length)
        self.length_v = self._floats(s.lengthV)
        self.taper_crown = float(s.taperCrown)
        self.curve_res = self._ints(s.curveRes)
        self.curve = Angles.to_radians(s.curve)
        self.curve_v = Angles.to_radians(s.curveV)
        self.curve_back = Angles.to_radians(s.curveBack)
        self.bend_v = Angles.to_radians(s.bendV)
        self.helix = self._bools(s.helix)
        self._check_helix()
        self.attract_up = self._floats(s.attractUp)
        self.attract_out = self._floats(s.attractOut)

    def _check_helix(self) -> None:
        """A helix level takes its helix angle from Curvature Variation, which must be less than 90 degrees."""
        for level in range(self.LEVELS):
            angle = abs(self.curve_v[level])
            if self.helix[level] and angle >= pi / 2:
                raise InvalidSettingError(
                    f"Helix on level {level + 1}: Curvature Variation sets the helix angle. It must be less than "
                    f"90 degrees. It is {degrees(angle):g} degrees"
                )

    def _pruning(self, s: Any) -> None:
        self.prune = bool(s.prune)
        self.prune_width = float(s.pruneWidth)
        self.prune_base = float(s.pruneBase)
        self.prune_width_peak = float(s.pruneWidthPeak)
        self.prune_power_low = float(s.prunePowerLow)
        self.prune_power_high = float(s.prunePowerHigh)
        self.prune_ratio = float(s.pruneRatio)

    def _leaves(self, s: Any) -> None:
        # a negative count grows palmate leaves from the stem tips
        self.leaves = int(s.leaves) if s.showLeaves else 0
        self.leaf_down_angle = radians(s.leafDownAngle)
        self.leaf_down_angle_v = radians(s.leafDownAngleV)
        self.leaf_rotate = radians(s.leafRotate)
        self.leaf_rotate_v = radians(s.leafRotateV)
        self.leaf_scale = float(s.leafScale)
        self.leaf_scale_x = float(s.leafScaleX)
        self.leaf_scale_t = float(s.leafScaleT)
        self.leaf_scale_v = float(s.leafScaleV)
        self.leaf_shape = str(s.leafShape)
        self.leaf_bend = float(s.bend)
        self.leaf_angle = float(s.leafangle)
        self.horizontal_leaves = bool(s.horzLeaves)
        self.leaf_dist = int(s.leafDist)
        self.fan_angles = bool(s.fanAngles)
        self.leaves_above_base = bool(s.leavesAboveBase)
        self.blossom_rate = float(s.blossomRate)
        self.blossom_shape: str = self._choice({s: s for s in BlossomShape.ALL}, str(s.blossomShape), "Blossom Shape")
        self.blossom_scale = float(s.blossomScale)

    @classmethod
    def level_index(cls, depth: int) -> int:
        """The parameter level of a stem at `depth` below the trunk: deeper levels reuse the last one."""
        return min(depth, cls.LEVELS - 1)

    def length_product(self, level: int, start: float) -> float:
        """`start` times the relative lengths of levels 0..level."""
        for factor in self.length[: level + 1]:
            start *= factor
        return start

    def envelope(self, ratio: float) -> float:
        """Pruning envelope width factor at a height ratio of the envelope."""
        return CrownShape.envelope(ratio, self.prune_width_peak, self.prune_power_high, self.prune_power_low)

    def envelopes(self, ratio: np.ndarray) -> np.ndarray:
        """envelope() for an array of height ratios."""
        return CrownShape.envelopes(ratio, self.prune_width_peak, self.prune_power_high, self.prune_power_low)


class WindParams(PlainParams):
    """The joints (what the rig's bones and the node wind's joints are) and the wind's strength and timing."""

    def __init__(self, settings: Any, tree: TreeParams) -> None:
        s = settings
        self.bone_step = tree.bone_step
        # Joint Levels: index of the last level with joints of its own; -1 when every level has them (0)
        self.bone_levels = min(int(s.jointLevels), tree.levels) - 1
        self.wind = float(s.windStrength)
        self.gust = float(s.gustStrength)
        self.gust_f = float(s.gustFrequency)
        self.animation_speed = float(s.animationSpeed)
        self.loop_frames = int(s.loopFrames)
        self.flutter = Flutter(float(s.flutterStrength), float(s.flutterSpeed), float(s.flutterRandomness))
        self._freeze()
