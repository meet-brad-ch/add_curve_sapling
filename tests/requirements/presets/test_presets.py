# SPDX-License-Identifier: GPL-3.0-or-later

"""Presets: presets (the requirements each class or test names)."""

import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon
from support.golden_cases import PRESETS
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0040")
class SmokePresets(unittest.TestCase):
    """Each built-in preset generates a tree."""

    def test_every_preset_generates(self):
        for name in PRESETS:
            with self.subTest(preset=name):
                settings = Addon.resolve_preset(f"{name}.py")
                self.assertEqual(Scene.generate(settings), {"FINISHED"})
                self.assertIn("tree", bpy.data.objects)


class UiPresets(unittest.TestCase):
    """The preset store lists and loads the built-in presets, saves user presets and refuses bad names.
    The operator applies a chosen preset to the tree that it adds."""

    def store(self):
        """The add-on's preset store."""
        return Addon.preset_store()

    @Verifies("SWR-0040")
    def test_builtin_presets_load(self):
        names = [e.name for e in self.store().entries() if e.builtin]
        self.assertEqual(sorted(names), sorted(PRESETS))
        generation = set(Addon.module("ui.operators").AddTreeOperator.generation_names())
        for name in names:
            with self.subTest(preset=name):
                values = self.store().load(name).values
                self.assertEqual(set(values) - generation, set())

    @Verifies("SWR-0043")
    def test_save_and_load_round_trip(self):
        store = self.store()
        settings = store.load("quaking_aspen")
        path = store.save("my tree", settings, overwrite=True)
        try:
            self.assertEqual(store.load("my tree").values, settings.values)
            self.assertIn(("my tree", False, None), [(e.name, e.builtin, e.problem) for e in store.entries()])
            with self.assertRaises(Addon.module("presets").PresetError):
                store.save("my tree", settings, overwrite=False)  # exists
        finally:
            path.unlink()

    @Verifies("SWR-0044")
    def test_rejected_names(self):
        store = self.store()
        settings = store.load("weeping_willow")
        for name in (
            "",
            "..\\evil",
            "../evil",
            "a/b",
            "C:\\x",
            "weeping_willow",
            "Weeping_Willow",
            ".hidden",
            "CON",
            "x" * 65,
        ):
            with self.subTest(name=name), self.assertRaises(Addon.module("presets").PresetError):
                store.save(name, settings, overwrite=True)

    def add_preset(self, **options):
        """Add a Douglas fir from its preset in an empty scene, with the options, and return the stored settings."""
        Scene.reset()
        self.assertEqual(bpy.ops.curve.tree_add(preset="douglas_fir", do_update=True, **options), {"FINISHED"})
        return Addon.module("build.tree_record").TreeRecord.settings(bpy.context.active_object).values

    @Verifies("SWR-0042")
    def test_operator_applies_preset(self):
        stored = self.add_preset()
        preset = self.store().load("douglas_fir").values
        self.assertEqual(stored["levels"], preset["levels"])
        self.assertEqual(stored["showLeaves"], preset["showLeaves"])
        self.assertEqual(stored["branches"], list(preset["branches"]))


@Verifies("SWR-0041")
class PresetApplication(unittest.TestCase):
    """A preset sets every setting: the result of an old preset does not depend on the preset loaded before it."""

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

    def test_order_independent(self):
        """A preset sets every setting: before, an older preset (willow lacked 39) kept the values of the one loaded
        before it."""
        defaults = Addon.operator_defaults()
        callistemon = Addon.preset_store().load("callistemon").values
        partial = {k: v for k, v in callistemon.items() if k not in self.OLD_PRESET_LACKS}
        path = Addon.preset_store().user_folder(create=True) / "old tree.py"
        path.write_text(repr(partial), encoding="utf-8")
        self.addCleanup(path.unlink)

        after_other = SimpleNamespace(**defaults)
        self.apply(after_other, "small_pine", defaults)
        self.apply(after_other, "old tree", defaults)
        fresh = SimpleNamespace(**defaults)
        self.apply(fresh, "old tree", defaults)
        self.assertEqual(vars(after_other), vars(fresh))


@Verifies("SWR-0041")
class BuiltinPresets(unittest.TestCase):
    """Every built-in preset sets every generation setting and needs no migration: loading one fills nothing in."""

    def test_complete_and_current(self):
        import ast

        defaults = Addon.operator_defaults()
        for entry in Addon.preset_store().entries():
            if not entry.builtin:
                continue
            with self.subTest(preset=entry.name):
                self.assertEqual(Addon.preset_store().load(entry.name).missing(defaults), [])
                path = Addon.preset_store().builtin / f"{entry.name}.py"
                body = "\n".join(
                    line for line in path.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
                )
                values = ast.literal_eval(body.strip())
                migrated = Addon.module("settings").TreeSettings(dict(values)).migrate().values
                self.assertEqual(migrated, values)


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

    @Verifies("SWR-0044")
    def test_save_rejects_bad_settings(self):
        for settings, message in (("", "Invalid settings JSON"), ("null", "version 1 settings object; got NoneType")):
            with self.subTest(settings=settings), self.assertRaisesRegex(RuntimeError, message):
                bpy.ops.sapling.preset_save(name="whatever", overwrite=False, settings=settings)

    @Verifies("SWR-0043")
    def test_save_through_operator_round_trips(self):
        settings = Addon.preset_store().load("quaking_aspen")
        saved = Addon.preset_store().user_folder(create=True) / "saved tree.py"
        self.addCleanup(saved.unlink, missing_ok=True)  # registered first: a failing save leaves no file behind
        self.assertEqual(
            bpy.ops.sapling.preset_save(name="saved tree", overwrite=True, settings=settings.to_json()), {"FINISHED"}
        )
        normalized = Addon.module("settings").TreeSettings.from_json
        self.assertEqual(
            normalized(Addon.preset_store().load("saved tree").to_json()).values, normalized(settings.to_json()).values
        )


@Verifies("SWR-0045")
class SaveOverwrite(unittest.TestCase):
    """Save Preset keeps an existing user preset file when Overwrite is off, and replaces it when Overwrite is on."""

    NAME = "overwrite check"

    def saved(self):
        """The user preset file of this test, removed after it."""
        path = Addon.preset_store().user_folder(create=True) / f"{self.NAME}.py"
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def save(self, preset, overwrite):
        """Save the preset's settings under NAME with the Save Preset operator, and return the operator's result."""
        settings = Addon.preset_store().load(preset).to_json()
        return bpy.ops.sapling.preset_save(name=self.NAME, overwrite=overwrite, settings=settings)

    def test_an_existing_preset_is_kept_without_overwrite(self):
        path = self.saved()
        self.assertEqual(self.save("quaking_aspen", overwrite=True), {"FINISHED"})
        before = path.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "Enable Overwrite"):
            self.save("weeping_willow", overwrite=False)
        self.assertEqual(path.read_bytes(), before)

    def test_overwrite_replaces_it(self):
        path = self.saved()
        self.assertEqual(self.save("quaking_aspen", overwrite=True), {"FINISHED"})
        before = path.read_bytes()
        self.assertEqual(self.save("weeping_willow", overwrite=True), {"FINISHED"})
        self.assertNotEqual(path.read_bytes(), before)
