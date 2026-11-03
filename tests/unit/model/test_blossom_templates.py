# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: blossom templates."""

import math
import unittest
import unittest.mock

import numpy as np
from support.addon import Addon
from support.foliage import Foliage
from support.model import Model


class BlossomTemplates(unittest.TestCase):
    """Each blossom template is a closed disc of unit diameter with petals that repeat around the centre and faces
    that look up. An unknown blossom shape is an error."""

    def template(self, shape):
        """The blossom template (vertices and faces) of the shape."""
        return Foliage.blossoms_module().BlossomShape.template(shape)

    def form(self, shape):
        """The blossom form (petal count, cup and other values) of the shape."""
        return Foliage.blossoms_module().BlossomShape.FORMS[shape]

    def test_counts(self):
        for shape in Foliage.blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                petals = self.form(shape).petals
                self.assertEqual(template.vertices.shape, (1 + 9 * petals, 3))
                self.assertEqual(template.faces.shape, (5 * petals, 4))
                self.assertEqual(set(np.unique(template.faces).tolist()), set(range(len(template.vertices))))

    def test_closed_disc_of_unit_diameter(self):
        for shape in Foliage.blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                self.assertAlmostEqual(np.hypot(template.vertices[:, 0], template.vertices[:, 1]).max(), 0.5)
                apart = [quad for quad in template.faces[::5].tolist() if 0 not in quad]
                self.assertEqual(apart, [], "every petal meets the centre")
                edges: dict[tuple[int, int], int] = {}
                for quad in template.faces.tolist():
                    for a, b in zip(quad, quad[1:] + quad[:1], strict=True):
                        edges[min(a, b), max(a, b)] = edges.get((min(a, b), max(a, b)), 0) + 1
                self.assertLessEqual(max(edges.values()), 2, "no edge is shared by more than two faces")

    def test_petals_repeat_around_the_centre(self):
        for shape in Foliage.blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                angle = 2 * math.pi / self.form(shape).petals
                turn = np.array(
                    [[math.cos(angle), -math.sin(angle), 0], [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
                )
                turned = template.vertices @ turn.T
                distance = np.linalg.norm(turned[:, None, :] - template.vertices[None, :, :], axis=2).min(axis=1)
                self.assertLess(distance.max(), 1e-9)

    def test_faces_look_up(self):
        for shape in Foliage.blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                v = template.vertices[template.faces]
                normals = np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 1])
                self.assertTrue((normals[:, 2] > 0).all())

    def test_cup_and_reflex(self):
        shapes = Foliage.blossoms_module().BlossomShape
        tips = {shape: self.template(shape).vertices[:, 2].max() for shape in [shapes.CHERRY, shapes.MAGNOLIA]}
        self.assertGreater(tips[shapes.CHERRY], 0)
        self.assertGreater(tips[shapes.MAGNOLIA], tips[shapes.CHERRY])
        self.assertLess(self.template(shapes.ORANGE).vertices[:, 2].min(), 0)

    def test_unknown_shapes(self):
        with self.assertRaisesRegex(ValueError, "unknown blossom shape rose"):
            self.template("rose")
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(blossomShape="rose")
        with self.assertRaisesRegex(ValueError, "Blossom Shape 'rose' is not one of"):
            Model.params(settings)
