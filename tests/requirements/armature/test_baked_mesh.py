# SPDX-License-Identifier: GPL-3.0-or-later

"""Armature and baked mesh: baked mesh (the requirements each class or test names)."""

import json
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import bpy
import numpy as np
from support.addon import Addon
from support.evaluated import Evaluated
from support.mesh_counts import MeshCounts
from support.node_trees import NodeTrees
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


class BakedBark(unittest.TestCase):
    """Make Mesh bakes the sweep into the root's mesh: with the rig weighted to its bones, otherwise following the
    node wind through the Follow Wind modifier."""

    @Verifies("SWR-0104")
    def test_baked_mesh_follows_the_node_wind(self):
        settings = NodeTrees.settings(windAnim=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        live = NodeTrees.counts("tree")
        settings["makeMesh"] = True
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual([m.name for m in root.modifiers], ["Sapling Follow Wind"])
        self.assertEqual(MeshCounts.of(root.data), live)
        self.assertEqual([m.name for m in root.data.materials], ["Sapling Bark"])
        self.assertNotIn("treemesh", bpy.data.objects)
        moved = np.linalg.norm(Evaluated.vertices("tree", 17) - Evaluated.vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the baked bark moves")

    @Verifies("SWR-0104")
    def test_baked_mesh_is_skinned_to_the_rig(self):
        self.assertEqual(Scene.generate(NodeTrees.settings(useRig=True, windAnim=True, makeMesh=True)), {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual([m.type for m in root.modifiers], ["ARMATURE"])
        self.assertEqual(root.modifiers[0].object.name, "treeArm")
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        self.assertTrue({g.name for g in root.vertex_groups} <= bones)
        not_rigid = [v.index for v in root.data.vertices if not (len(v.groups) == 1 and v.groups[0].weight == 1.0)]
        self.assertEqual(not_rigid[:5], [], "vertices not in exactly one group at weight 1")
        self.assertEqual([m.name for m in root.data.materials], ["Sapling Bark"])
        moved = np.linalg.norm(Evaluated.vertices("tree", 17) - Evaluated.vertices("tree", 1), axis=1)
        self.assertGreater(np.mean(moved > 1e-3), 0.5, "most of the baked bark moves")

    @Verifies("SWR-0107")
    def test_baked_rig_tree_exports_a_skin(self):
        self.assertEqual(Scene.generate(NodeTrees.settings(useRig=True, makeMesh=True)), {"FINISHED"})
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


@Verifies("SWR-0104")
class StaticBake(unittest.TestCase):
    """Make Mesh without a rig and without wind bakes the bark and binds it to nothing: no joints are computed."""

    def test_static_bake_binds_nothing(self):
        settings = NodeTrees.settings()
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        live = NodeTrees.counts("tree")
        settings["makeMesh"] = True
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        root = bpy.data.objects["tree"]
        self.assertEqual(list(root.modifiers), [])
        self.assertEqual([a.name for a in root.data.attributes if a.name.startswith("sapling")], [])
        self.assertEqual(MeshCounts.of(root.data), live)
        self.assertNotIn("tree_wind", bpy.data.objects)
        self.assertNotIn("tree_joints", bpy.data.objects)

    def test_a_binding_needs_the_joints(self):
        bake = Addon.module("build.bake").BarkBake(None, bpy.context)
        with self.assertRaisesRegex(RuntimeError, "needs the joints"):
            bake.bake(None, None, None, None, object())


@Verifies("SWR-0104")
class SecondTree(unittest.TestCase):
    """The skin mesh looked the armature up by the name 'treeArm', so a second tree got the first one's."""

    def test_baked_mesh_uses_its_own_armature(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, makeMesh=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        for root_name, arm_name in (("tree", "treeArm"), ("tree.001", "treeArm.001")):
            root = bpy.data.objects[root_name]
            armatures = [m for m in root.modifiers if m.type == "ARMATURE"]
            self.assertTrue(armatures, "an Armature modifier on the root")
            modifier = armatures[0]
            self.assertEqual(modifier.object.name, arm_name, root_name)
            self.assertEqual(bpy.data.objects[arm_name].parent, root, root_name)


@Verifies("SWR-0104")
class Ownership(unittest.TestCase):
    def test_baked_mesh_is_the_tree_itself(self):
        Scene.reset()
        root = Trees.add(makeMesh=True, useRig=False)
        self.assertGreater(len(root.data.vertices), 0)
        self.assertEqual(root.data.name, "tree")
        self.assertNotIn("treemesh", bpy.data.objects)
        self.assertEqual(sorted(ob.name for ob in Trees.record().owned(root)), ["leaves", "tree", "tree_curves"])


@Verifies("SWR-0104")
class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_make_mesh_keeps_the_blossoms(self):
        blossoms = self.generate(windAnim=True, makeMesh=True)
        self.assertIn("Sapling Follow Wind", [m.name for m in blossoms.modifiers])


@Verifies("SWR-0107")
class RootSweep(unittest.TestCase):
    """The root is a mesh: the bark it sweeps has the old bevel's vertices and faces."""

    def test_export_writes_the_bark(self):
        self.assertEqual(Scene.generate(NodeTrees.settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        verts = NodeTrees.counts("tree").vertices
        for ob in bpy.context.view_layer.objects:
            ob.select_set(ob == root)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tree.obj"
            result = bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True, apply_modifiers=True)
            self.assertEqual(result, {"FINISHED"})
            lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(sum(line.startswith("v ") for line in lines), verts)
