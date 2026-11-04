# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: handle type, branch rings, custom shape and the down-angle rules (the requirements each class names)."""

import unittest

import numpy as np
from support.addon import Addon
from support.model import Model
from support.verifies import Verifies


class FirstLevel:
    """The first-level branches of a two-level Quaking Aspen, grown in the model."""

    STRAIGHT = {
        "levels": 2,
        "curve": (0.0, 0.0, 0.0, 0.0),
        "curveV": (0.0, 0.0, 0.0, 0.0),
        "curveBack": (0.0, 0.0, 0.0, 0.0),
        "bendV": (0.0, 0.0, 0.0, 0.0),
        "attractUp": (0.0, 0.0, 0.0, 0.0),
        "attractOut": (0.0, 0.0, 0.0, 0.0),
        "segSplits": (0.0, 0.0, 0.0, 0.0),
        "baseSplits": 0,
        "downAngleV": (0.0, 0.0, 0.0, 0.0),
        "rotateV": (0.0, 0.0, 0.0, 0.0),
        "lengthV": (0.0, 0.0, 0.0, 0.0),
        "prune": False,
    }

    @staticmethod
    def grow(**changes):
        """The model of a straight two-level Quaking Aspen with the changes."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(FirstLevel.STRAIGHT)
        settings.update(changes)
        return Model.grow(settings)

    @staticmethod
    def splines(model) -> list[int]:
        """The spline indices of the first-level branches: the first level without the stem that continues the
        trunk's tip (it starts at the trunk's last point)."""
        ends = model.grown.level_ends
        flat = model.curve.flatten()
        trunk_end = flat.co[int(flat.start[1]) - 1]
        out = []
        for spline in range(ends[0], ends[1]):
            start = flat.co[int(flat.start[spline])]
            if float(np.linalg.norm(start - trunk_end)) > 1e-4:
                out.append(spline)
        return out

    @staticmethod
    def angles_from_vertical(model) -> np.ndarray:
        """Each first-level branch's first segment, as its angle from the vertical in degrees."""
        flat = model.curve.flatten()
        angles = []
        for spline in FirstLevel.splines(model):
            start = int(flat.start[spline])
            direction = flat.co[start + 1] - flat.co[start]
            cosine = direction[2] / np.linalg.norm(direction)
            angles.append(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))
        return np.array(angles)

    @staticmethod
    def start_heights(model) -> np.ndarray:
        """Each first-level branch's start height."""
        flat = model.curve.flatten()
        starts = [int(flat.start[spline]) for spline in FirstLevel.splines(model)]
        return flat.co[starts][:, 2].astype(np.float64)

    @staticmethod
    def lengths(model) -> np.ndarray:
        """Each first-level branch's length along its points."""
        flat = model.curve.flatten()
        out = []
        for spline in FirstLevel.splines(model):
            start = int(flat.start[spline])
            points = flat.co[start : start + int(flat.sizes[spline])].astype(np.float64)
            out.append(float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()))
        return np.array(out)


@Verifies("SWR-0165")
class HandleTypes(unittest.TestCase):
    """Handle Type gives the points of the grown stems automatic or vector handles; a stem's first point, where it
    joins its parent, has vector handles."""

    def test_each_point_has_the_selected_handles(self):
        handle = Addon.module("model.curve_data").HandleType
        for setting, expected in (("0", handle.AUTO), ("1", handle.VECTOR)):
            with self.subTest(handleType=setting):
                flat = FirstLevel.grow(handleType=setting).curve.flatten()
                first = flat.start[:-1]
                later = np.delete(np.arange(len(flat.h1)), first)
                kinds = set(flat.h1[later].tolist()) | set(flat.h2[later].tolist())
                self.assertEqual(kinds, {int(expected)})
                starts = set(flat.h1[first].tolist()) | set(flat.h2[first].tolist())
                self.assertEqual(starts, {int(handle.VECTOR)})


@Verifies("SWR-0166")
class BranchRings(unittest.TestCase):
    """Branch Rings start the branches of a stem at that number of heights at most."""

    def test_the_branches_start_in_rings(self):
        for rings in (3, 4):
            with self.subTest(rings=rings):
                model = FirstLevel.grow(nrings=rings)
                heights = np.sort(FirstLevel.start_heights(model))
                flat = model.curve.flatten()
                trunk_top = float(flat.co[int(flat.start[1]) - 1][2])
                groups = int((np.diff(heights) > 0.03 * trunk_top).sum()) + 1
                self.assertGreater(len(heights), rings)
                self.assertLessEqual(groups, rings)

    def test_without_rings_the_branches_spread(self):
        heights = np.sort(FirstLevel.start_heights(FirstLevel.grow(nrings=0)))
        self.assertEqual(len(np.unique(np.round(heights, 4))), len(heights), "every branch at its own height")


@Verifies("SWR-0167")
class CustomShape(unittest.TestCase):
    """The Custom Shape values set the first-level branch lengths along the trunk."""

    def test_a_flat_profile_gives_one_length(self):
        lengths = FirstLevel.lengths(FirstLevel.grow(shape="8", customShape=(1.0, 1.0, 0.5, 1.0)))
        self.assertLess((lengths.max() - lengths.min()) / lengths.max(), 0.01)

    def test_a_short_base_gives_a_short_lowest_branch(self):
        model = FirstLevel.grow(shape="8", customShape=(0.1, 1.0, 0.5, 0.1))
        lengths = FirstLevel.lengths(model)
        lowest = int(np.argmin(FirstLevel.start_heights(model)))
        self.assertLess(lengths[lowest], 0.5 * lengths.max())


@Verifies("SWR-0168")
class ParentAngle(unittest.TestCase):
    """In Rotate mode, without Use Parent Angle the first-level down angle is measured from the vertical."""

    CURVED = {"rMode": "rotate", "curve": (40.0, 0.0, 0.0, 0.0), "downAngle": (0.0, 60.0, 45.0, 45.0)}

    def test_off_measures_from_the_vertical(self):
        angles = FirstLevel.angles_from_vertical(FirstLevel.grow(useParentAngle=False, **self.CURVED))
        self.assertLess(float(np.abs(angles - 60.0).max()), 0.5)

    def test_on_follows_the_trunk(self):
        angles = FirstLevel.angles_from_vertical(FirstLevel.grow(useParentAngle=True, **self.CURVED))
        self.assertGreater(float(np.abs(angles - 60.0).max()), 2.0)


@Verifies("SWR-0169")
class OldDownAngleVariation(unittest.TestCase):
    """With Use Old Down Angle Variation, a negative variation follows the branch height, not a random draw."""

    VARIED = {"downAngle": (0.0, 60.0, 45.0, 45.0), "downAngleV": (0.0, -30.0, 0.0, 0.0)}

    def correlation(self, old: bool) -> float:
        """The correlation of the first-level branches' start height and down angle."""
        model = FirstLevel.grow(useOldDownAngle=old, **self.VARIED)
        heights = FirstLevel.start_heights(model)
        angles = FirstLevel.angles_from_vertical(model)
        return float(np.corrcoef(heights, angles)[0, 1])

    def test_on_follows_the_height(self):
        self.assertLess(self.correlation(old=True), -0.99)

    def test_off_is_random(self):
        self.assertLess(abs(self.correlation(old=False)), 0.6)
