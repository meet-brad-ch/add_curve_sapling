# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/build: node wind."""

import unittest

import bpy
import numpy as np
from support.evaluated import Evaluated
from support.node_trees import NodeTrees
from support.scene import Scene


class NodeWindPoints(unittest.TestCase):
    """Every curve point moves by the inclusive transform of its joint: without bevel and at Resolution U 1 the
    bark's vertices are the moved control points themselves."""

    def test_every_point_moves_by_its_joints_transform(self):
        settings = NodeTrees.settings(windAnim=True, bevel=False, resU=1, jointStep=(2, 2, 1, 1))
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        curves = Evaluated.tree_curves().data
        rest = np.empty((len(curves.position_data), 3), np.float32)
        curves.position_data.foreach_get("vector", rest.ravel())
        numbers = np.empty(len(rest), np.int32)
        curves.attributes["sapling_joint"].data.foreach_get("value", numbers)
        sizes = np.array([len(c.points) for c in curves.curves])
        drawn = np.repeat(sizes > 1, sizes)  # a single-point curve draws nothing
        bpy.context.scene.frame_set(17)
        wind = bpy.data.objects["tree_wind"].evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        flat = np.empty(len(wind.position_data) * 16, np.float32)
        wind.attributes["fk_incl"].data.foreach_get("value", flat)
        matrices = flat.reshape(-1, 4, 4).transpose(0, 2, 1)[numbers]
        expected = np.einsum("nij,nj->ni", matrices[:, :3, :3], rest) + matrices[:, :3, 3]
        now = Evaluated.vertices("tree", 17)
        self.assertEqual(len(now), int(drawn.sum()))
        np.testing.assert_allclose(now, expected[drawn], atol=1e-5)
        self.assertGreater(np.linalg.norm(now - rest[drawn], axis=1).max(), 1e-2, "the tree moves")


class NodeWindJoints(unittest.TestCase):
    """The joints as the rig would make them: leaves climb to the nearest joint below when their level has none."""

    def test_leaves_follow_joints_of_the_level_below(self):
        settings = NodeTrees.settings(
            levels=3, branches=(0, 20, 5, 0), showLeaves=True, windAnim=True, makeMesh=True, jointLevels=1
        )
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        leaves = bpy.data.objects["leaves"]
        joints = np.empty(len(leaves.data.vertices), np.int32)
        leaves.data.attributes["sapling_joint"].data.foreach_get("value", joints)
        wind = bpy.data.objects["tree_wind"].data
        self.assertEqual(len(wind.curves), 1, "with Joint Levels 1 only the trunk has joints")
        trunk_joints = len(wind.position_data)
        self.assertTrue((joints < trunk_joints).all(), "every leaf hangs from a trunk joint")
        self.assertGreater(len(set(joints.tolist())), 1)
        moved = np.linalg.norm(Evaluated.vertices("leaves", 17) - Evaluated.vertices("leaves", 1), axis=1)
        self.assertGreater(moved.max(), 1e-3)

    def test_every_point_follows_the_last_joint_head_before_it(self):
        """Joint Length 2: points 0 and 1 follow the joint at 0, points 2 and 3 the one at 2, the last the last."""
        joints = NodeTrees.model_joints(levels=2, makeMesh=True, jointLevels=0, jointStep=(2, 2, 1, 1)).joints
        point_joints = joints.point_joints()
        self.assertEqual(len(point_joints), int(joints.flat.start[-1]))
        checked = 0
        for c in range(len(joints.sizes)):
            start = int(joints.starts[c])
            size = int(joints.sizes[c])
            if size < 2:
                continue
            last_head = start + (int(joints.count[c]) - 1) * 2
            for n in range(size):
                self.assertEqual(point_joints[start + n], min(start + (n // 2) * 2, last_head), f"curve {c} point {n}")
                checked += 1
        self.assertGreater(checked, 100)
        self.assertTrue(np.isin(point_joints[joints.sizes[0] :], joints.joint_point).all())
        ordinals = joints.ordinals(point_joints)
        np.testing.assert_array_equal(joints.joint_point[ordinals], point_joints)

    def test_points_above_the_joint_levels_follow_the_joint_their_stem_hangs_from(self):
        found = NodeTrees.model_joints(levels=3, branches=(0, 20, 5, 0), makeMesh=True, jointLevels=1)
        grown = found.model.grown
        joints = found.joints
        point_joints = joints.point_joints()
        trunk_points = int(joints.sizes[0])
        self.assertTrue((point_joints[trunk_points:] < trunk_points).all(), "every branch point follows a trunk joint")
        second_level = np.arange(grown.level_ends[0], grown.level_ends[1])
        hanging = joints.nearest_joint(joints.link_spline[second_level], joints.link_point[second_level])
        for c, joint in zip(second_level.tolist(), hanging.tolist(), strict=True):
            start = int(joints.starts[c])
            size = int(joints.sizes[c])
            self.assertTrue((point_joints[start : start + size] == joint).all(), f"curve {c}")
        np.testing.assert_array_equal(joints.leaf_joints(NodeTrees.empty_leaves(grown)), [])

    def test_a_point_that_is_no_joint_has_no_ordinal(self):
        joints = NodeTrees.model_joints(levels=2, makeMesh=True, jointStep=(2, 2, 1, 1)).joints
        with self.assertRaisesRegex(RuntimeError, "not a joint"):
            joints.ordinals(np.array([1]))  # point 1 of the trunk is inside the first joint's span

    def test_a_stem_hanging_from_no_joint_is_an_error(self):
        joints = NodeTrees.model_joints(levels=2).joints
        joints.eligible[:] = False  # as if no curve had joints
        with self.assertRaisesRegex(RuntimeError, "without a joint below"):
            joints.nearest_joint(np.array([1]), np.array([0]))


class BakedBark(unittest.TestCase):
    """Make Mesh bakes the sweep into the root's mesh: with the rig weighted to its bones, otherwise following the
    node wind through the Follow Wind modifier."""

    def test_every_baked_vertex_has_the_joint_of_its_segment(self):
        """Without bevel the baked vertices are the evaluated points: Resolution U per segment, each with the joint
        number of the point its segment starts at (the curves' own joint numbers, which the resample rounds inside
        a segment, must not reach the baked mesh)."""
        settings = NodeTrees.settings(windAnim=True, makeMesh=True, bevel=False, resU=4, jointStep=(2, 2, 1, 1))
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        curves = Evaluated.tree_curves().data
        numbers = np.empty(len(curves.position_data), np.int32)
        curves.attributes["sapling_joint"].data.foreach_get("value", numbers)
        expected = []
        start = 0
        for c in curves.curves:
            size = len(c.points)
            if size > 1:
                segment = np.minimum(np.arange((size - 1) * 4 + 1) // 4, size - 2)
                expected.append(numbers[start + segment])
            start += size
        mesh = bpy.data.objects["tree"].data
        self.assertEqual([a.name for a in mesh.attributes if a.name.startswith("sapling")], ["sapling_joint"])
        baked = np.empty(len(mesh.vertices), np.int32)
        mesh.attributes["sapling_joint"].data.foreach_get("value", baked)
        np.testing.assert_array_equal(baked, np.concatenate(expected))
