# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: setting errors (the requirements each class or test names)."""

import unittest
import unittest.mock

import bpy
import numpy as np
from support.addon import Addon
from support.model import Model
from support.scene import Scene
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


@Verifies("SWR-0076")
class TreeSizeAboveZero(unittest.TestCase):
    """A Scale minus Scale Variation of 0 refuses the tree with both settings named, and a size above 0 generates."""

    def settings(self, scale, variation):
        """Quaking aspen settings with the Scale and the Scale Variation."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(scale=scale, scaleV=variation)
        return settings

    def test_a_size_range_reaching_zero_is_refused(self):
        Scene.reset()
        with self.assertRaisesRegex(RuntimeError, "Scale 1 minus Scale Variation 1 is 0"):
            Scene.generate(self.settings(1.0, 1.0))
        self.assertEqual(len(bpy.data.objects), 0)

    def test_a_size_range_above_zero_generates(self):
        self.assertEqual(Scene.generate(self.settings(1.0, 0.5)), {"FINISHED"})


@Verifies("SWR-0077")
class PruningEnvelopeHeight(unittest.TestCase):
    """Prune with Prune Base Height and Trunk Height at 1 refuses the tree, and the scene stays empty."""

    def test_an_envelope_without_height_is_refused(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(prune=True, pruneBase=1.0, baseSize=1.0)
        Scene.reset()
        with self.assertRaisesRegex(RuntimeError, "Prune Base Height 1 and Trunk Height 1"):
            Scene.generate(settings)
        self.assertEqual(len(bpy.data.objects), 0)


@Verifies("SWR-0125")
class FlutterSpeedAboveZero(unittest.TestCase):
    """A Flutter Speed of 0 refuses the tree with Leaf Flutter on, and does not block it with Leaf Flutter off."""

    def settings(self, flutter):
        """Quaking aspen settings with leaves, wind, a Flutter Speed of 0 and Leaf Flutter on or off."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, windAnim=True, leafFlutter=flutter, flutterSpeed=0.0)
        return settings

    def test_a_flutter_speed_of_zero_is_refused(self):
        Scene.reset()
        with self.assertRaisesRegex(RuntimeError, "Flutter Speed 0"):
            Scene.generate(self.settings(flutter=True))
        self.assertEqual(len(bpy.data.objects), 0)

    def test_an_unused_speed_does_not_block(self):
        self.assertEqual(Scene.generate(self.settings(flutter=False)), {"FINISHED"})
