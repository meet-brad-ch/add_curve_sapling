# SPDX-License-Identifier: GPL-3.0-or-later

"""The shaping wind: Wind Shear cuts the pruning envelope back on the windward side, Wind Bend turns the branches
downwind, Wind Direction says where downwind is (0: toward -Y, 90: toward +X). A coast tree's one-sided crown."""

import unittest

import helpers
import numpy as np


def crown_points(settings: dict) -> np.ndarray:
    """Every point of the tree's branches (all splines but the first, the trunk), as (x, y, z)."""
    helpers.generate(settings)
    splines = helpers.spline_points()
    return np.array([point for spline in splines[1:] for point, _radius in spline])


class WindShape(unittest.TestCase):
    """A pruned tree grown still, sheared and bent."""

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("black_oak.py")
        settings.update(levels=3, prune=True, pruneWidth=0.5, pruneRatio=1.0, seed=3)
        cls.base = settings
        cls.still = crown_points(settings)

    def grown(self, **wind) -> np.ndarray:
        settings = dict(self.base)
        settings.update(wind)
        return crown_points(settings)

    def test_a_direction_without_strength_changes_nothing(self):
        turned = self.grown(windDir=137.0)
        np.testing.assert_array_equal(turned, self.still)

    def test_the_shear_moves_the_crown_downwind(self):
        sheared = self.grown(windDir=0.0, windShear=0.6)
        # downwind is -Y: the crown reaches less far windward (+Y) and at least as far downwind (-Y); its reach, not
        # its mean, is what the envelope cuts (the inner points stay where they are)
        self.assertLess(sheared[:, 1].max(), 0.8 * self.still[:, 1].max())
        self.assertLessEqual(sheared[:, 1].min(), self.still[:, 1].min())

    def test_the_bend_turns_the_branches_downwind(self):
        bent = self.grown(windDir=90.0, windBend=[0.0, 0.6, 0.6, 0.0])
        spread = np.ptp(self.still[:, 0])
        # downwind is +X
        self.assertGreater(bent[:, 0].mean(), self.still[:, 0].mean() + 0.05 * spread)


if __name__ == "__main__":
    unittest.main()
