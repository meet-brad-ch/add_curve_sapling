# SPDX-License-Identifier: GPL-3.0-or-later

"""Blossoms: some leaf positions grow a flower instead of a leaf (Blossom Rate, Shape and Scale)."""

import math
import random
import unittest
import unittest.mock

import bpy
import helpers
import numpy as np


def blossoms_module():
    return helpers.module("model.blossoms")


def foliage(**changes):
    """The leaves and blossoms of a quaking aspen with leaves, grown in the model alone."""
    settings = helpers.resolve_preset("quaking_aspen.py")
    settings.update(levels=2, showLeaves=True, **changes)
    params = helpers.model_params(settings)
    curve = helpers.module("model.curve_data").CurveData()
    rng = random.Random(params.seed)
    grown = helpers.module("model.tree").TreeGrower(params, rng).grow(curve, params.scale)
    return helpers.module("model.leaves").LeafGenerator(params, rng).generate(grown.sprouts)


def leaf_blocks(leaf_set):
    """Each leaf's vertices as one bytes value (for comparing sets of leaves)."""
    per_leaf = leaf_set.vertices.reshape(leaf_set.count, -1)
    return [row.tobytes() for row in per_leaf]


class BlossomTemplates(unittest.TestCase):
    def template(self, shape):
        return blossoms_module().BlossomShape.template(shape)

    def form(self, shape):
        return blossoms_module().BlossomShape.FORMS[shape]

    def test_counts(self):
        for shape in blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                petals = self.form(shape).petals
                self.assertEqual(template.vertices.shape, (1 + 9 * petals, 3))
                self.assertEqual(template.faces.shape, (5 * petals, 4))
                self.assertEqual(set(np.unique(template.faces).tolist()), set(range(len(template.vertices))))

    def test_closed_disc_of_unit_diameter(self):
        for shape in blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                self.assertAlmostEqual(np.hypot(template.vertices[:, 0], template.vertices[:, 1]).max(), 0.5)
                self.assertTrue(all(0 in quad for quad in template.faces[::5].tolist()), "every petal meets the centre")
                edges: dict[tuple[int, int], int] = {}
                for quad in template.faces.tolist():
                    for a, b in zip(quad, quad[1:] + quad[:1], strict=True):
                        edges[min(a, b), max(a, b)] = edges.get((min(a, b), max(a, b)), 0) + 1
                self.assertLessEqual(max(edges.values()), 2, "no edge is shared by more than two faces")

    def test_petals_repeat_around_the_centre(self):
        for shape in blossoms_module().BlossomShape.ALL:
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
        for shape in blossoms_module().BlossomShape.ALL:
            with self.subTest(shape=shape):
                template = self.template(shape)
                v = template.vertices[template.faces]
                normals = np.cross(v[:, 2] - v[:, 0], v[:, 3] - v[:, 1])
                self.assertTrue((normals[:, 2] > 0).all())

    def test_cup_and_reflex(self):
        shapes = blossoms_module().BlossomShape
        tips = {shape: self.template(shape).vertices[:, 2].max() for shape in [shapes.CHERRY, shapes.MAGNOLIA]}
        self.assertGreater(tips[shapes.CHERRY], 0)
        self.assertGreater(tips[shapes.MAGNOLIA], tips[shapes.CHERRY])
        self.assertLess(self.template(shapes.ORANGE).vertices[:, 2].min(), 0)

    def test_unknown_shapes(self):
        with self.assertRaisesRegex(ValueError, "unknown blossom shape rose"):
            self.template("rose")
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(blossomShape="rose")
        with self.assertRaisesRegex(ValueError, "Blossom Shape 'rose' is not one of"):
            helpers.model_params(settings)


class BlossomPositions(unittest.TestCase):
    def test_rate_zero_draws_nothing(self):
        randomness = helpers.module("model.randomness")
        original = randomness.KeyedRandom.uniform
        seen = set()

        def spy(keys, step, draw):
            seen.add(draw)
            return original(keys, step, draw)

        with unittest.mock.patch.object(randomness.KeyedRandom, "uniform", side_effect=spy):
            self.assertIsNone(foliage(blossomRate=0.0).blossoms)
            self.assertNotIn(randomness.Draw.BLOSSOM, seen)
            foliage(blossomRate=0.5)
        self.assertIn(randomness.Draw.BLOSSOM, seen)

    def test_rate_one_grows_only_blossoms(self):
        everything = foliage(blossomRate=1.0)
        self.assertEqual(everything.leaves.count, 0)
        self.assertEqual(everything.blossoms.count, foliage().leaves.count)

    def test_fraction_follows_the_rate(self):
        result = foliage(blossomRate=0.3)
        total = result.leaves.count + result.blossoms.count
        spread = 4 * math.sqrt(total * 0.3 * 0.7)
        self.assertLess(abs(result.blossoms.count - 0.3 * total), spread)

    def test_a_higher_rate_keeps_every_blossom(self):
        low = set(map(bytes, foliage(blossomRate=0.3).blossoms.sprout_co))
        high = set(map(bytes, foliage(blossomRate=0.6).blossoms.sprout_co))
        self.assertTrue(low < high)

    def test_leaves_and_blossoms_share_the_positions(self):
        plain = foliage().leaves
        mixed = foliage(blossomRate=0.4)
        together = np.concatenate([mixed.leaves.sprout_co, mixed.blossoms.sprout_co])
        self.assertEqual(sorted(map(bytes, together)), sorted(map(bytes, plain.sprout_co)))
        self.assertTrue(set(leaf_blocks(mixed.leaves)) <= set(leaf_blocks(plain)), "the leaves left are unchanged")

    def test_blossom_size_and_place(self):
        shapes = blossoms_module().BlossomShape
        scale = 0.3
        result = foliage(blossomRate=1.0, blossomScale=scale)
        blossoms = result.blossoms
        flowers = blossoms.vertices.reshape(blossoms.count, -1, 3).astype(np.float64)
        np.testing.assert_array_equal(flowers[:, 0], blossoms.sprout_co)
        reach = np.linalg.norm(flowers - flowers[:, :1], axis=2).max(axis=1)
        expected = scale * math.hypot(0.5, shapes.FORMS[shapes.CHERRY].cup)
        np.testing.assert_allclose(reach, expected, rtol=1e-5)


class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_object_material_and_uvs(self):
        blossoms = self.generate()
        record = helpers.module("build.tree_record").TreeRecord
        self.assertEqual(blossoms.parent, bpy.data.objects["tree"])
        self.assertEqual(blossoms[record.ROLE], "blossoms")
        mesh = blossoms.data
        self.assertEqual(len(mesh.polygons) % 25, 0)  # five petals of five quads each
        self.assertEqual([m.name for m in mesh.materials], ["Sapling Blossom"])
        self.assertNotIn("sharp_face", mesh.attributes)
        uv = np.zeros(len(mesh.loops) * 2)
        mesh.uv_layers["blossomUV"].uv.foreach_get("vector", uv)
        self.assertTrue((uv >= 0).all() and (uv <= 1).all())
        self.assertIn("leaves", bpy.data.objects)

    def test_no_leaves_object_at_rate_one(self):
        self.generate(blossomRate=1.0)
        self.assertNotIn("leaves", bpy.data.objects)

    def test_leaf_material_off(self):
        self.assertEqual(len(self.generate(leafMaterial=False).data.materials), 0)

    def test_rig_moves_the_blossoms(self):
        blossoms = self.generate(useRig=True)
        self.assertIn("Armature", [m.type.title() for m in blossoms.modifiers])
        bones = {bone.name for bone in helpers.armature().data.bones}
        self.assertTrue(blossoms.vertex_groups and {g.name for g in blossoms.vertex_groups} <= bones)
        weights = [len(v.groups) for v in blossoms.data.vertices]
        self.assertEqual(set(weights), {1}, "every vertex follows one bone")

    def test_node_wind_and_flutter_move_the_blossoms(self):
        blossoms = self.generate(windAnim=True, leafFlutter=True)
        self.assertEqual([m.name for m in blossoms.modifiers], ["Leaf Flutter", "Sapling Follow Wind"])
        rest = helpers.evaluated_vertices("blossoms")
        bpy.context.scene.frame_set(17)
        self.assertGreater(np.abs(helpers.evaluated_vertices("blossoms") - rest).max(), 1e-4)

    def test_make_mesh_keeps_the_blossoms(self):
        blossoms = self.generate(windAnim=True, makeMesh=True)
        self.assertIn("Sapling Follow Wind", [m.name for m in blossoms.modifiers])
