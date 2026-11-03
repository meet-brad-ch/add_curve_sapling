# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves and blossoms: leaves (the requirements each class or test names)."""

import unittest
import unittest.mock
from types import MappingProxyType

import bpy
import numpy as np
from support.addon import Addon
from support.foliage import Foliage
from support.model import Model
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0080")
class LastLevelBase(unittest.TestCase):
    """The last level has no bare base (its base size is reset to 0), also with 5 levels: the check compared the
    level clamped to 3 with levels - 1, so on deep trees the leaves started above a bare base."""

    def test_leaves_start_near_the_base_of_their_stem(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 10, 6, 4), showLeaves=True, leaves=60, baseSize=0.4, baseSize_s=1.0)
        sprouts = Model.grow(settings).grown.sprouts
        along = sprouts.offset[~sprouts.is_end]
        self.assertGreater(len(along), 50)
        self.assertLess(float(along.min()), 0.2)


@Verifies("SWR-0081")
class LeafInstanceObject(unittest.TestCase):
    """`leafDupliObj not in "NONE"` was a substring test: objects named N, O, NE, ONE, ... were ignored."""

    def test_short_object_name(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace")
        Scene.reset()
        instance = bpy.data.objects.new("N", bpy.data.meshes.new("N"))
        bpy.context.scene.collection.objects.link(instance)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj="N", do_update=True), {"FINISHED"})
        self.assertEqual(instance.parent, bpy.data.objects["leaves"])


@Verifies("SWR-0081")
class InstancePointLeaves(unittest.TestCase):
    """Instance Points leaves were rotated by vertex normals, which cannot be set since Blender 4.1:
    every leaf was turned by its position instead. Each instance must follow its own leaf normal."""

    def test_instances_follow_leaf_normals(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert")
        Scene.reset()
        card = Scene.add_leaf_card()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True), {"FINISHED"})

        leaves = bpy.data.objects["leaves"]
        rotations = leaves.data.attributes["leaf_rotation"].data
        depsgraph = bpy.context.evaluated_depsgraph_get()
        instances = [
            i.matrix_world.copy()
            for i in depsgraph.object_instances
            if i.is_instance and i.parent and i.parent.name == "leaves"
        ]
        self.assertEqual(len(instances), len(leaves.data.vertices))
        turned = 0
        for matrix, vertex, stored in zip(instances, leaves.data.vertices, rotations, strict=True):
            self.assertLess((matrix.translation - vertex.co).length, 1e-5)
            self.assertLess(matrix.to_quaternion().rotation_difference(stored.value).angle, 1e-4)
            position_rotation = vertex.co.normalized().to_track_quat("Y", "Z")
            turned += position_rotation.rotation_difference(stored.value).angle > 0.01
        self.assertGreater(turned, len(instances) // 2, "rotations still follow the leaf positions")


class LeafObjectSetting(unittest.TestCase):
    """The leaf object used to be a dynamic enum, stored by index: stored trees recorded one of their
    own objects ("envelope") and a missing object silently gave leaves that instance nothing."""

    @Verifies("SWR-0082")
    def test_instanced_leaves_without_object_cancel_before_creating_anything(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace")
        for name in ("", "no_such_object"):
            with self.subTest(leaf_object=name):
                Scene.reset()
                with self.assertRaisesRegex(RuntimeError, "Instanced leaves need a Leaf Object"):
                    bpy.ops.curve.tree_add(**settings, leafDupliObj=name, do_update=True)
                self.assertEqual(len(bpy.data.objects), 0)

    @Verifies("SWR-0081")
    def test_tree_part_is_not_a_leaf_object(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        settings.update(showLeaves=True, leafShape="dVert")
        with self.assertRaisesRegex(RuntimeError, "is part of a Sapling tree"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj="tree", do_update=True)

    @Verifies("SWR-0081")
    def test_stored_leaf_object_is_the_chosen_one(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", prune=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        stored = Addon.stored_settings(Scene.active_object())
        self.assertEqual(stored["leafDupliObj"], Scene.LEAF_CARD)


@Verifies("SWR-0083")
class TreeStructure(unittest.TestCase):
    def test_no_children_sprout_only_tips(self):
        """A negative leaf count (palmate leaves) sprouts at the stem tips only."""
        model = Model.grow_preset(levels=2, leaves=-3, showLeaves=True)
        grown = model.grown
        self.assertTrue(grown.sprouts.is_end.all())
        self.assertEqual(grown.sprouts.count, grown.level_ends[1] - grown.level_ends[0])


@Verifies("SWR-0086")
class LeafUp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("cambridge_oak.py")
        settings.update(levels=3, seed=5, leafShape="rect", leaves=12, showLeaves=True)
        cls.base = settings

    def test_one_lays_every_leaf_flat(self):
        normals = Foliage.normals(dict(self.base, leafUp=1.0))
        self.assertGreater(len(normals), 100)
        np.testing.assert_allclose(np.abs(normals[:, 2]), 1.0, atol=1e-5)

    def test_half_turns_every_leaf_halfway(self):
        tilted = Foliage.normals(dict(self.base, leafUp=0.0))
        half = Foliage.normals(dict(self.base, leafUp=0.5))
        before = np.degrees(np.arccos(np.clip(np.abs(tilted[:, 2]), 0.0, 1.0)))
        after = np.degrees(np.arccos(np.clip(np.abs(half[:, 2]), 0.0, 1.0)))
        # the mesh's normals are float32: near vertical, arccos magnifies their error to about 0.01 degrees
        np.testing.assert_allclose(after, before / 2.0, atol=0.02)

    def test_variation_tilts_each_leaf_within_its_range(self):
        normals = Foliage.normals(dict(self.base, leafUp=1.0, leafUpV=10.0))
        tilt = np.degrees(np.arccos(np.clip(np.abs(normals[:, 2]), 0.0, 1.0)))
        # every leaf within 10 degrees of horizontal (float32 normals: 0.02), and spread over the range, not flat
        self.assertLessEqual(tilt.max(), 10.02)
        self.assertGreater(tilt.max(), 8.0)
        self.assertGreater(np.median(tilt), 3.0)


class PalmSettings(unittest.TestCase):
    """Count Above Base, Leaves Above Base and Fan Angles: tree-gen's palm, fan palm and bamboo need them."""

    PALM = MappingProxyType({"levels": 2, "baseSize": 0.95, "branches": (0, 25, 0, 0), "showLeaves": False})

    @staticmethod
    def first_level(model):
        ends = model.grown.level_ends
        return [i for i in range(ends[0], ends[1]) if not model.grown.bone_map[i].is_split]

    @Verifies("SWR-0087")
    def test_leaves_above_base_keep_off_the_bare_base(self):
        result = Foliage.grow_with_tree(baseSize=0.4, baseSize_s=1.0)
        grown = result.grown
        plain = result.foliage.leaves
        self.assertLess(grown.sprouts.stem_offset[~grown.sprouts.is_tip].min(), 0.3)
        result = Foliage.grow_with_tree(baseSize=0.4, baseSize_s=1.0, leavesAboveBase=True)
        grown = result.grown
        above = result.foliage.leaves
        self.assertGreaterEqual(grown.sprouts.stem_offset[~grown.sprouts.is_tip].min(), 0.4 - 1e-9)
        self.assertLess(above.count, plain.count)

    @Verifies("SWR-0088")
    def test_fan_angles_cup_the_fans(self):
        def out_of_plane(**changes):
            foliage = Foliage.grow(leaves=-7, leafRotate=200.0, leafDownAngle=-20.0, leafDownAngleV=-5.0, **changes)
            leaves = foliage.leaves
            per_leaf = leaves.vertices.reshape(leaves.count, -1, 3).astype(np.float64)
            directions = per_leaf.mean(axis=1) - leaves.sprout_co
            directions /= np.linalg.norm(directions, axis=1, keepdims=True)
            fans = directions.reshape(-1, 7, 3)
            return np.array([np.linalg.svd(fan)[1][-1] for fan in fans])

        self.assertLess(out_of_plane().max(), 1e-5)
        self.assertGreater(np.median(out_of_plane(fanAngles=True)), 0.1)
