# SPDX-License-Identifier: GPL-3.0-or-later

"""The wind and armature settings were renamed: old presets, stored trees and scripts keep working."""

import json
import unittest

import bpy
import helpers


def settings_class():
    return helpers.module("settings").TreeSettings


def store():
    return helpers.module("presets").PresetStore.for_addon()


def with_old_names(values):
    """The same settings under their old ids."""
    old_of = {new: old for old, new in settings_class().RENAMED.items()}
    return {old_of.get(key, key): value for key, value in values.items()}


class RenameKeys(unittest.TestCase):
    def test_every_old_key_moves(self):
        renamed = settings_class()
        values = {old: f"value of {old}" for old in renamed.RENAMED}
        result = renamed(values).rename_keys().values
        self.assertEqual(result, {new: f"value of {old}" for old, new in renamed.RENAMED.items()})

    def test_old_and_new_key_with_the_same_value(self):
        self.assertEqual(
            settings_class()({"wind": 2.0, "windStrength": 2.0}).rename_keys().values, {"windStrength": 2.0}
        )

    def test_old_and_new_key_disagree(self):
        with self.assertRaisesRegex(helpers.module("settings").SettingsError, "wind .*windStrength"):
            settings_class()({"wind": 2.0, "windStrength": 1.0}).rename_keys()

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
                self.assertEqual(settings_class()(dict(values)).rename_keys().values["windAnim"], wind)


class OldTrees(unittest.TestCase):
    """A tree generated before the rename stores the old ids; Edit loads them under the new ones."""

    def test_edit_a_tree_stored_with_old_ids(self):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, windStrength=2.5, jointStep=(1, 2, 1, 1), makeMesh=True)
        self.assertEqual(helpers.generate(settings), {"FINISHED"})
        root = helpers.active_object()
        record = helpers.module("build.tree_record").TreeRecord
        stored = json.loads(root[record.SETTINGS])
        stored["settings"] = with_old_names(stored["settings"])
        root[record.SETTINGS] = json.dumps(stored)

        self.assertEqual(bpy.ops.curve.tree_add(replace=root.name, do_update=True), {"FINISHED"})
        edited = helpers.stored_settings(helpers.active_object())
        self.assertEqual((edited["useRig"], edited["windAnim"], edited["windStrength"]), (True, True, 2.5))
        self.assertEqual(edited["jointStep"], [1, 2, 1, 1])
        self.assertNotIn("wind", edited)


class OldUserPresets(unittest.TestCase):
    def test_user_preset_with_old_ids_loads(self):
        values = with_old_names(helpers.resolve_preset("quaking_aspen.py"))
        values["wind"] = 3.0
        path = store().user_folder(create=True) / "old names.py"
        path.write_text(repr(values), encoding="utf-8")
        self.addCleanup(path.unlink)
        loaded = store().load("old names").values
        self.assertEqual(loaded["windStrength"], 3.0)
        self.assertFalse(set(settings_class().RENAMED) & set(loaded))


class OldScriptCalls(unittest.TestCase):
    """bpy.ops.curve.tree_add(useArm=True, ...) as scripts wrote it before the rename."""

    def test_old_keywords_generate_under_the_new_ids(self):
        helpers.reset_scene()
        settings = with_old_names(helpers.resolve_preset("quaking_aspen.py"))
        settings.update(useArm=True, armAnim=True, wind=2.0, boneStep=(1, 1, 2, 1))
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        stored = helpers.stored_settings(helpers.active_object())
        self.assertEqual((stored["useRig"], stored["windAnim"], stored["windStrength"]), (True, True, 2.0))
        self.assertEqual(stored["jointStep"], [1, 1, 2, 1])

    def test_old_wind_keyword_without_armature_stays_still(self):
        helpers.reset_scene()
        settings = with_old_names(helpers.resolve_preset("quaking_aspen.py"))
        settings.update(armAnim=True)  # useArm stays off: the old wind needed the armature
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        stored = helpers.stored_settings(helpers.active_object())
        self.assertEqual((stored["useRig"], stored["windAnim"]), (False, False))
        self.assertFalse(helpers.tree_curves().modifiers, "no node wind")

    def test_old_and_new_keyword_disagree(self):
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(windStrength=1.0)
        with self.assertRaisesRegex(RuntimeError, "wind .*windStrength"):
            bpy.ops.curve.tree_add(**settings, wind=2.0, do_update=True)
