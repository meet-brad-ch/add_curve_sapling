# SPDX-License-Identifier: GPL-3.0-or-later

"""Presets: old presets (the requirements each class or test names)."""

import json
import unittest

import bpy
from support.addon import Addon
from support.console import Console
from support.old_names import OldNames
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


@Verifies("SWR-0047")
class PresetDefaults(unittest.TestCase):
    """A preset that lacks settings loads with their defaults, and the operator says which ones."""

    def test_missing_settings_are_reported(self):
        values = Addon.preset_store().load("callistemon").values
        for name in ("bend", "rootFlare"):
            values.pop(name)
        path = Addon.preset_store().user_folder(create=True) / "lacking.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(repr(values), encoding="utf-8")
        Scene.reset()
        with Console.capture() as console:
            self.assertEqual(bpy.ops.curve.tree_add(preset="lacking", do_update=True), {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn("does not have 2 settings: bend, rootFlare", warnings[0])


@Verifies("SWR-0047")
class OlderTrees(unittest.TestCase):
    """A tree stores its settings; Edit failed on trees made before a setting existed ("missing [...]")."""

    def test_edit_fills_settings_added_since(self):
        import json

        Scene.reset()
        root = Trees.add()
        stored = json.loads(root[Trees.record().SETTINGS])
        default = Addon.operator_defaults()["rootFlare"]
        stored["settings"].pop("rootFlare")  # as if the tree came from a version without this setting
        root[Trees.record().SETTINGS] = json.dumps(stored)

        self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        self.assertEqual(Addon.stored_settings(Scene.active_object())["rootFlare"], default)


@Verifies("SWR-0047")
class EditReports(unittest.TestCase):
    """Edit Sapling Tree tells the user what it could not keep: objects whose part of the tree is gone, and
    settings an older tree did not store."""

    def test_settings_an_older_tree_lacks_are_reported_and_listed(self):
        import json

        Scene.reset()
        root = Trees.add()
        stored = json.loads(root[Trees.record().SETTINGS])
        stored["settings"].pop("rootFlare")
        root[Trees.record().SETTINGS] = json.dumps(stored)
        edit_class = Addon.module("build.tree_record").TreeEdit
        found = edit_class.claim(root.name, bpy.context.view_layer).stored(Addon.operator_defaults())
        self.assertEqual(found.missing, ["rootFlare"])
        self.assertIn("rootFlare", found.settings.values)
        with Console.capture() as console:
            self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn("does not have 1 settings: rootFlare", warnings[0])


@Verifies("SWR-0048")
class RenameKeys(unittest.TestCase):
    """Settings with the 0.3.x names move to the current names, and an old and a new name with different values fail.
    The old wind turns into the node wind only with the old armature on."""

    def test_every_old_key_moves(self):
        renamed = Addon.module("settings").TreeSettings
        values = {old: f"value of {old}" for old in renamed.RENAMED}
        result = renamed(values).rename_keys().values
        self.assertEqual(result, {new: f"value of {old}" for old, new in renamed.RENAMED.items()})

    def test_old_and_new_key_with_the_same_value(self):
        self.assertEqual(
            Addon.module("settings").TreeSettings({"wind": 2.0, "windStrength": 2.0}).rename_keys().values,
            {"windStrength": 2.0},
        )

    def test_old_and_new_key_disagree(self):
        with self.assertRaisesRegex(Addon.module("settings").SettingsError, "wind .*windStrength"):
            Addon.module("settings").TreeSettings({"wind": 2.0, "windStrength": 1.0}).rename_keys()

    def test_old_wind_without_armature_stays_still(self):
        """The old wind ran on the armature only; windAnim alone now makes the node wind."""
        for values, wind in (
            ({"armAnim": True, "useArm": False}, False),
            ({"armAnim": True}, False),
            ({"armAnim": True, "useArm": True}, True),
            ({"armAnim": True, "useRig": True}, True),
            ({"armAnim": False, "useArm": True}, False),
        ):
            with self.subTest(values=values):
                self.assertEqual(
                    Addon.module("settings").TreeSettings(dict(values)).rename_keys().values["windAnim"], wind
                )


@Verifies("SWR-0048")
class OldTrees(unittest.TestCase):
    """A tree generated before the rename stores the old ids; Edit loads them under the new ones."""

    def test_edit_a_tree_stored_with_old_ids(self):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, windStrength=2.5, jointStep=(1, 2, 1, 1), makeMesh=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        root = Scene.active_object()
        record = Addon.module("build.tree_record").TreeRecord
        stored = json.loads(root[record.SETTINGS])
        stored["settings"] = OldNames.with_old_names(stored["settings"])
        root[record.SETTINGS] = json.dumps(stored)

        self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        edited = Addon.stored_settings(Scene.active_object())
        self.assertEqual((edited["useRig"], edited["windAnim"], edited["windStrength"]), (True, True, 2.5))
        self.assertEqual(edited["jointStep"], [1, 2, 1, 1])
        self.assertNotIn("wind", edited)


@Verifies("SWR-0048")
class OldUserPresets(unittest.TestCase):
    """A user preset file with the 0.3.x setting names loads under the current names."""

    def test_user_preset_with_old_ids_loads(self):
        values = OldNames.with_old_names(Addon.resolve_preset("quaking_aspen.py"))
        values["wind"] = 3.0
        path = Addon.preset_store().user_folder(create=True) / "old names.py"
        path.write_text(repr(values), encoding="utf-8")
        self.addCleanup(path.unlink)
        loaded = Addon.preset_store().load("old names").values
        self.assertEqual(loaded["windStrength"], 3.0)
        self.assertFalse(set(Addon.module("settings").TreeSettings.RENAMED) & set(loaded))


@Verifies("SWR-0048")
class OldScriptCalls(unittest.TestCase):
    """bpy.ops.curve.tree_add(useArm=True, ...) as scripts wrote it before the rename."""

    def test_old_keywords_generate_under_the_new_ids(self):
        Scene.reset()
        settings = OldNames.with_old_names(Addon.resolve_preset("quaking_aspen.py"))
        settings.update(useArm=True, armAnim=True, wind=2.0, boneStep=(1, 1, 2, 1))
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        stored = Addon.stored_settings(Scene.active_object())
        self.assertEqual((stored["useRig"], stored["windAnim"], stored["windStrength"]), (True, True, 2.0))
        self.assertEqual(stored["jointStep"], [1, 1, 2, 1])

    def test_old_wind_keyword_without_armature_stays_still(self):
        Scene.reset()
        settings = OldNames.with_old_names(Addon.resolve_preset("quaking_aspen.py"))
        settings.update(armAnim=True)  # useArm stays off: the old wind needed the armature
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        stored = Addon.stored_settings(Scene.active_object())
        self.assertEqual((stored["useRig"], stored["windAnim"]), (False, False))
        self.assertNotIn("tree_wind", bpy.data.objects, "no node wind")

    def test_old_and_new_keyword_disagree(self):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(windStrength=1.0)
        with self.assertRaisesRegex(RuntimeError, "wind .*windStrength"):
            bpy.ops.curve.tree_add(**settings, wind=2.0, do_update=True)
