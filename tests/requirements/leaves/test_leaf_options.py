# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves: Horizontal Leaves and Leaf Angle (the requirements each class names)."""

import unittest

import numpy as np
from support.addon import Addon
from support.foliage import Foliage
from support.model import Model
from support.verifies import Verifies


class LeafNormals:
    """One normal per leaf of a Quaking Aspen with leaves, and the stem each leaf grows on."""

    BASE = {"showLeaves": True, "leafRotate": 137.5, "leafRotateV": 0.0, "leafUp": 0.0, "leafangle": 0.0}

    @staticmethod
    def settings(**changes) -> dict:
        """The Quaking Aspen with leaves and the changes."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(LeafNormals.BASE)
        settings.update(changes)
        return settings

    @staticmethod
    def per_leaf(settings: dict) -> np.ndarray:
        """One unit normal per leaf (a hexagonal leaf has two faces in one plane: the first one's normal)."""
        normals = Foliage.normals(settings)
        leaves = len(Model.grow(settings).grown.sprouts.parent_spline)
        if len(normals) % leaves != 0:
            raise AssertionError(f"{len(normals)} leaf faces for {leaves} leaves")
        return normals.reshape(leaves, -1, 3)[:, 0]


@Verifies("SWR-0170")
class HorizontalLeaves(unittest.TestCase):
    """Horizontal Leaves turn the leaves of a stem to one side of it."""

    @staticmethod
    def one_sidedness(horizontal: bool) -> float:
        """The mean, over stems with 3 or more leaves, of the mean resultant length of the leaf normals' horizontal
        directions (1: every leaf of the stem faces one way, 0: they face all around)."""
        settings = LeafNormals.settings(horzLeaves=horizontal)
        parents = Model.grow(settings).grown.sprouts.parent_spline
        normals = LeafNormals.per_leaf(settings)
        lengths = []
        for stem in np.unique(parents):
            mine = normals[parents == stem]
            if len(mine) < 3:
                continue
            azimuth = np.arctan2(mine[:, 1], mine[:, 0])
            lengths.append(float(np.hypot(np.cos(azimuth).mean(), np.sin(azimuth).mean())))
        return float(np.mean(lengths))

    def test_on_turns_the_leaves_to_one_side(self):
        self.assertGreaterEqual(self.one_sidedness(horizontal=True), 0.6)

    def test_off_leaves_face_around_the_stem(self):
        self.assertLessEqual(self.one_sidedness(horizontal=False), 0.5)


@Verifies("SWR-0171")
class LeafAngle(unittest.TestCase):
    """Leaf Angle turns every leaf blade by its value."""

    def test_each_blade_turns_by_the_angle(self):
        flat = LeafNormals.per_leaf(LeafNormals.settings(leafangle=0.0))
        tilted = LeafNormals.per_leaf(LeafNormals.settings(leafangle=30.0))
        cosine = np.clip((flat * tilted).sum(axis=1), -1.0, 1.0)
        turns = np.degrees(np.arccos(cosine))
        self.assertLess(float(np.abs(turns - 30.0).max()), 0.01)
