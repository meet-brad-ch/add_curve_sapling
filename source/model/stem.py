# SPDX-License-Identifier: GPL-3.0-or-later

"""Stems, sprout points and the map from splines to the bones they hang from."""

from dataclasses import dataclass


class BoneName:
    """Branch bones are named bone<spline>.<point>: the spline and point index where they start."""

    @staticmethod
    def of(spline_index, point_index):
        return "bone" + str(spline_index).rjust(3, "0") + "." + str(point_index).rjust(3, "0")

    @staticmethod
    def rounded(bone, step):
        """Round the point index down to a multiple of step (armature simplification)."""
        point = int(int(bone[-3:]) / step) * step
        return bone[:-3] + str(point).rjust(3, "0")

    @staticmethod
    def spline(bone):
        """Spline index of a bone name."""
        return int(bone[4:-4])


class Stem:
    """A stem (or a split of it) that is being grown, with the parameters it grows with."""

    def __init__(
        self,
        spline,
        curvature,
        curvature_v,
        attract_up,
        segment,
        segments,
        segment_length,
        children,
        radius_start,
        radius_end,
        index,
        offset_length,
        parent_quat,
    ):
        self.spline = spline
        self.point = spline.bezier_points[-1]
        self.curvature = curvature
        self.curvature_v = curvature_v
        self.attract_up = attract_up
        self.segment = segment
        self.segments = segments
        self.segment_length = segment_length
        self.children = children
        self.radius_start = radius_start
        self.radius_end = radius_end
        self.index = index
        self.offset_length = offset_length
        self.parent_quat = parent_quat
        self.curve_sign_x = 1
        self.curve_sign_y = 1
        self.split_last = 0
        # None until the first split, which then draws a random start rotation
        self.last_rotation = None

    def quat(self):
        """Direction of the end of the stem."""
        points = self.spline.bezier_points
        if len(points) == 1:
            return ((points[-1].handle_right - points[-1].co).normalized()).to_track_quat("Z", "Y")
        return ((points[-1].co - points[-2].co).normalized()).to_track_quat("Z", "Y")

    def update_end(self):
        """The newly added point becomes the end of the stem."""
        self.point = self.spline.bezier_points[-1]
        self.segment += 1


class ChildPoint:
    """A point on a stem where a child stem or a leaf sprouts."""

    __slots__ = ("co", "length_parent", "offset", "parent_bone", "quat", "radius_parent", "stem_offset")

    def __init__(self, co, quat, radius_parent, offset, stem_offset, length_parent, parent_bone):
        self.co = co
        self.quat = quat
        self.radius_parent = radius_parent
        self.offset = offset
        self.stem_offset = stem_offset
        self.length_parent = length_parent
        self.parent_bone = parent_bone


@dataclass(frozen=True, slots=True)
class BoneLink:
    """Where a spline hangs in the armature.

    bone: the parent bone of the spline's first bone ("" for the trunk).
    is_end: the spline continues its parent from the parent's tip.
    is_split: the spline is a split of its parent at parent point split_point.
    """

    bone: str
    is_end: bool = False
    is_split: bool = False
    split_point: int = 0


class BoneMap:
    """One BoneLink per curve spline, in spline order."""

    def __init__(self):
        self._links = [BoneLink("")]

    def __len__(self):
        return len(self._links)

    def __getitem__(self, index):
        return self._links[index]

    def __iter__(self):
        return iter(self._links)

    def add_stem(self, bone, is_end):
        self._links.append(BoneLink(bone, is_end))

    def add_split(self, bone, split_point):
        self._links.append(BoneLink(bone, False, True, split_point))

    def snapshot(self):
        return list(self._links)

    def restore(self, snapshot):
        self._links[:] = snapshot

    def bones(self):
        return [link.bone for link in self._links]
