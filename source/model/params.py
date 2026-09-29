# SPDX-License-Identifier: GPL-3.0-or-later

"""Generation parameters derived from the operator settings (angles in radians, enums as ints)."""

from math import radians

from .geometry import Angles, Bezier, CrownShape


class TreeParams:
    """Everything the generator reads, derived once from the settings.

    `settings` is any object with the operator's property names as attributes (the operator
    itself, or a TreeSettings); vector values are indexed per level (at most 4 entries).
    """

    def __init__(self, settings):
        s = settings
        self.seed = s.seed
        self.levels = s.levels
        self.length = s.length
        self.length_v = s.lengthV
        self.taper_crown = s.taperCrown
        self.branches = s.branches
        self.curve_res = s.curveRes
        self.curve = Angles.to_radians(s.curve)
        self.curve_v = Angles.to_radians(s.curveV)
        self.curve_back = Angles.to_radians(s.curveBack)
        self.base_splits = s.baseSplits
        self.seg_splits = s.segSplits
        self.split_by_len = s.splitByLen
        self.rotate_mode = s.rMode
        self.split_angle = Angles.to_radians(s.splitAngle)
        self.split_angle_v = Angles.to_radians(s.splitAngleV)
        self.scale = s.scale
        self.scale_v = s.scaleV
        self.attract_up = s.attractUp
        self.attract_out = s.attractOut
        self.shape = int(s.shape)
        self.shape_s = int(s.shapeS)
        self.custom_shape = s.customShape
        self.branch_dist = s.branchDist
        self.rings = s.nrings
        self.base_size = s.baseSize
        self.base_size_s = s.baseSize_s
        self.split_height = s.splitHeight
        self.split_bias = s.splitBias
        self.ratio = s.ratio
        self.min_radius = s.minRadius
        self.close_tip = s.closeTip
        self.root_flare = s.rootFlare
        self.radius_tweak = s.radiusTweak
        self.ratio_power = s.ratioPower
        self.down_angle = Angles.to_radians(s.downAngle)
        self.down_angle_v = Angles.to_radians(s.downAngleV)
        self.rotate = Angles.to_radians(s.rotate)
        self.rotate_v = Angles.to_radians(s.rotateV)
        self.scale0 = s.scale0
        self.scale_v0 = s.scaleV0
        self.use_old_down_angle = s.useOldDownAngle
        self.use_parent_angle = s.useParentAngle

        self.prune = s.prune
        self.prune_width = s.pruneWidth
        self.prune_base = s.pruneBase
        self.prune_width_peak = s.pruneWidthPeak
        self.prune_power_low = s.prunePowerLow
        self.prune_power_high = s.prunePowerHigh
        self.prune_ratio = s.pruneRatio

        # Leaves: a negative count grows palmate leaves from the stem tips
        self.leaves = s.leaves if s.showLeaves else 0
        self.leaf_down_angle = radians(s.leafDownAngle)
        self.leaf_down_angle_v = radians(s.leafDownAngleV)
        self.leaf_rotate = radians(s.leafRotate)
        self.leaf_rotate_v = radians(s.leafRotateV)
        self.leaf_scale = s.leafScale
        self.leaf_scale_x = s.leafScaleX
        self.leaf_scale_t = s.leafScaleT
        self.leaf_scale_v = s.leafScaleV
        self.leaf_shape = s.leafShape
        self.leaf_instance_name = s.leafDupliObj
        self.leaf_bend = s.bend
        self.leaf_angle = s.leafangle
        self.horizontal_leaves = s.horzLeaves
        self.leaf_dist = int(s.leafDist)
        self.leaf_material = s.leafMaterial

        self.bevel_depth = 1.0 if s.bevel else 0.0
        self.bevel_res = s.bevelRes
        self.res_u = s.resU
        self.handles = Bezier.AUTO if s.handleType == "0" else Bezier.VECTOR

        self.use_armature = s.useArm
        self.preview_armature = s.previewArm
        self.armature_animation = s.armAnim
        self.leaf_animation = s.leafAnim
        self.frame_rate = s.frameRate
        self.loop_frames = s.loopFrames
        self.wind = s.wind
        self.gust = s.gust
        self.gust_f = s.gustF
        self.leaf_wind = (s.af1, s.af2, s.af3)
        self.make_mesh = s.makeMesh
        self.armature_levels = s.armLevels
        # Bone Step simplifies the armature for the skin mesh only
        self.bone_step = s.boneStep if s.makeMesh else [1, 1, 1, 1]

        # The envelope's base cannot be above the bare trunk
        self.prune_base_clamped = min(self.prune_base, self.base_size)

        if s.autoTaper:
            self.taper = CrownShape.auto_taper(
                self.length, s.taper, self.shape, self.shape_s, self.levels, self.custom_shape
            )
        else:
            self.taper = s.taper

    def length_product(self, level, start):
        """`start` times the relative lengths of levels 0..level."""
        for factor in self.length[: level + 1]:
            start *= factor
        return start

    def envelope(self, ratio):
        """Pruning envelope width factor at a height ratio of the envelope."""
        return CrownShape.envelope(ratio, self.prune_width_peak, self.prune_power_high, self.prune_power_low)
