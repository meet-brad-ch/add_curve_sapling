# SPDX-License-Identifier: GPL-3.0-or-later

"""Starting new stems: the trunk, and one child stem per sprout point of the level above."""

from math import atan2, copysign, cos, pi, radians, sin

from mathutils import Euler, Matrix, Vector

from .geometry import Angles, Axes, CrownShape
from .stem import BoneName, ChildPoint, Stem


class BranchSpawner:
    """Creates the first point of every new stem on the tree curve."""

    def __init__(self, params, rng, curve):
        self.params = params
        self.rng = rng
        self.curve = curve

    def start_trunk(self, scale):
        """The trunk stem, standing at the origin."""
        p = self.params
        spline = self.curve.splines.new("BEZIER")
        self.curve.resolution_u = p.res_u
        point = spline.bezier_points[-1]
        point.co = Vector((0, 0, 0))
        point.handle_right = Vector((0, 0, 1))
        point.handle_left = Vector((0, 0, -1))
        length = scale * p.length[0]
        curvature = p.curve[0] / p.curve_res[0]
        children = p.leaves if p.levels == 1 else p.branches[1]
        radius_start = scale * p.ratio * p.scale0 * self.rng.uniform(1 - p.scale_v0, 1 + p.scale_v0)
        radius_end = (radius_start * (1 - p.taper[0])) ** p.ratio_power
        radius_start = max(radius_start, p.min_radius)
        radius_end = max(radius_end, p.min_radius)
        point.radius = radius_start * p.root_flare
        return Stem(
            spline,
            curvature,
            p.curve_v[0] / p.curve_res[0],
            p.attract_up[0],
            0,
            p.curve_res[0],
            length / p.curve_res[0],
            children,
            radius_start,
            radius_end,
            0,
            0,
            None,
        )

    def start_children(self, sprouts, level, depth, base_size, scale, bone_map):
        """One new stem per sprout point; returns the stems and records their parent bones.

        level: the parameter level (at most 3); depth: the real level, which may be deeper.
        """
        p = self.params
        rng = self.rng
        base_size = min(0.999, base_size)  # never divide by zero below
        rotations: list[float] = []
        if (level == 1) and (p.rotate_mode != "original"):
            sprouts, rotations = self._pick_trunk_sprouts(sprouts, level, base_size)

        stems: list[Stem] = []
        old_rotate = 0.0
        for i, sprout in enumerate(sprouts):
            spline = self.curve.splines.new("BEZIER")
            self.curve.resolution_u = p.res_u
            point = spline.bezier_points[-1]
            point.co = sprout.co
            direction = Axes.z()

            down_angle_v = p.down_angle_v[level]
            if p.use_old_down_angle:
                if down_angle_v < 0.0:
                    down_v = down_angle_v * (1 - 2 * (0.2 + 0.8 * ((1 - sprout.offset) / (1 - base_size))))
                else:
                    down_v = rng.uniform(-down_angle_v, down_angle_v)
            elif down_angle_v < 0.0:
                down_v = rng.uniform(-down_angle_v, down_angle_v)
            else:
                down_v = -down_angle_v * (1 - (1 - sprout.offset) / (1 - base_size)) ** 2

            if sprout.offset == 1:
                down_rot = Matrix.Rotation(0, 3, "X")
            else:
                down_rot = Matrix.Rotation(p.down_angle[level] + down_v, 3, "X")

            # A negative rotate angle alternates sides; otherwise keep turning by it
            if p.rotate[level] < 0.0:
                old_rotate = -copysign(p.rotate[level], old_rotate)
            else:
                old_rotate += p.rotate[level]
            rotate = old_rotate + rng.uniform(-p.rotate_v[level], p.rotate_v[level])
            if (level == 1) and (p.rotate_mode == "rotate"):
                rotate = rotations[i]

            direction.rotate(down_rot)
            direction.rotate(Matrix.Rotation(rotate, 3, "Z"))

            if (p.rotate_mode == "rotate") and (level == 1) and (sprout.offset != 1):
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

            point.handle_right = sprout.co + direction

            # Branch length and number of children
            max_length = scale
            for length in p.length[: level + 1]:
                max_length *= length
            if level == 1:
                shape = CrownShape.ratio(p.shape, (1 - sprout.stem_offset) / (1 - base_size), custom=p.custom_shape)
            else:
                shape = CrownShape.ratio(p.shape_s, (1 - sprout.stem_offset) / (1 - base_size))
            length = sprout.length_parent * p.length[level] * shape
            children = p.branches[min(3, level + 1)] * (0.1 + 0.9 * (length / max_length))

            # The last level sprouts leaves instead of stems
            if depth == p.levels - 1:
                if p.leaves < 0:
                    children = False
                else:
                    children = (
                        p.leaves
                        * (0.1 + 0.9 * (length / max_length))
                        * CrownShape.ratio(p.leaf_dist, (1 - sprout.offset))
                    )

            radius_start = min(
                (sprout.radius_parent[0] * ((length / sprout.length_parent) ** p.ratio_power)) * p.radius_tweak[level],
                sprout.radius_parent[1],
            )
            if sprout.offset == 1:
                radius_start = sprout.radius_parent[1]
            radius_end = (radius_start * (1 - p.taper[level])) ** p.ratio_power
            radius_start = max(radius_start, p.min_radius)
            radius_end = max(radius_end, p.min_radius)
            point.radius = radius_start

            stems.append(
                Stem(
                    spline,
                    p.curve[level] / p.curve_res[level],
                    p.curve_v[level] / p.curve_res[level],
                    p.attract_up[level],
                    0,
                    p.curve_res[level],
                    length / p.curve_res[level],
                    children,
                    radius_start,
                    radius_end,
                    bone_map.next_index(),
                    0,
                    sprout.quat,
                )
            )
            bone_map.add_stem(BoneName.rounded(sprout.parent_bone, p.bone_step[level - 1]), sprout.offset == 1)
        return stems

    def _pick_trunk_sprouts(self, sprouts, level, base_size):
        """Rotate/random modes: one branch per height on the trunk, picked around the trunk.

        Returns the chosen sprouts (tips last) and, for "rotate", the growth angle of each.
        """
        p = self.params
        rng = self.rng
        by_height: dict[float, list[ChildPoint]] = {}
        tips: list[ChildPoint] = []
        for sprout in sprouts:
            if sprout.offset == 1:
                tips.append(sprout)
            else:
                by_height.setdefault(sprout.offset, []).append(sprout)

        chosen: list[ChildPoint] = []
        rotations: list[float] = []
        old_rotate = 0.0
        for height in sorted(by_height):
            candidates = by_height[height]
            if p.rotate_mode == "rotate":
                if p.rotate[level] < 0.0:
                    old_rotate = -copysign(p.rotate[level], old_rotate)
                else:
                    old_rotate += p.rotate[level]
                rotate = old_rotate + rng.uniform(-p.rotate_v[level], p.rotate_v[level])

                # the candidate whose angle around the trunk is closest to the rotate angle
                target = rotate % Angles.TAU
                distances = []
                for candidate in candidates:
                    angle = atan2(candidate.co[0], -candidate.co[1])
                    distances.append(
                        min((target - angle + Angles.TAU) % Angles.TAU, (angle - target + Angles.TAU) % Angles.TAU)
                    )
                best = candidates[distances.index(min(distances))]

                # the growth angle that makes the branch point in the rotate direction
                co = best.co
                aim = Vector((sin(rotate), cos(rotate)))
                trunk_distance = (co[0] * co[0] + co[1] * co[1]) ** 0.5
                reach = (
                    best.length_parent
                    * p.length[1]
                    * CrownShape.ratio(p.shape, (1 - best.offset) / (1 - base_size), custom=p.custom_shape)
                )
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
                chosen.append(best)
                rotations.append(atan2(to_target[0], to_target[1]))
            else:
                chosen.append(candidates[rng.randint(0, len(candidates) - 1)])

        chosen.extend(tips)
        rotations.extend([0] * len(tips))
        return chosen, rotations
