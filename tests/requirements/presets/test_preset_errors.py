# SPDX-License-Identifier: GPL-3.0-or-later

"""Presets: preset errors (the requirements each class or test names)."""

import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0046")
class PresetErrors(unittest.TestCase):
    """User preset files that cannot be used make the operator cancel with a clear message."""

    def write(self, name, text):
        """Write a user preset file with the name and the text, removed after the test."""
        path = Addon.preset_store().user_folder(create=True) / f"{name}.py"
        path.write_text(text, encoding="utf-8")
        self.addCleanup(path.unlink)

    def assert_add_fails(self, preset, message):
        """Adding a tree with the preset fails with the message, and the scene stays empty."""
        Scene.reset()
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
        values = Addon.preset_store().load("callistemon").values
        values["bogus"] = 1
        self.write("bogus", repr(values))
        self.assert_add_fails("bogus", r"unknown \['bogus'\]")

    def test_invalid_file_name_is_listed_not_hidden(self):
        self.write("bad name!", repr(Addon.preset_store().load("willow").values))
        (entry,) = [e for e in Addon.preset_store().entries() if e.name == "bad name!"]
        self.assertIn("invalid name", entry.problem)
        self.assert_add_fails("bad name!", "Rename the file")


@Verifies("SWR-0046")
class PresetApplication(unittest.TestCase):
    """Applying a preset with a setting that does not exist fails with a SettingsError that names the setting."""

    def apply(self, props, name, defaults):
        """Load the preset, fill its missing settings from the defaults and apply it to the properties."""
        names = Addon.generation_names()
        Addon.preset_store().load(name).complete(defaults).apply_to(props, names)

    OLD_PRESET_LACKS = (
        "flutterStrength", "flutterSpeed", "flutterRandomness", "jointLevels", "attractOut", "autoTaper",
        "baseSize_s", "jointStep", "branchDist", "closeTip", "customShape", "gustStrength", "gustFrequency",
        "horzLeaves", "leafFlutter", "leafDownAngle", "leafDownAngleV",
        "leafRotate", "leafRotateV", "leafScaleT", "leafScaleV", "leafangle", "loopFrames", "makeMesh", "minRadius",
        "nrings", "fastPreview", "pruneBase", "rMode", "radiusTweak", "rootFlare", "shapeS", "splitBias",
        "splitByLen", "splitHeight", "taperCrown", "useOldDownAngle", "useParentAngle", "windStrength",
    )  # fmt: skip

    def test_unknown_key_rejected(self):
        settings = Addon.preset_store().load("willow").complete(Addon.operator_defaults())
        settings.values["bogus"] = 1
        with self.assertRaisesRegex(Addon.module("settings").SettingsError, r"unknown \['bogus'\]"):
            settings.apply_to(SimpleNamespace(), Addon.generation_names())


@Verifies("SWR-0046")
class PresetFileErrors(unittest.TestCase):
    """Preset files with the right syntax but the wrong content cancel with a message naming the cause."""

    def write(self, name, text):
        """Write a user preset file with the name and the text, removed after the test."""
        path = Addon.preset_store().user_folder(create=True) / f"{name}.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_short_angle_list(self):
        self.write(
            "short", "{'levels': 3, 'attractUp': 1, 'downAngle': [1], 'downAngleV': [1], 'rotate': [1], 'rotateV': [1]}"
        )
        with self.assertRaisesRegex(Addon.module("presets").PresetError, "downAngle has 1 values; 4 are needed"):
            Addon.preset_store().load("short")

    def test_unhashable_key(self):
        self.write("unhashable", "{[1]: 2}")
        with self.assertRaisesRegex(Addon.module("presets").PresetError, "Cannot read preset unhashable.py"):
            Addon.preset_store().load("unhashable")


@Verifies("SWR-0046")
class SettingsShape(unittest.TestCase):
    """Settings of the wrong shape are SettingsErrors naming the problem; older shapes are brought up to date."""

    def settings(self):
        """The add-on's TreeSettings class."""
        return Addon.module("settings").TreeSettings

    def test_not_a_dictionary(self):
        with self.assertRaisesRegex(Addon.module("settings").SettingsError, "must be a dictionary, not list"):
            self.settings()([1])

    def test_levels_must_be_an_integer(self):
        values = {"levels": "3", "attractUp": [0, 0, 0, 0], "leafDownAngle": 45}
        with self.assertRaisesRegex(Addon.module("settings").SettingsError, "levels must be an integer, not str"):
            self.settings()(values).migrate()

    def test_one_vertical_attraction_for_all_levels(self):
        values = {"levels": 3, "attractUp": 0.5, "leafDownAngle": 45}
        self.assertEqual(self.settings()(values).migrate().values["attractUp"], [0, 0, 0.5, 0.5])

    def test_preset_not_found(self):
        with self.assertRaisesRegex(Addon.module("presets").PresetError, "Preset 'nowhere' not found"):
            Addon.preset_store().load("nowhere")

    def test_preset_that_is_not_utf8(self):
        path = Addon.preset_store().user_folder(create=True) / "latin.py"
        self.addCleanup(path.unlink, missing_ok=True)
        path.write_bytes("{'name': 'caf\xe9'}".encode("latin-1"))
        with self.assertRaisesRegex(Addon.module("presets").PresetError, "Cannot read preset latin.py"):
            Addon.preset_store().load("latin")
