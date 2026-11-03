# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: the wind's explicit rules for a removed stem and for a joint's radius."""

import random
import unittest

from support.addon import Addon
from support.model import Model


class RemovedStemWind(unittest.TestCase):
    """A stem that pruning removed has length 0: no wave, also with a loop (no fallback frequency)."""

    FPS = 24.0

    def wind_model(self, **changes):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(windAnim=True, **changes)
        params = Model.params(settings)
        wind = Model.wind_params(settings, params)
        return Addon.module("model.wind_model").WindModel(wind, self.FPS)

    def test_no_wave_for_a_removed_stem(self):
        frequencies = self.wind_model().branch_frequencies(0.0)
        self.assertEqual((frequencies.first, frequencies.second), (0.0, 0.0))

    def test_no_wave_also_with_a_loop(self):
        frequencies = self.wind_model(loopFrames=48).branch_frequencies(0.0)
        self.assertEqual((frequencies.first, frequencies.second), (0.0, 0.0))


class JointRadius(unittest.TestCase):
    def test_a_joint_of_radius_zero_is_a_model_defect(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(windAnim=True)
        model = Model.grow(settings)
        joints = Model.joints(settings, model)
        joints.flat.radius[joints.joint_point[0]] = 0.0
        wind_model = Addon.module("model.wind_model").WindModel(joints.params, 24.0)
        with self.assertRaisesRegex(RuntimeError, "joint 0 has radius 0"):
            joints.sway(wind_model, random.Random(0))
