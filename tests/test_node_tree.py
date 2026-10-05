# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree as a mesh root whose "Sapling Tree" modifier sweeps the curves to the bark, and the wind without the
rig: forward kinematics in Geometry Nodes, matching the armature's wind."""

import json
import random
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import bpy
import helpers
import numpy as np


def tree_settings(**changes):
    settings = helpers.resolve_preset("quaking_aspen.py")
    settings.update(levels=2, showLeaves=False, bevel=True, bevelRes=1)
    settings.update(changes)
    return settings


def vertices(name, frame=None):
    """An object's evaluated vertex positions (at a frame), as an (n, 3) array."""
    if frame is not None:
        bpy.context.scene.frame_set(frame)
    ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ob.to_mesh()
    out = np.empty(len(mesh.vertices) * 3, np.float32)
    mesh.vertices.foreach_get("co", out)
    ob.to_mesh_clear()
    return out.reshape(-1, 3)


def evaluated_counts(name):
    ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = ob.to_mesh()
    counts = (len(mesh.vertices), len(mesh.edges), len(mesh.polygons))
    ob.to_mesh_clear()
    return counts


def model_joints(**changes):
    """The WindJoints of a tree grown in the model alone (no Blender objects): (params, grown, joints)."""
    settings = tree_settings(**changes)
    params = helpers.module("model.params").TreeParams(SimpleNamespace(**settings, leafDupliObj=""))
    curve = helpers.module("model.curve_data").CurveData()
    grown = helpers.module("model.tree").TreeGrower(params, random.Random(params.seed)).grow(curve, params.scale)
    return params, grown, helpers.module("build.node_wind").WindJoints(params, curve, grown)


def grown_leaves(grown):
    """A leaf set with no leaves (the arrays leaf_joints reads), for a tree grown in the model alone."""
    return SimpleNamespace(parent_spline=np.zeros(0, np.int64), parent_point=np.zeros(0, np.int64), verts_per_leaf=4)


def set_input(ob, name, value):
    """Set an input of the root's "Sapling Tree" modifier, as a user does in the modifier panel."""
    helpers.module("build.node_groups").SharedNodeGroup.set_input(ob.modifiers["Sapling Tree"], name, value)
    ob.update_tag()


class LegacyBevel:
    """The bark as the old tree drew it: a legacy curve with the same points and handles, bevelled by Blender."""

    @staticmethod
    def legacy_curve(curves):
        """A legacy Curve datablock with the Curves' points, handles, handle types and radii."""
        data = bpy.data.curves.new("legacy_bevel", "CURVE")
        data.dimensions = "3D"
        attributes = curves.attributes
        co = helpers._floats(curves.position_data, "vector", 3).reshape(-1, 3)
        left = helpers._floats(attributes["handle_left"].data, "vector", 3).reshape(-1, 3)
        right = helpers._floats(attributes["handle_right"].data, "vector", 3).reshape(-1, 3)
        radius = helpers._floats(attributes["radius"].data, "value", 1)
        h1 = helpers._ints(attributes["handle_type_left"].data, "value")
        h2 = helpers._ints(attributes["handle_type_right"].data, "value")
        start = 0
        for c in curves.curves:
            size = len(c.points)
            span = slice(start, start + size)
            points = data.splines.new("BEZIER").bezier_points
            points.add(size - 1)
            points.foreach_set("handle_left_type", h1[span].tolist())
            points.foreach_set("handle_right_type", h2[span].tolist())
            points.foreach_set("co", co[span].ravel())
            points.foreach_set("handle_left", left[span].ravel())
            points.foreach_set("handle_right", right[span].ravel())
            points.foreach_set("radius", radius[span])
            start += size
        return data

    @classmethod
    def counts(cls, settings):
        data = cls.legacy_curve(helpers.tree_curves().data)
        data.bevel_depth = 1.0 if settings["bevel"] else 0.0
        data.bevel_resolution = settings["bevelRes"]
        data.resolution_u = settings["resU"]
        ob = bpy.data.objects.new("legacy_bevel", data)
        bpy.context.scene.collection.objects.link(ob)
        try:
            return evaluated_counts(ob.name)
        finally:
            bpy.data.objects.remove(ob)
            bpy.data.curves.remove(data)


class RootSweep(unittest.TestCase):
    """The root is a mesh: the bark it sweeps has the old bevel's vertices and faces."""

    def test_root_is_a_mesh_that_draws_the_bark(self):
        self.assertEqual(helpers.generate(tree_settings()), {"FINISHED"})
        root = helpers.active_object()
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        self.assertEqual([(m.type, m.name) for m in root.modifiers], [("NODES", "Sapling Tree")])
        source = helpers.tree_curves()
        self.assertEqual((source.type, source.parent), ("CURVES", root))
        self.assertTrue(source.hide_viewport and source.hide_render)
        verts, _edges, faces = evaluated_counts("tree")
        self.assertGreater(faces, 1000)
        self.assertGreater(verts, faces)

    def test_sweep_counts_equal_the_old_bevel(self):
        """Blender's own bevel of a legacy curve with the same points is the reference."""
        for changes in ({}, {"bevelRes": 3, "resU": 2}, {"bevel": False}, {"prune": True}):
            with self.subTest(changes=changes):
                settings = tree_settings(**changes)
                self.assertEqual(helpers.generate(settings), {"FINISHED"})
                self.assertEqual(evaluated_counts("tree"), LegacyBevel.counts(settings))

    def test_inputs_stay_live(self):
        self.assertEqual(helpers.generate(tree_settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        before = evaluated_counts("tree")
        set_input(root, "Bevel Resolution", 4)
        after = evaluated_counts("tree")
        self.assertGreater(after[0], before[0])
        set_input(root, "Fill Caps", True)
        self.assertGreater(evaluated_counts("tree")[2], after[2])

    def test_apply_gives_the_mesh(self):
        self.assertEqual(helpers.generate(tree_settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        counts = evaluated_counts("tree")
        with bpy.context.temp_override(object=root, active_object=root):
            self.assertEqual(bpy.ops.object.modifier_apply(modifier="Sapling Tree"), {"FINISHED"})
        mesh = root.data
        self.assertEqual((len(mesh.vertices), len(mesh.edges), len(mesh.polygons)), counts)
        self.assertEqual([m.name for m in mesh.materials], ["Sapling Bark"])

    def test_export_writes_the_bark(self):
        self.assertEqual(helpers.generate(tree_settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        verts = evaluated_counts("tree")[0]
        for ob in bpy.context.view_layer.objects:
            ob.select_set(ob == root)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tree.obj"
            result = bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True, apply_modifiers=True)
            self.assertEqual(result, {"FINISHED"})
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(line.startswith("v ") for line in lines), verts)

    def test_fast_preview_shows_the_curves(self):
        self.assertEqual(helpers.generate(tree_settings(fastPreview=True)), {"FINISHED"})
        root = bpy.data.objects["tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
        geometry = root.evaluated_geometry()
        self.assertEqual(len(geometry.mesh.vertices) if geometry.mesh else 0, 0)  # the root's own, empty mesh
        self.assertGreater(len(geometry.curves.curves), 10)
        self.assertEqual(root.display_type, "TEXTURED")  # bounds are the rig's preview only


class RigSweep(unittest.TestCase):
    """With the rig, the bark is still the live sweep: its points and handles are read from the joint proxy, a
    hidden mesh the bones deform through vertex groups."""

    @classmethod
    def setUpClass(cls):
        cls.result = helpers.generate(tree_settings(useRig=True, windAnim=True))

    def test_curves_source_and_joint_proxy(self):
        self.assertEqual(self.result, {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual(helpers.tree_curves().type, "CURVES")
        proxy = bpy.data.objects["tree_joints"]
        self.assertEqual((proxy.type, proxy.parent, proxy.hide_viewport, proxy.hide_render), ("MESH", root, True, True))
        points = sum(len(c.points) for c in helpers.tree_curves().data.curves)
        self.assertEqual(len(proxy.data.vertices), 3 * points)
        self.assertEqual([m.type for m in proxy.modifiers], ["ARMATURE"])
        self.assertEqual(proxy.modifiers[0].object.name, "treeArm")
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        self.assertEqual({g.name for g in proxy.vertex_groups}, bones)
        self.assertTrue(all(len(v.groups) == 1 and v.groups[0].weight == 1.0 for v in proxy.data.vertices))
        inputs = helpers._modifier_inputs(root)["Sapling Tree"]["inputs"]
        self.assertEqual((inputs["Rig"], inputs["Wind"], inputs["Joints"]), (True, False, "tree_joints"))

    def test_bark_sways_with_the_bones(self):
        moved = np.linalg.norm(vertices("tree", 17) - vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the bark moves")
        self.assertEqual(evaluated_counts("tree"), evaluated_counts("tree"))

    def test_fast_preview_disables_the_proxy_deform(self):
        self.assertEqual(helpers.generate(tree_settings(useRig=True, fastPreview=True)), {"FINISHED"})
        proxy = bpy.data.objects["tree_joints"]
        self.assertFalse(proxy.modifiers[0].show_viewport)
        self.assertEqual(bpy.data.objects["tree"].display_type, "BOUNDS")


def wind_joint_positions(frame, joints):
    """Where the heads of these joints (numbers) are at a frame: the wind curves' evaluated transform at each."""
    bpy.context.scene.frame_set(frame)
    wind = bpy.data.objects["tree_wind"].evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    n = len(wind.position_data)
    co = np.empty(n * 3, np.float32)
    wind.position_data.foreach_get("vector", co)
    flat = np.empty(n * 16, np.float32)
    wind.attributes["fk_total"].data.foreach_get("value", flat)
    matrices = flat.reshape(n, 4, 4).transpose(0, 2, 1)  # stored by columns
    heads = np.einsum("nij,nj->ni", matrices[:, :3, :3], co.reshape(-1, 3)) + matrices[:, :3, 3]
    return heads[joints]


class NodeWind(unittest.TestCase):
    """Wind without the rig: the joints' transforms, composed in Geometry Nodes on the wind curves (one point per
    joint), move the bark."""

    @classmethod
    def setUpClass(cls):
        cls.settings = tree_settings(windAnim=True, loopFrames=48)
        cls.result = helpers.generate(cls.settings)
        cls.rest = vertices("tree", 1)

    def test_no_armature(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertFalse([ob for ob in bpy.data.objects if ob.type == "ARMATURE"])
        self.assertEqual([m.name for m in helpers.tree_curves().modifiers], [])
        inputs = helpers._modifier_inputs(bpy.data.objects["tree"])["Sapling Tree"]["inputs"]
        self.assertEqual((inputs["Wind"], inputs["Wind Joints"], inputs["Rig"]), (True, "tree_wind", False))

    def test_wind_curves_hold_one_point_per_joint(self):
        _, _, joints = model_joints(windAnim=True, loopFrames=48)
        wind = bpy.data.objects["tree_wind"]
        root = bpy.data.objects["tree"]
        self.assertEqual((wind.type, wind.parent, wind.hide_viewport, wind.hide_render), ("CURVES", root, True, True))
        self.assertEqual([m.name for m in wind.modifiers], ["Sapling Wind"])
        self.assertEqual(len(wind.data.position_data), len(joints.joint_point))
        self.assertEqual([len(c.points) for c in wind.data.curves], joints.count[joints.eligible].tolist())
        self.assertLess(len(joints.joint_point), len(helpers.tree_curves().data.position_data))
        numbers = np.empty(len(helpers.tree_curves().data.position_data), np.int32)
        helpers.tree_curves().data.attributes["sapling_joint"].data.foreach_get("value", numbers)
        np.testing.assert_array_equal(numbers, joints.ordinals(joints.point_joints()))

    def test_bark_moves(self):
        moved = np.linalg.norm(vertices("tree", 17) - self.rest, axis=1)
        self.assertGreater(moved.max(), 1e-3)
        self.assertGreater((moved > 1e-5).mean(), 0.5)

    def test_loop_returns_to_the_first_frame(self):
        self.assertLess(np.abs(vertices("tree", 49) - self.rest).max(), 1e-4)

    def test_trunk_base_stays_still(self):
        """The first two joints of the trunk hold still: the centres of the bark rings at the trunk's first three
        points (a ring may still turn: the moving points above change the curve's direction there)."""
        s = self.settings
        profile = 4 + 2 * s["bevelRes"]
        for frame in (9, 17, 33):
            now = vertices("tree", frame)
            for point in range(3):
                ring = slice(point * s["resU"] * profile, (point * s["resU"] + 1) * profile)
                with self.subTest(frame=frame, point=point):
                    centre = now[ring].mean(axis=0) - self.rest[ring].mean(axis=0)
                    self.assertLess(np.abs(centre).max(), 1e-6)

    def test_bark_stretches_no_more_than_the_rig(self):
        """Rotations keep lengths: the bark's edges hardly change (the rig's envelopes stretch up to about 3 %)."""
        edges = self.evaluated_edges()
        rest = np.linalg.norm(self.rest[edges[:, 0]] - self.rest[edges[:, 1]], axis=1)
        now = vertices("tree", 17)
        lengths = np.linalg.norm(now[edges[:, 0]] - now[edges[:, 1]], axis=1)
        long = rest > 1e-4
        stretch = np.abs(lengths[long] / rest[long] - 1.0)
        self.assertLess(np.percentile(stretch, 99), 0.035)

    @staticmethod
    def evaluated_edges():
        ob = bpy.data.objects["tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        edges = np.empty(len(mesh.edges) * 2, np.int32)
        mesh.edges.foreach_get("vertices", edges)
        ob.to_mesh_clear()
        return edges.reshape(-1, 2)


class NodeWindPoints(unittest.TestCase):
    """Every curve point moves by the inclusive transform of its joint: without bevel and at Resolution U 1 the
    bark's vertices are the moved control points themselves."""

    def test_every_point_moves_by_its_joints_transform(self):
        settings = tree_settings(windAnim=True, bevel=False, resU=1, jointStep=(2, 2, 1, 1))
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        curves = helpers.tree_curves().data
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
        now = vertices("tree", 17)
        self.assertEqual(len(now), int(drawn.sum()))
        np.testing.assert_allclose(now, expected[drawn], atol=1e-5)
        self.assertGreater(np.linalg.norm(now - rest[drawn], axis=1).max(), 1e-2, "the tree moves")


class NodeWindMatchesTheRig(unittest.TestCase):
    """The node wind moves the bark as the armature's wind does, from the same random draws."""

    FRAMES = range(5, 97, 8)

    def displacements(self, rig, strength):
        settings = tree_settings(levels=3, branches=(0, 30, 10, 0), windAnim=True, useRig=rig)
        settings.update(windStrength=strength, gustStrength=strength)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        return np.stack([vertices("tree", frame) for frame in self.FRAMES])

    def relative_rms(self, strength):
        rest = self.still()
        rig = self.displacements(True, strength) - rest
        node = self.displacements(False, strength) - rest
        return float(np.sqrt(np.mean((node - rig) ** 2)) / np.sqrt(np.mean(rig**2)))

    def still(self):
        settings = tree_settings(levels=3, branches=(0, 30, 10, 0))
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        return vertices("tree", 1)

    def test_wind_1(self):
        self.assertLess(self.relative_rms(1.0), 0.08)

    def test_wind_3(self):
        self.assertLess(self.relative_rms(3.0), 0.02)


class NodeWindLeaves(unittest.TestCase):
    """Leaves follow the joint they hang from: rigid, and at the same distance from it on every frame."""

    @classmethod
    def setUpClass(cls):
        settings = tree_settings(showLeaves=True, windAnim=True)
        cls.result = helpers.generate(settings)
        cls.leaves = bpy.data.objects["leaves"]
        cls.size = 6 if settings["leafShape"] == "hex" else 4

    def joint_positions(self, frame):
        """Where each leaf vertex's joint head is at a frame."""
        joints = np.empty(len(self.leaves.data.vertices), np.int32)
        self.leaves.data.attributes["sapling_joint"].data.foreach_get("value", joints)
        return wind_joint_positions(frame, joints)

    def test_modifiers(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertEqual([m.name for m in self.leaves.modifiers], ["Sapling Follow Wind"])

    def test_leaves_move_rigidly_with_their_joint(self):
        rest = vertices("leaves", 1)
        rest_distance = np.linalg.norm(rest - self.joint_positions(1), axis=1)
        moved = 0
        for frame in (9, 17):
            now = vertices("leaves", frame)
            distance = np.linalg.norm(now - self.joint_positions(frame), axis=1)
            np.testing.assert_allclose(distance, rest_distance, atol=1e-4)
            leaves_now = now.reshape(-1, self.size, 3)
            leaves_rest = rest.reshape(-1, self.size, 3)
            span_now = np.linalg.norm(leaves_now - leaves_now[:, :1], axis=2)
            span_rest = np.linalg.norm(leaves_rest - leaves_rest[:, :1], axis=2)
            np.testing.assert_allclose(span_now, span_rest, atol=1e-4)
            moved += int((np.linalg.norm(now - rest, axis=1) > 1e-4).sum())
        self.assertGreater(moved, len(rest) // 2)


class NodeWindLeafOptions(unittest.TestCase):
    def test_flutter_comes_before_the_wind(self):
        settings = tree_settings(showLeaves=True, windAnim=True, leafFlutter=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        names = [m.name for m in bpy.data.objects["leaves"].modifiers]
        self.assertEqual(names[1:], ["Sapling Follow Wind"])
        self.assertEqual(bpy.data.objects["leaves"].modifiers[0].type, "NODES")

    def test_instanced_leaves_follow(self):
        settings = tree_settings(showLeaves=True, windAnim=True, leafShape="dVert")
        helpers.reset_scene()
        card = helpers.add_leaf_card()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True), {"FINISHED"})
        positions = []
        for frame in (1, 17):
            bpy.context.scene.frame_set(frame)
            depsgraph = bpy.context.evaluated_depsgraph_get()
            positions.append([i.matrix_world.translation.copy() for i in depsgraph.object_instances if i.is_instance])
        self.assertEqual(len(positions[0]), len(bpy.data.objects["leaves"].data.vertices))
        self.assertTrue(any((a - b).length > 1e-4 for a, b in zip(*positions, strict=True)))


class NodeWindJoints(unittest.TestCase):
    """The joints as the rig would make them: leaves climb to the nearest joint below when their level has none."""

    def test_leaves_follow_joints_of_the_level_below(self):
        settings = tree_settings(
            levels=3, branches=(0, 20, 5, 0), showLeaves=True, windAnim=True, makeMesh=True, jointLevels=1
        )
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        leaves = bpy.data.objects["leaves"]
        joints = np.empty(len(leaves.data.vertices), np.int32)
        leaves.data.attributes["sapling_joint"].data.foreach_get("value", joints)
        wind = bpy.data.objects["tree_wind"].data
        self.assertEqual(len(wind.curves), 1, "with Joint Levels 1 only the trunk has joints")
        trunk_joints = len(wind.position_data)
        self.assertTrue((joints < trunk_joints).all(), "every leaf hangs from a trunk joint")
        self.assertGreater(len(set(joints.tolist())), 1)
        moved = np.linalg.norm(vertices("leaves", 17) - vertices("leaves", 1), axis=1)
        self.assertGreater(moved.max(), 1e-3)

    def test_every_point_follows_the_last_joint_head_before_it(self):
        """Joint Length 2: points 0 and 1 follow the joint at 0, points 2 and 3 the one at 2, the last the last."""
        _, _, joints = model_joints(levels=2, makeMesh=True, jointLevels=0, jointStep=(2, 2, 1, 1))
        point_joints = joints.point_joints()
        self.assertEqual(len(point_joints), int(joints.flat.start[-1]))
        checked = 0
        for c in range(len(joints.sizes)):
            start, size = int(joints.starts[c]), int(joints.sizes[c])
            if size < 2:
                continue
            last_head = start + (int(joints.count[c]) - 1) * 2
            for n in range(size):
                self.assertEqual(point_joints[start + n], min(start + (n // 2) * 2, last_head), f"curve {c} point {n}")
                checked += 1
        self.assertGreater(checked, 100)
        self.assertTrue(joints.is_joint[point_joints[joints.sizes[0] :]].all())
        ordinals = joints.ordinals(point_joints)
        np.testing.assert_array_equal(joints.joint_point[ordinals], point_joints)

    def test_points_above_the_joint_levels_follow_the_joint_their_stem_hangs_from(self):
        _, grown, joints = model_joints(levels=3, branches=(0, 20, 5, 0), makeMesh=True, jointLevels=1)
        point_joints = joints.point_joints()
        trunk_points = int(joints.sizes[0])
        self.assertTrue((point_joints[trunk_points:] < trunk_points).all(), "every branch point follows a trunk joint")
        second_level = np.arange(grown.level_ends[0], grown.level_ends[1])
        hanging = joints.nearest_joint(joints.link_spline[second_level], joints.link_point[second_level])
        for c, joint in zip(second_level.tolist(), hanging.tolist(), strict=True):
            start, size = int(joints.starts[c]), int(joints.sizes[c])
            self.assertTrue((point_joints[start : start + size] == joint).all(), f"curve {c}")
        np.testing.assert_array_equal(joints.leaf_joints(grown_leaves(grown)), [])

    def test_a_point_that_is_no_joint_has_no_ordinal(self):
        _, _, joints = model_joints(levels=2, makeMesh=True, jointStep=(2, 2, 1, 1))
        with self.assertRaisesRegex(RuntimeError, "not a joint"):
            joints.ordinals(np.array([1]))  # point 1 of the trunk is inside the first joint's span

    def test_a_stem_hanging_from_no_joint_is_an_error(self):
        _, _, joints = model_joints(levels=2)
        joints.eligible[:] = False  # as if no curve had joints
        with self.assertRaisesRegex(RuntimeError, "without a joint below"):
            joints.nearest_joint(np.array([1]), np.array([0]))


class BakedBark(unittest.TestCase):
    """Make Mesh bakes the sweep into the root's mesh: with the rig weighted to its bones, otherwise following the
    node wind through the Follow Wind modifier."""

    def test_baked_mesh_follows_the_node_wind(self):
        settings = tree_settings(windAnim=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        live = evaluated_counts("tree")
        settings["makeMesh"] = True
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual([m.name for m in root.modifiers], ["Sapling Follow Wind"])
        self.assertEqual((len(root.data.vertices), len(root.data.edges), len(root.data.polygons)), live)
        self.assertEqual([m.name for m in root.data.materials], ["Sapling Bark"])
        self.assertNotIn("treemesh", bpy.data.objects)
        moved = np.linalg.norm(vertices("tree", 17) - vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the baked bark moves")

    def test_every_baked_vertex_has_the_joint_of_its_segment(self):
        """Without bevel the baked vertices are the evaluated points: Resolution U per segment, each with the joint
        number of the point its segment starts at (the curves' own joint numbers, which the resample rounds inside
        a segment, must not reach the baked mesh)."""
        settings = tree_settings(windAnim=True, makeMesh=True, bevel=False, resU=4, jointStep=(2, 2, 1, 1))
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        curves = helpers.tree_curves().data
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

    def test_baked_mesh_is_skinned_to_the_rig(self):
        self.assertEqual(helpers.generate(tree_settings(useRig=True, windAnim=True, makeMesh=True)), {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual([m.type for m in root.modifiers], ["ARMATURE"])
        self.assertEqual(root.modifiers[0].object.name, "treeArm")
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        self.assertTrue({g.name for g in root.vertex_groups} <= bones)
        self.assertTrue(all(len(v.groups) == 1 and v.groups[0].weight == 1.0 for v in root.data.vertices))
        self.assertEqual([m.name for m in root.data.materials], ["Sapling Bark"])
        moved = np.linalg.norm(vertices("tree", 17) - vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the baked bark moves")

    def test_baked_rig_tree_exports_a_skin(self):
        self.assertEqual(helpers.generate(tree_settings(useRig=True, makeMesh=True)), {"FINISHED"})
        root = bpy.data.objects["tree"]
        bones = len(bpy.data.objects["treeArm"].data.bones)
        for ob in bpy.context.view_layer.objects:
            ob.select_set(ob.name in ("tree", "treeArm"))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tree.gltf"
            result = bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLTF_SEPARATE", use_selection=True)
            self.assertEqual(result, {"FINISHED"})
            document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(document["skins"]), 1)
        self.assertEqual(len(document["skins"][0]["joints"]), bones)
        self.assertEqual(len(root.data.vertices), document["accessors"][0]["count"])

    def test_fast_preview_shows_the_bounds(self):
        self.assertEqual(helpers.generate(tree_settings(windAnim=True, makeMesh=True, fastPreview=True)), {"FINISHED"})
        self.assertEqual(bpy.data.objects["tree"].display_type, "BOUNDS")
