# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: setting errors (the requirements each class or test names)."""

import unittest
import unittest.mock

import numpy as np
from support.addon import Addon
from support.model import Model
from support.verifies import Verifies


@Verifies("SWR-0067")
class ExplicitChoices(unittest.TestCase):
    """Enum settings a script or preset gives with an unknown value are errors, never a silent other choice."""

    def test_unknown_handle_type(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(handleType="7")
        with self.assertRaisesRegex(ValueError, r"Handle Type '7' is not one of \['0', '1'\]"):
            Model.params(settings)

    def test_unknown_branching_mode(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(rMode="spiral")
        with self.assertRaisesRegex(ValueError, "Branching Mode 'spiral' is not one of"):
            Model.params(settings)

    def test_custom_shape_needs_its_values(self):
        geometry = Addon.module("model.geometry")
        with self.assertRaisesRegex(ValueError, "Custom Shape needs its four values"):
            geometry.CrownShape.ratios(geometry.CrownShape.CUSTOM, np.array([0.5]))
