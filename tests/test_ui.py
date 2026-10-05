# SPDX-License-Identifier: GPL-3.0-or-later

"""Operator, presets, settings pages, placement and re-editing a generated tree."""

import unittest
from types import SimpleNamespace

import bpy
import helpers
from golden_cases import PRESETS
from mathutils import Matrix


def root_of(ob):
    return helpers.module("build.tree_record").TreeRecord.root_of(ob)


class Registration(unittest.TestCase):
    def test_reregister(self):
        self.addCleanup(bpy.ops.preferences.addon_enable, module=helpers.MODULE)  # enabled again if a step fails
        for _ in range(2):
            bpy.ops.preferences.addon_disable(module=helpers.MODULE)
            self.assertFalse(hasattr(bpy.types, "VIEW3D_PT_sapling_tree"))
            bpy.ops.preferences.addon_enable(module=helpers.MODULE)
        self.assertIsNotNone(bpy.types.Operator.bl_rna_get_subclass_py("CURVE_OT_tree_add"))


class Presets(unittest.TestCase):
    def store(self):
        return helpers.preset_store()

    def test_limit_import_is_off_by_default(self):
        """With Limit Import on, presets loaded with 2 levels and no leaves, and multi-level trees looked bare."""
        prop = bpy.ops.curve.tree_add.get_rna_type().properties["limitImport"]
        self.assertFalse(prop.default)

    def test_builtin_presets_load(self):
        names = [e.name for e in self.store().entries() if e.builtin]
        self.assertEqual(sorted(names), sorted(PRESETS))
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

    def add_preset(self, **options):
        helpers.reset_scene()
        self.assertEqual(bpy.ops.curve.tree_add(preset="douglas_fir", do_update=True, **options), {"FINISHED"})
        return helpers.module("build.tree_record").TreeRecord.settings(bpy.context.active_object).values

    def test_operator_applies_preset(self):
        stored = self.add_preset()
        preset = self.store().load("douglas_fir").values
        self.assertEqual(stored["levels"], preset["levels"])
        self.assertEqual(stored["showLeaves"], preset["showLeaves"])
        self.assertEqual(stored["branches"], list(preset["branches"]))

    def test_limit_import_caps_levels_and_hides_leaves(self):
        stored = self.add_preset(limitImport=True)
        preset = self.store().load("douglas_fir").values
        self.assertGreater(preset["levels"], 2)
        self.assertEqual(stored["levels"], 2)
        self.assertFalse(stored["showLeaves"])


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
        self.instance = helpers.add_leaf_card()
        result = bpy.ops.curve.tree_add(**settings, leafDupliObj=self.instance.name, do_update=True)
        self.assertEqual(result, {"FINISHED"})
        return bpy.context.active_object

    def assert_same_transform(self, a, b):
        self.assertLess((a.to_translation() - b.to_translation()).length, 1e-5)
        self.assertLess(a.to_quaternion().rotation_difference(b.to_quaternion()).angle, 1e-5)
        self.assertLess((a.to_scale() - b.to_scale()).length, 1e-5)

    def test_settings_stored_on_root(self):
        root = self.generate(useRig=True)
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        stored = helpers.stored_settings(root)
        self.assertTrue(stored["useRig"])
        self.assertEqual(stored["leafDupliObj"], helpers.LEAF_CARD)
        tree_id = root["sapling_tree"]
        tagged = sorted(ob.name for ob in bpy.data.objects if ob.get("sapling_tree") == tree_id)
        self.assertEqual(tagged, ["leaves", "tree", "treeArm", "tree_curves", "tree_joints"])

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
        splines = len(helpers.spline_points())
        self.assertEqual(
            bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **self._stored(), levels=1, do_update=True),
            {"FINISHED"},
        )
        self.assertLess(len(helpers.spline_points()), splines)
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
        original = builder.__dict__["_branch_bones"]  # the staticmethod itself, put back as it was

        def recording(*args):
            modes.append(other.mode)
            return original.__func__(*args)

        builder._branch_bones = staticmethod(recording)
        self.addCleanup(setattr, builder, "_branch_bones", original)
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        self.assertEqual(modes, ["OBJECT"], "the other armature stays in Object Mode while bones are made")
        self.assertEqual(len(other.data.bones), 0)
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(bpy.context.active_object.location.to_tuple(), (0.0, 0.0, 0.0))


class ArmatureDisplay(unittest.TestCase):
    """The tree mesh is the root, the armature its child; the bones are hidden, the root never is."""

    def add(self, **changes):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, **changes)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        root = helpers.active_object()
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        (armature,) = [ob for ob in root.children if ob.type == "ARMATURE"]
        (collection,) = armature.data.collections
        return root, armature, collection

    def assert_selected_and_movable(self, root):
        self.assertTrue(root.visible_get())
        self.assertTrue(root.select_get())
        editable = bpy.context.selected_editable_objects
        if editable is None:
            raise AssertionError("no selected_editable_objects in this context")
        self.assertIn(root, editable)

    def test_bones_hidden_tree_selected_and_movable(self):
        root, armature, collection = self.add()
        self.assertEqual(collection.name, "Sapling Bones")
        self.assertFalse(collection.is_visible)
        self.assertEqual(len(collection.bones), len(armature.data.bones))
        self.assertGreater(len(armature.data.bones), 10)
        self.assert_selected_and_movable(root)

    def test_fast_preview_draws_the_tree_as_bounds_and_shows_the_bones(self):
        root, _armature, collection = self.add(fastPreview=True)
        self.assertTrue(collection.is_visible)
        self.assertEqual(root.display_type, "BOUNDS")
        self.assert_selected_and_movable(root)

    def test_hidden_bones_still_deform(self):
        self.add(showLeaves=True, windAnim=True)
        leaves = bpy.data.objects["leaves"]
        scene = bpy.context.scene
        positions = []
        for frame in (1, 17):
            scene.frame_set(frame)
            mesh = leaves.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
            positions.append([v.co.copy() for v in mesh.vertices[:50]])
        self.assertTrue(any((a - b).length > 1e-6 for a, b in zip(*positions, strict=True)), "leaves do not sway")


class RedoPanel(unittest.TestCase):
    """In the redo panel, a change of page or other UI state keeps the tree (execute passes through); a setting
    change regenerates it; a settings error cancels with its message. Blender sets is_repeat only for its own redo,
    so execute runs on a stand-in operator."""

    def operator(self, **values):
        reports = []
        stand_in = SimpleNamespace(
            options=SimpleNamespace(is_repeat=True), report=lambda kind, text: reports.append(text), **values
        )
        return stand_in, reports

    def execute(self, stand_in):
        return helpers.module("ui.operators").AddTreeOperator.execute(stand_in, bpy.context)

    def test_ui_state_passes_through(self):
        stand_in, _reports = self.operator(do_update=False)
        self.assertEqual(self.execute(stand_in), {"PASS_THROUGH"})

    def test_a_setting_change_regenerates(self):
        stand_in, _reports = self.operator(do_update=True, _generate=lambda context: {"FINISHED"})
        self.assertEqual(self.execute(stand_in), {"FINISHED"})

    def test_a_settings_error_cancels_with_its_message(self):
        error = helpers.module("settings").SettingsError("Leaf Object 'x' is not an object")

        def failing(context):
            raise error

        stand_in, reports = self.operator(do_update=True, _generate=failing)
        self.assertEqual(self.execute(stand_in), {"CANCELLED"})
        self.assertEqual(reports, [str(error)])


class UpdateCallbacks(unittest.TestCase):
    """A setting's update callback decides whether the next run regenerates the tree."""

    def properties(self):
        return helpers.module("ui.properties").TreeProperties

    def test_a_leaf_setting_regenerates_only_with_leaves_shown(self):
        for shown in (False, True):
            with self.subTest(show_leaves=shown):
                props = SimpleNamespace(showLeaves=shown, do_update=not shown)
                self.properties().update_leaves(props, None)
                self.assertEqual(props.do_update, shown)

    def test_generation_and_ui_settings(self):
        props = SimpleNamespace(do_update=False)
        self.properties().update_tree(props, None)
        self.assertTrue(props.do_update)
        self.properties().no_update_tree(props, None)
        self.assertFalse(props.do_update)


class NoActiveCollection(unittest.TestCase):
    """Without an active collection the operator cancels with a message (not a traceback), and makes nothing."""

    def test_add_without_a_collection_cancels(self):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        with bpy.context.temp_override(collection=None), self.assertRaisesRegex(RuntimeError, "No active collection"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
        self.assertEqual(len(bpy.data.objects), 0)
