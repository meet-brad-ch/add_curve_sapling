# SPDX-License-Identifier: GPL-3.0-or-later

"""Operator, presets, settings pages, placement and re-editing a generated tree."""

import re
import unittest
from pathlib import Path

import bpy
import helpers
from mathutils import Matrix

SOURCE = Path(__file__).resolve().parent.parent / "source"


def root_of(ob):
    return helpers.module("build.tree_record").TreeRecord.root_of(ob)


class Registration(unittest.TestCase):
    def test_reregister(self):
        for _ in range(2):
            bpy.ops.preferences.addon_disable(module=helpers.MODULE)
            self.addCleanup(bpy.ops.preferences.addon_enable, module=helpers.MODULE)
            self.assertFalse(hasattr(bpy.types, "VIEW3D_PT_sapling_tree"))
            bpy.ops.preferences.addon_enable(module=helpers.MODULE)
        self.assertIsNotNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))

    def test_pages_draw_existing_properties(self):
        text = (SOURCE / "ui" / "pages.py").read_text(encoding="utf-8")
        drawn = set(re.findall(r'\.prop\(props, "(\w+)"', text))
        self.assertGreater(len(drawn), 60)
        self.assertEqual(drawn - set(helpers.operator_property_names()), set())

    def test_every_generation_property_is_drawn(self):
        text = (SOURCE / "ui" / "pages.py").read_text(encoding="utf-8")
        drawn = set(re.findall(r'\.prop\(props, "(\w+)"', text))
        hidden = {"bend"}  # Leaf Bend has no control, as in earlier versions
        names = set(helpers.module("ui.operators").AddTreeOperator.generation_names())
        self.assertEqual(names - drawn - hidden, set())


class Presets(unittest.TestCase):
    def store(self):
        return helpers.module("presets").PresetStore.for_addon()

    def test_builtin_presets_load(self):
        names = [e.name for e in self.store().entries() if e.builtin]
        self.assertEqual(len(names), 9)
        generation = set(helpers.module("ui.operators").AddTreeOperator.generation_names())
        for name in names:
            with self.subTest(preset=name):
                values = self.store().load(name).values
                self.assertEqual(set(values) - generation, set())

    def test_save_and_load_round_trip(self):
        store = self.store()
        settings = store.load("quaking_aspen")
        path = store.save("my tree", settings, overwrite=True)
        try:
            self.assertEqual(store.load("my tree").values, settings.values)
            self.assertIn(("my tree", False, None), [(e.name, e.builtin, e.problem) for e in store.entries()])
            with self.assertRaises(helpers.module("presets").PresetError):
                store.save("my tree", settings, overwrite=False)  # exists
        finally:
            path.unlink()

    def test_rejected_names(self):
        store = self.store()
        settings = store.load("willow")
        for name in ("", "..\\evil", "../evil", "a/b", "C:\\x", "willow", "Willow", ".hidden", "CON", "x" * 65):
            with self.subTest(name=name), self.assertRaises(helpers.module("presets").PresetError):
                store.save(name, settings, overwrite=True)

    def test_operator_applies_preset(self):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.curve.tree_add(preset="douglas_fir", do_update=True), {"FINISHED"})
        stored = helpers.module("build.tree_record").TreeRecord.settings(bpy.context.active_object).values
        preset = self.store().load("douglas_fir").values
        self.assertEqual(stored["levels"], min(preset["levels"], 2))  # Limit Import
        self.assertFalse(stored["showLeaves"])
        self.assertEqual(stored["branches"], list(preset["branches"]))


class Placement(unittest.TestCase):
    def test_new_tree_at_cursor_selected_and_active(self):
        helpers.reset_scene()
        other = bpy.data.objects.new("other", None)
        bpy.context.scene.collection.objects.link(other)
        other.select_set(True)
        bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
        try:
            settings = helpers.resolve_preset("quaking_aspen.py")
            self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        finally:
            bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
        root = bpy.context.active_object
        self.assertEqual(root_of(root), root)
        self.assertEqual(root.location.to_tuple(), (1.0, 2.0, 3.0))
        self.assertEqual(bpy.context.selected_objects, [root])


class ReEdit(unittest.TestCase):
    """Edit Sapling Tree: regenerate from the settings stored on the tree, in the same place."""

    def generate(self, **overrides):
        settings = helpers.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", **overrides)
        helpers.reset_scene()
        self.instance = bpy.data.objects.new("leaf_card", bpy.data.meshes.new("leaf_card"))
        bpy.context.scene.collection.objects.link(self.instance)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, leafDupliObj="leaf_card", do_update=True), {"FINISHED"})
        return bpy.context.active_object

    def assert_same_transform(self, a, b):
        self.assertLess((a.to_translation() - b.to_translation()).length, 1e-5)
        self.assertLess(a.to_quaternion().rotation_difference(b.to_quaternion()).angle, 1e-5)
        self.assertLess((a.to_scale() - b.to_scale()).length, 1e-5)

    def test_settings_stored_on_root(self):
        root = self.generate(useArm=True)
        self.assertEqual(root.type, "ARMATURE")
        stored = helpers.stored_settings(root)
        self.assertTrue(stored["useArm"])
        self.assertEqual(stored["leafDupliObj"], "leaf_card")
        tree_id = root["sapling_tree"]
        tagged = sorted(ob.name for ob in bpy.data.objects if ob.get("sapling_tree") == tree_id)
        self.assertEqual(tagged, ["leaves", "tree", "treeArm"])

    def test_regenerate_in_place(self):
        root = self.generate()
        before = helpers.fingerprint()
        root.matrix_world = Matrix.Translation((5, 0, 0)) @ Matrix.Rotation(0.5, 4, "Z")
        bpy.context.view_layer.update()
        placed = root.matrix_world.copy()
        card_world = self.instance.matrix_world.copy()
        count = len(bpy.data.objects)

        self.assertEqual(bpy.ops.curve.tree_add("INVOKE_DEFAULT", replace=root.name), {"FINISHED"})

        new_root = bpy.context.active_object
        bpy.context.view_layer.update()
        self.assertEqual(len(bpy.data.objects), count)
        self.assertEqual(new_root.name, "tree")
        self.assert_same_transform(new_root.matrix_world, placed)
        self.assertEqual(self.instance.parent, bpy.data.objects["leaves"])
        self.assert_same_transform(self.instance.matrix_world, card_world)
        self.assertEqual(helpers.fingerprint(), before)

    def test_edit_changes_settings(self):
        root = self.generate()
        splines = len(root.data.splines)
        self.assertEqual(
            bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **self._stored(), levels=1, do_update=True),
            {"FINISHED"},
        )
        self.assertLess(len(bpy.data.objects["tree"].data.splines), splines)
        self.assertNotIn("tree.001", bpy.data.objects)

    def test_not_a_tree(self):
        helpers.reset_scene()
        ob = bpy.data.objects.new("plain", None)
        bpy.context.scene.collection.objects.link(ob)
        with self.assertRaisesRegex(RuntimeError, "'plain' is not part of a Sapling tree"):
            bpy.ops.curve.tree_add(replace="plain", do_update=True)

    @staticmethod
    def _stored():
        values = helpers.stored_settings(bpy.data.objects["tree"])
        values.pop("levels")
        return values


class ArmatureContext(unittest.TestCase):
    def test_other_selected_armature_is_not_edited(self):
        helpers.reset_scene()
        other = bpy.data.objects.new("other_rig", bpy.data.armatures.new("other_rig"))
        bpy.context.scene.collection.objects.link(other)
        other.select_set(True)
        bpy.context.view_layer.objects.active = other
        modes = []
        builder = helpers.module("build.armature").ArmatureBuilder
        original = builder._branch_bones

        def recording(builder_self, *args):
            modes.append(other.mode)
            return original(builder_self, *args)

        builder._branch_bones = recording
        self.addCleanup(setattr, builder, "_branch_bones", original)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useArm=True)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        self.assertEqual(modes, ["OBJECT"], "the other armature stays in Object Mode while bones are made")
        self.assertEqual(len(other.data.bones), 0)
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(bpy.context.active_object.location.to_tuple(), (0.0, 0.0, 0.0))
