# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree as a mesh root whose "Sapling Tree" modifier sweeps the curves to the bark, and the wind without the
rig: forward kinematics in Geometry Nodes, matching the armature's wind."""

import tempfile
import unittest
from pathlib import Path

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


def set_input(ob, name, value):
    """Set an input of the root's "Sapling Tree" modifier, as a user does in the modifier panel."""
    helpers.module("build.node_groups").SharedNodeGroup.set_input(ob.modifiers["Sapling Tree"], name, value)
    ob.update_tag()


class LegacyBevel:
    """The bark as the old tree drew it: a legacy curve with the same points, bevelled by Blender."""

    @staticmethod
    def counts(settings):
        source = helpers.tree_curves()
        data = source.data.copy()
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
        """The rig keeps a legacy curve source, so Blender's own bevel of the same points is the reference."""
        for changes in ({}, {"bevelRes": 3, "resU": 2}, {"bevel": False}, {"prune": True}):
            with self.subTest(changes=changes):
                settings = tree_settings(useRig=True, **changes)
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


class NodeWind(unittest.TestCase):
    """Wind without the rig: the joints' transforms composed in Geometry Nodes move the bark."""

    @classmethod
    def setUpClass(cls):
        cls.settings = tree_settings(windAnim=True, loopFrames=48)
        cls.result = helpers.generate(cls.settings)
        cls.rest = vertices("tree", 1)

    def test_no_armature(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertFalse([ob for ob in bpy.data.objects if ob.type == "ARMATURE"])
        self.assertEqual([m.name for m in helpers.tree_curves().modifiers], ["Sapling Wind"])

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
        """Where each leaf vertex's joint head is at a frame: the evaluated curves' transform at that point."""
        bpy.context.scene.frame_set(frame)
        source = helpers.tree_curves().evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        n = len(source.position_data)
        co = np.empty(n * 3, np.float32)
        source.position_data.foreach_get("vector", co)
        flat = np.empty(n * 16, np.float32)
        source.attributes["fk_total"].data.foreach_get("value", flat)
        matrices = flat.reshape(n, 4, 4).transpose(0, 2, 1)  # stored by columns
        heads = np.einsum("nij,nj->ni", matrices[:, :3, :3], co.reshape(-1, 3)) + matrices[:, :3, 3]
        joints = np.empty(len(self.leaves.data.vertices), np.int32)
        self.leaves.data.attributes["sapling_joint"].data.foreach_get("value", joints)
        return heads[joints]

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


class NodeWindSkinMesh(unittest.TestCase):
    """Make Mesh without the rig: the skin mesh follows the node wind."""

    def test_skin_mesh_moves_with_the_wind(self):
        self.assertEqual(helpers.generate(tree_settings(windAnim=True, makeMesh=True)), {"FINISHED"})
        skin = bpy.data.objects["treemesh"]
        self.assertEqual([m.type for m in skin.modifiers], ["NODES", "SKIN"])
        self.assertTrue(skin.vertex_groups)  # one per joint, as with the rig: the skin mesh can still be rigged
        moved = np.linalg.norm(vertices("treemesh", 17) - vertices("treemesh", 1), axis=1)
        self.assertGreater(moved.max(), 1e-3)
