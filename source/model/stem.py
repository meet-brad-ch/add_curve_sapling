# SPDX-License-Identifier: GPL-3.0-or-later

"""Bone names and the map from splines to the bones they hang from."""

from collections.abc import Iterator
from dataclasses import dataclass


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

    @staticmethod
    def point(bone: str) -> int:
        """Point index of a bone name."""
        return int(bone[-3:])


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

    def __init__(self, links: list[BoneLink]) -> None:
        if not links or links[0].bone:
            raise ValueError("the first spline must be a trunk")
        self._links = list(links)

    @classmethod
    def from_links(cls, links: list[BoneLink]) -> "BoneMap":
        """A map of the given links, in spline order (the first must be a trunk's)."""
        return cls(links)

    def __len__(self) -> int:
        return len(self._links)

    def __getitem__(self, index: int) -> BoneLink:
        return self._links[index]

    def __iter__(self) -> Iterator[BoneLink]:
        return iter(self._links)

    def bones(self) -> list[str]:
        """Parent bone name of every spline, in spline order ("" for the trunk)."""
        return [link.bone for link in self._links]
