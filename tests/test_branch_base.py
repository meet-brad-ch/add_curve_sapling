# SPDX-License-Identifier: GPL-3.0-or-later

"""Branch Base: a level's stems stay bare over that share of their length, so their children (or the last level's
leaves) grow only on the outer part: a Monterey cypress's foliage pads at its limb ends."""

import unittest

import helpers
import numpy as np


def spray_starts(settings: dict) -> np.ndarray:
    """The first point of every third-level stem (the sprays on the limbs), as (x, y, z)."""
    model = helpers.grow_model(settings)
    ends = model.grown.level_ends
    helpers.generate(settings)
    splines = helpers.spline_points()
    return np.array([spline[0][0] for spline in splines[ends[1] : ends[2]]])


class BranchBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("cambridge_oak.py")
        # no splits: every spline is one stem, starting where it sprouts (a split piece starts mid-stem)
        settings.update(levels=3, seed=5, prune=False, baseSplits=0, segSplits=[0.0, 0.0, 0.0, 0.0])
        cls.base = settings
        cls.plain = spray_starts(settings)

    def test_zero_changes_nothing(self):
        same = spray_starts(dict(self.base, branchBase=[0.0, 0.0, 0.0, 0.0]))
        np.testing.assert_array_equal(same, self.plain)

    def test_the_sprays_grow_on_the_limbs_outer_part(self):
        outer = spray_starts(dict(self.base, branchBase=[0.0, 0.6, 0.0, 0.0]))
        plain_reach = np.hypot(self.plain[:, 0], self.plain[:, 1])
        outer_reach = np.hypot(outer[:, 0], outer[:, 1])
        # the sprays start further out from the trunk: none on the limbs' bare inner 60 %
        self.assertGreater(np.percentile(outer_reach, 10), np.percentile(plain_reach, 10) * 1.5)


if __name__ == "__main__":
    unittest.main()
