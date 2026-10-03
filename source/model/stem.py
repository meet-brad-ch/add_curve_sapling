# SPDX-License-Identifier: GPL-3.0-or-later

"""Stems, sprout points and the map from splines to the bones they hang from."""

from collections.abc import Iterator
from dataclasses import dataclass

from mathutils import Quaternion, Vector

from .curve_data import CurveSpline


class BoneName:
    """Branch bones are named bone<spline>.<point>: the spline and point index where they start."""

    PREFIX = "bone"

    @classmethod
    def of(cls, spline_index: int, point_index: int) -> str:
        """Name of the bone that starts at point `point_index` of spline `spline_index` (bone007.012)."""
        return cls.PREFIX + str(spline_index).rjust(3, "0") + "." + str(point_index).rjust(3, "0")

    @staticmethod
    def rounded(bone: str, step: int) -> str:
        """Round the point index down to a multiple of step (armature simplification)."""
        point = int(int(bone[-3:]) / step) * step
        return bone[:-3] + str(point).rjust(3, "0")

    @staticmethod
    def spline(bone: str) -> int:
        """Spline index of a bone name."""
        return int(bone[4:-4])


class Stem:
    """A stem (or a split of it) that is being grown, with the parameters it grows with."""

    def __init__(
        self,
        spline: CurveSpline,
        curvature: float,
        curvature_v: float,
        attract_up: float,
        segment: int,
        segments: int,
        segment_length: float,
        children: float,
        radius_start: float,
        radius_end: float,
        index: int,
        offset_length: float,
    ) -> None:
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
        # Curvature variation alternates its sign from segment to segment
        self.curve_sign = 1
        self.split_last = 0
        # None until the first split, which then draws a random start rotation
        self.last_rotation: float | None = None
        # Turns the plane the stem curves in about its own axis (each trunk of a clump curves its own way)
        self.roll = 0.0

    def quat(self) -> Quaternion:
        """Direction of the end of the stem."""
        points = self.spline.bezier_points
        if len(points) == 1:
            return ((points[-1].handle_right - points[-1].co).normalized()).to_track_quat("Z", "Y")
        return ((points[-1].co - points[-2].co).normalized()).to_track_quat("Z", "Y")

    def radius_at(self, segment: int) -> float:
        """Radius at a segment boundary, tapering from the start radius to the end radius."""
        return self.radius_start * (1 - segment / self.segments) + self.radius_end * (segment / self.segments)

    def update_end(self) -> None:
        """The newly added point becomes the end of the stem."""
        self.point = self.spline.bezier_points[-1]
        self.segment += 1


class ChildPoint:
    """A point on a stem where a child stem or a leaf sprouts."""

    __slots__ = ("co", "length_parent", "offset", "parent_bone", "quat", "radius_parent", "stem_offset")

    def __init__(
        self,
        co: Vector,
        quat: Quaternion,
        radius_parent: tuple[float, float],
        offset: float,
        stem_offset: float,
        length_parent: float,
        parent_bone: str,
    ) -> None:
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

    def __init__(self) -> None:
        self._links = [BoneLink("")]

    def __len__(self) -> int:
        return len(self._links)

    def __getitem__(self, index: int) -> BoneLink:
        return self._links[index]

    def __iter__(self) -> Iterator[BoneLink]:
        return iter(self._links)

    def add_stem(self, bone: str, is_end: bool) -> None:
        """Link the next spline, a new child stem, to its parent bone; `is_end` when it continues the parent's tip."""
        self._links.append(BoneLink(bone, is_end))

    def add_trunk(self) -> None:
        """Link the next spline, another trunk of the clump: like the first trunk, it hangs from no bone."""
        self._links.append(BoneLink(""))

    def trunk_of(self, index: int) -> int:
        """The spline index of the trunk that spline `index` grows from (through its parents and splits)."""
        while self._links[index].bone:
            index = BoneName.spline(self._links[index].bone)
        return index

    def add_split(self, bone: str, split_point: int) -> None:
        """Link the next spline, a split of its parent at parent point `split_point`."""
        self._links.append(BoneLink(bone, False, True, split_point))

    def next_index(self) -> int:
        """Index of the next tree spline: there is one link per spline (len(curve.splines) is O(n))."""
        return len(self._links)

    def snapshot(self) -> list[BoneLink]:
        """A copy of the links for restore(): the pruning search regrows a stem, and its splits, several times."""
        return list(self._links)

    def restore(self, snapshot: list[BoneLink]) -> None:
        """Roll the links back, in place, to a snapshot()."""
        self._links[:] = snapshot

    def bones(self) -> list[str]:
        """Parent bone name of every spline, in spline order ("" for the trunk)."""
        return [link.bone for link in self._links]
