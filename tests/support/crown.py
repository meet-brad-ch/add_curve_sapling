# SPDX-License-Identifier: GPL-3.0-or-later

"""The branches of the generated tree as points: the crown, the sprays."""

import numpy as np

from support.evaluated import Evaluated
from support.model import Model
from support.scene import Scene


class Crown:
    """The branches of the generated tree as points: the crown, the sprays."""

    @staticmethod
    def points(settings: dict) -> np.ndarray:
        """Every point of the tree's branches (all splines but the first, the trunk), as (x, y, z)."""
        Scene.generate(settings)
        splines = Evaluated.spline_points()
        return np.array([point for spline in splines[1:] for point, _radius in spline])

    @staticmethod
    def spray_starts(settings: dict) -> np.ndarray:
        """The first point of every third-level stem (the sprays on the limbs), as (x, y, z)."""
        model = Model.grow(settings)
        ends = model.grown.level_ends
        Scene.generate(settings)
        splines = Evaluated.spline_points()
        return np.array([spline[0][0] for spline in splines[ends[1] : ends[2]]])
