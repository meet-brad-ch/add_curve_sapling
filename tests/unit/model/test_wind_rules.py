# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: the wind's explicit rules for a removed stem and for a joint's radius."""

import random
import unittest

import numpy as np
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


class ParentCycles(unittest.TestCase):
    """The loops over parent links are bounded: a cycle raises instead of hanging."""

    def joints(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(windAnim=True)
        model = Model.grow(settings)
        return Model.joints(settings, model)

    def test_a_cycle_in_the_depths_raises(self):
        joints = self.joints()
        joints.link_spline[0] = 1
        joints.link_spline[1] = 0
        with self.assertRaisesRegex(RuntimeError, "form a cycle"):
            joints.depths()

    def test_a_cycle_in_the_joint_search_raises(self):
        joints = self.joints()
        # two curves without joints that hang from each other: the climb never reaches a curve with joints
        joints.eligible[1] = False
        joints.eligible[2] = False
        joints.link_spline[1] = 2
        joints.link_spline[2] = 1
        with self.assertRaisesRegex(RuntimeError, "form a cycle"):
            joints.nearest_joint(np.array([1]), np.array([0]))
