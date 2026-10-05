# SPDX-License-Identifier: GPL-3.0-or-later

"""Bone names and the map from splines to the bones they hang from."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass


class BoneName:
    """Branch bones are named bone<spline>.<point>: the spline and point index where they start."""

    PREFIX = "bone"
    DIGITS = 3

    @classmethod
    def of(cls, spline_index: int, point_index: int) -> str:
        """Name of the bone that starts at point `point_index` of spline `spline_index` (bone007.012)."""
        return cls.PREFIX + str(spline_index).rjust(cls.DIGITS, "0") + "." + str(point_index).rjust(cls.DIGITS, "0")

    @classmethod
    def names(cls, splines: Sequence[int], points: Sequence[int]) -> list[str]:
        """The bone names of (spline, point) pairs, in order."""
        return [cls.of(spline, point) for spline, point in zip(splines, points, strict=True)]

    @classmethod
    def rounded(cls, bone: str, step: int) -> str:
        """Round the point index down to a multiple of step (Joint Length: one bone per step segments)."""
        point = (cls.point(bone) // step) * step
        return bone[: -cls.DIGITS] + str(point).rjust(cls.DIGITS, "0")

    @classmethod
    def spline(cls, bone: str) -> int:
        """Spline index of a bone name."""
        return int(bone[len(cls.PREFIX) : -(cls.DIGITS + 1)])

    @classmethod
    def point(cls, bone: str) -> int:
        """Point index of a bone name."""
        return int(bone[-cls.DIGITS :])


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
    """One BoneLink per curve spline, in spline order (the first must be a trunk's)."""

    def __init__(self, links: list[BoneLink]) -> None:
        if not links or links[0].bone:
            raise ValueError("the first spline must be a trunk")
        self._links = list(links)

    def __len__(self) -> int:
        return len(self._links)

    def __getitem__(self, index: int) -> BoneLink:
        return self._links[index]

    def __iter__(self) -> Iterator[BoneLink]:
        return iter(self._links)

    def bones(self) -> list[str]:
        """Parent bone name of every spline, in spline order ("" for the trunk)."""
        return [link.bone for link in self._links]
