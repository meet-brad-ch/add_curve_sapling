# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves and blossoms: blossoms (the requirements each class or test names)."""

import math
import unittest
import unittest.mock

import bpy
import numpy as np
from support.addon import Addon
from support.foliage import Foliage
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0084")
class BlossomPositions(unittest.TestCase):
    """Blossom Rate picks that share of the leaf positions for blossoms, in trees grown in the model alone.
    A higher rate keeps each blossom of a lower rate, and each blossom has its size and place."""

    def test_rate_zero_draws_nothing(self):
        randomness = Addon.module("model.randomness")
        original = randomness.KeyedRandom.uniform
        seen = set()

        def spy(keys, step, draw):
            seen.add(draw)
            return original(keys, step, draw)

        with unittest.mock.patch.object(randomness.KeyedRandom, "uniform", side_effect=spy):
            self.assertIsNone(Foliage.grow(blossomRate=0.0).blossoms)
            self.assertNotIn(randomness.Draw.BLOSSOM, seen)
            Foliage.grow(blossomRate=0.5)
        self.assertIn(randomness.Draw.BLOSSOM, seen)

    def test_rate_one_grows_only_blossoms(self):
        everything = Foliage.grow(blossomRate=1.0)
        self.assertEqual(everything.leaves.count, 0)
        self.assertEqual(everything.blossoms.count, Foliage.grow().leaves.count)

    def test_fraction_follows_the_rate(self):
        result = Foliage.grow(blossomRate=0.3)
        total = result.leaves.count + result.blossoms.count
        spread = 4 * math.sqrt(total * 0.3 * 0.7)
        self.assertLess(abs(result.blossoms.count - 0.3 * total), spread)

    def test_a_higher_rate_keeps_every_blossom(self):
        low = set(map(bytes, Foliage.grow(blossomRate=0.3).blossoms.sprout_co))
        high = set(map(bytes, Foliage.grow(blossomRate=0.6).blossoms.sprout_co))
        self.assertTrue(low < high)

    def test_leaves_and_blossoms_share_the_positions(self):
        plain = Foliage.grow().leaves
        mixed = Foliage.grow(blossomRate=0.4)
        together = np.concatenate([mixed.leaves.sprout_co, mixed.blossoms.sprout_co])
        self.assertEqual(sorted(map(bytes, together)), sorted(map(bytes, plain.sprout_co)))
        self.assertTrue(
            set(Foliage.blocks(mixed.leaves)) <= set(Foliage.blocks(plain)), "the leaves left are unchanged"
        )

    def test_blossom_size_and_place(self):
        shapes = Foliage.blossoms_module().BlossomShape
        scale = 0.3
        result = Foliage.grow(blossomRate=1.0, blossomScale=scale)
        blossoms = result.blossoms
        flowers = blossoms.vertices.reshape(blossoms.count, -1, 3).astype(np.float64)
        np.testing.assert_array_equal(flowers[:, 0], blossoms.sprout_co)
        reach = np.linalg.norm(flowers - flowers[:, :1], axis=2).max(axis=1)
        expected = scale * math.hypot(0.5, shapes.FORMS[shapes.CHERRY].cup)
        np.testing.assert_allclose(reach, expected, rtol=1e-5)


@Verifies("SWR-0084")
class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        """Generate a quaking aspen (2 levels, leaves, blossom rate 0.5, the changes) and return its blossoms object."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_no_leaves_object_at_rate_one(self):
        self.generate(blossomRate=1.0)
        self.assertNotIn("leaves", bpy.data.objects)
