# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaf Face Up: each leaf's face turned toward the sky by a share, after every other turn; at 1 the leaves lie
flat, as a Monterey cypress's foliage pads do."""

import unittest

import bpy
import helpers
import numpy as np


def leaf_normals(settings: dict) -> np.ndarray:
    """The unit face normal of every leaf of the generated tree."""
    helpers.generate(settings)
    mesh = bpy.data.objects["leaves"].data
    normals = np.zeros(len(mesh.polygons) * 3)
    mesh.polygons.foreach_get("normal", normals)
    return normals.reshape(-1, 3)


class LeafUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("cambridge_oak.py")
        settings.update(levels=3, seed=5, leafShape="rect", leaves=12, showLeaves=True)
        cls.base = settings

    def test_one_lays_every_leaf_flat(self):
        normals = leaf_normals(dict(self.base, leafUp=1.0))
        self.assertGreater(len(normals), 100)
        np.testing.assert_allclose(np.abs(normals[:, 2]), 1.0, atol=1e-5)

    def test_half_turns_every_leaf_halfway(self):
        tilted = leaf_normals(dict(self.base, leafUp=0.0))
        half = leaf_normals(dict(self.base, leafUp=0.5))
        before = np.degrees(np.arccos(np.clip(np.abs(tilted[:, 2]), 0.0, 1.0)))
        after = np.degrees(np.arccos(np.clip(np.abs(half[:, 2]), 0.0, 1.0)))
        # the mesh's normals are float32: near vertical, arccos magnifies their error to about 0.01 degrees
        np.testing.assert_allclose(after, before / 2.0, atol=0.02)

    def test_variation_tilts_each_leaf_within_its_range(self):
        normals = leaf_normals(dict(self.base, leafUp=1.0, leafUpV=10.0))
        tilt = np.degrees(np.arccos(np.clip(np.abs(normals[:, 2]), 0.0, 1.0)))
        # every leaf within 10 degrees of horizontal (float32 normals: 0.02), and spread over the range, not flat
        self.assertLessEqual(tilt.max(), 10.02)
        self.assertGreater(tilt.max(), 8.0)
        self.assertGreater(np.median(tilt), 3.0)


if __name__ == "__main__":
    unittest.main()
