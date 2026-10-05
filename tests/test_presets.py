# SPDX-License-Identifier: GPL-3.0-or-later

"""Presets: complete application, and every error path failing visibly."""

import unittest
from types import SimpleNamespace

import bpy
import helpers

store = helpers.preset_store


class PresetApplication(unittest.TestCase):
    def apply(self, props, name, defaults):
        names = helpers.generation_names()
        store().load(name).complete(defaults).apply_to(props, names)

    # The settings the old willow preset (0.3.7) did not have: a real preset from an older version
    OLD_PRESET_LACKS = (
        "flutterStrength", "flutterSpeed", "flutterRandomness", "jointLevels", "attractOut", "autoTaper",
        "baseSize_s", "jointStep", "branchDist", "closeTip", "customShape", "gustStrength", "gustFrequency",
        "horzLeaves", "leafFlutter", "leafDownAngle", "leafDownAngleV",
        "leafRotate", "leafRotateV", "leafScaleT", "leafScaleV", "leafangle", "loopFrames", "makeMesh", "minRadius",
        "nrings", "fastPreview", "pruneBase", "rMode", "radiusTweak", "rootFlare", "shapeS", "splitBias",
        "splitByLen", "splitHeight", "taperCrown", "useOldDownAngle", "useParentAngle", "windStrength",
    )  # fmt: skip

    def test_order_independent(self):
        """A preset sets every setting: before, an older preset (willow lacked 39) kept the values of the one loaded
        before it."""
        defaults = helpers.operator_defaults()
        callistemon = store().load("callistemon").values
        partial = {k: v for k, v in callistemon.items() if k not in self.OLD_PRESET_LACKS}
        path = store().user_folder(create=True) / "old tree.py"
        path.write_text(repr(partial), encoding="utf-8")
        self.addCleanup(path.unlink)

        after_other = SimpleNamespace(**defaults)
        self.apply(after_other, "small_pine", defaults)
        self.apply(after_other, "old tree", defaults)
        fresh = SimpleNamespace(**defaults)
        self.apply(fresh, "old tree", defaults)
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
        self.assert_add_fails("tiny", r"tiny.py: Settings do not have \['attractUp'")

    def test_unknown_key(self):
        values = store().load("callistemon").values
        values["bogus"] = 1
        self.write("bogus", repr(values))
        self.assert_add_fails("bogus", r"unknown \['bogus'\]")

    def test_invalid_file_name_is_listed_not_hidden(self):
        self.write("bad name!", repr(store().load("willow").values))
        (entry,) = [e for e in store().entries() if e.name == "bad name!"]
        self.assertIn("invalid name", entry.problem)
        self.assert_add_fails("bad name!", "Rename the file")

    def test_save_rejects_bad_settings(self):
        for settings, message in (("", "Invalid settings JSON"), ("null", "version 1 settings object; got NoneType")):
            with self.subTest(settings=settings), self.assertRaisesRegex(RuntimeError, message):
                bpy.ops.sapling.preset_save(name="whatever", overwrite=False, settings=settings)

    def test_save_through_operator_round_trips(self):
        settings = store().load("quaking_aspen")
        saved = store().user_folder(create=True) / "saved tree.py"
        self.addCleanup(saved.unlink, missing_ok=True)  # registered first: a failing save leaves no file behind
        self.assertEqual(
            bpy.ops.sapling.preset_save(name="saved tree", overwrite=True, settings=settings.to_json()), {"FINISHED"}
        )
        normalized = helpers.module("settings").TreeSettings.from_json
        self.assertEqual(normalized(store().load("saved tree").to_json()).values, normalized(settings.to_json()).values)


class BuiltinPresets(unittest.TestCase):
    """Every built-in preset sets every generation setting and needs no migration: loading one fills nothing in."""

    def test_complete_and_current(self):
        import ast

        defaults = helpers.operator_defaults()
        for entry in store().entries():
            if not entry.builtin:
                continue
            with self.subTest(preset=entry.name):
                self.assertEqual(store().load(entry.name).missing(defaults), [])
                path = store().builtin / f"{entry.name}.py"
                body = "\n".join(
                    line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
                )
                values = ast.literal_eval(body.strip())
                migrated = helpers.module("settings").TreeSettings(dict(values)).migrate().values
                self.assertEqual(migrated, values)


class PresetDefaults(unittest.TestCase):
    """A preset that lacks settings loads with their defaults, and the operator says which ones."""

    def test_missing_settings_are_reported(self):
        values = store().load("callistemon").values
        for name in ("bend", "rootFlare"):
            values.pop(name)
        path = store().user_folder(create=True) / "lacking.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(repr(values), encoding="utf-8")
        helpers.reset_scene()
        with helpers.console_output() as console:
            self.assertEqual(bpy.ops.curve.tree_add(preset="lacking", do_update=True), {"FINISHED"})
        warnings = console.lines("Warning")
        self.assertEqual(len(warnings), 1, console.text)
        self.assertIn("does not have 2 settings: bend, rootFlare", warnings[0])

    def test_limit_import(self):
        settings = store().load("quaking_aspen")
        settings.values["levels"] = 4
        settings.values["showLeaves"] = True
        settings.limit_import()
        self.assertEqual((settings.values["levels"], settings.values["showLeaves"]), (2, False))


class PresetFileErrors(unittest.TestCase):
    """Preset files with the right syntax but the wrong content cancel with a message naming the cause."""

    def write(self, name, text):
        path = store().user_folder(create=True) / f"{name}.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_short_angle_list(self):
        self.write(
            "short", "{'levels': 3, 'attractUp': 1, 'downAngle': [1], 'downAngleV': [1], 'rotate': [1], 'rotateV': [1]}"
        )
        with self.assertRaisesRegex(helpers.module("presets").PresetError, "downAngle has 1 values; 4 are needed"):
            store().load("short")

    def test_unhashable_key(self):
        self.write("unhashable", "{[1]: 2}")
        with self.assertRaisesRegex(helpers.module("presets").PresetError, "Cannot read preset unhashable.py"):
            store().load("unhashable")


class SettingsShape(unittest.TestCase):
    """Settings of the wrong shape are SettingsErrors naming the problem; older shapes are brought up to date."""

    def settings(self):
        return helpers.module("settings").TreeSettings

    def test_not_a_dictionary(self):
        with self.assertRaisesRegex(helpers.module("settings").SettingsError, "must be a dictionary, not list"):
            self.settings()([1])

    def test_levels_must_be_an_integer(self):
        values = {"levels": "3", "attractUp": [0, 0, 0, 0], "leafDownAngle": 45}
        with self.assertRaisesRegex(helpers.module("settings").SettingsError, "levels must be an integer, not str"):
            self.settings()(values).migrate()

    def test_one_vertical_attraction_for_all_levels(self):
        values = {"levels": 3, "attractUp": 0.5, "leafDownAngle": 45}
        self.assertEqual(self.settings()(values).migrate().values["attractUp"], [0, 0, 0.5, 0.5])

    def test_preset_not_found(self):
        with self.assertRaisesRegex(helpers.module("presets").PresetError, "Preset 'nowhere' not found"):
            store().load("nowhere")

    def test_preset_that_is_not_utf8(self):
        path = store().user_folder(create=True) / "latin.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_bytes("{'name': 'caf\xe9'}".encode("latin-1"))
        with self.assertRaisesRegex(helpers.module("presets").PresetError, "Cannot read preset latin.py"):
            store().load("latin")
