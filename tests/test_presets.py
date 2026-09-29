# SPDX-License-Identifier: GPL-3.0-or-later

"""Presets: complete application, and every error path failing visibly."""

import unittest
from types import SimpleNamespace

import bpy
import helpers


def store():
    return helpers.module("presets").PresetStore.for_addon()


class PresetApplication(unittest.TestCase):
    def apply(self, props, name, defaults):
        names = helpers.generation_names()
        store().load(name).complete(defaults).apply_to(props, names)

    def test_order_independent(self):
        """A preset sets every setting: before, willow kept ~35 values of the preset loaded before it."""
        defaults = helpers.operator_defaults()
        after_other = SimpleNamespace(**defaults)
        self.apply(after_other, "callistemon", defaults)
        self.apply(after_other, "willow", defaults)
        fresh = SimpleNamespace(**defaults)
        self.apply(fresh, "willow", defaults)
        self.assertEqual(vars(after_other), vars(fresh))

    def test_unknown_key_rejected(self):
        settings = store().load("willow").complete(helpers.operator_defaults())
        settings.values["bogus"] = 1
        with self.assertRaisesRegex(helpers.module("settings").SettingsError, r"unknown \['bogus'\]"):
            settings.apply_to(SimpleNamespace(), helpers.generation_names())


class PresetErrors(unittest.TestCase):
    """User preset files that cannot be used make the operator cancel with a clear message."""

    def write(self, name, text):
        path = store().user_folder(create=True) / f"{name}.py"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(path.unlink)

    def assert_add_fails(self, preset, message):
        helpers.reset_scene()
        with self.assertRaisesRegex(RuntimeError, message):
            bpy.ops.curve.tree_add(preset=preset, do_update=True)
        self.assertEqual(len(bpy.data.objects), 0)

    def test_unreadable(self):
        self.write("broken", "{'levels': ")
        self.assert_add_fails("broken", "Cannot read preset broken.py")

    def test_not_a_dictionary(self):
        self.write("listy", "[1, 2]")
        self.assert_add_fails("listy", "not a settings dictionary")

    def test_incomplete(self):
        self.write("tiny", "{'levels': 3}")
        self.assert_add_fails("tiny", "incomplete or malformed")

    def test_unknown_key(self):
        values = store().load("callistemon").values
        values["bogus"] = 1
        self.write("bogus", repr(values))
        self.assert_add_fails("bogus", r"unknown \['bogus'\]")

    def test_invalid_file_name_is_listed_not_hidden(self):
        self.write("bad name!", repr(store().load("willow").values))
        (entry,) = [e for e in store().entries() if e.name == "bad name!"]
        self.assertIn("invalid name", entry.problem)
        self.assert_add_fails("bad name!", "rename the file")

    def test_save_rejects_bad_settings(self):
        for settings, message in (("", "Invalid settings JSON"), ("null", "not version 1 settings")):
            with self.subTest(settings=settings), self.assertRaisesRegex(RuntimeError, message):
                bpy.ops.sapling.preset_save(name="whatever", overwrite=False, settings=settings)

    def test_save_through_operator_round_trips(self):
        settings = store().load("quaking_aspen")
        self.assertEqual(
            bpy.ops.sapling.preset_save(name="saved tree", overwrite=True, settings=settings.to_json()), {"FINISHED"}
        )
        self.addCleanup((store().user_folder(create=False) / "saved tree.py").unlink)
        normalized = helpers.module("settings").TreeSettings.from_json
        self.assertEqual(normalized(store().load("saved tree").to_json()).values, normalized(settings.to_json()).values)
