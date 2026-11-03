# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/service: the decisions the UI used to hold, called directly (no operator, no panel)."""

import json
import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon
from support.scene import Scene
from support.trees import Trees


class Service:
    """The add-on's service modules."""

    @staticmethod
    def module(name):
        return Addon.module(f"service.{name}")

    @classmethod
    def trees(cls):
        names = Addon.module("ui.properties").TreeProperties
        return cls.module("trees").TreeService(bpy.context, names.generation_names(), names.stored_names())


class MissingViewLayer(unittest.TestCase):
    """A context without a view layer is an error, not a later AttributeError."""

    def test_the_service_names_the_missing_view_layer(self):
        names = Addon.module("ui.properties").TreeProperties
        context = SimpleNamespace(view_layer=None)
        service = Service.module("trees").TreeService(context, names.generation_names(), names.stored_names())
        with self.assertRaisesRegex(RuntimeError, "no view layer"):
            service.view_layer()

    def test_a_duplicate_names_the_missing_view_layer(self):
        Scene.reset()
        root = Trees.add()
        before = len(bpy.data.objects)
        context = SimpleNamespace(view_layer=None, active_object=root)
        with self.assertRaisesRegex(RuntimeError, "no view layer"):
            Service.module("copies").TreeCopies.duplicate(context)
        self.assertEqual(len(bpy.data.objects), before, "no copy was made")


class PresetChoices(unittest.TestCase):
    def test_labels_by_kind(self):
        choice = Service.module("presets").PresetService.choice
        self.assertEqual(choice("japanese_maple", True, None).label, "Japanese Maple")
        self.assertEqual(choice("mine", False, None).description, "Your preset")
        broken = choice("bad", False, "not a settings dictionary")
        self.assertEqual((broken.label, broken.description), ("bad (cannot load)", "not a settings dictionary"))

    def test_builtin_presets_come_first(self):
        choices = Service.module("presets").PresetService.choices()
        builtin = [c.description == "Built-in preset" for c in choices]
        self.assertEqual(builtin, sorted(builtin, reverse=True))


class PageRules(unittest.TestCase):
    def rules(self):
        return Service.module("page_rules").PageRules

    def test_leaf_object_only_for_instanced_shapes(self):
        self.assertTrue(self.rules().leaf_object(SimpleNamespace(leafShape="dFace")))
        self.assertFalse(self.rules().leaf_object(SimpleNamespace(leafShape="hex")))

    def test_blossom_options_and_material(self):
        none = SimpleNamespace(leafShape="dVert", blossomRate=0.0)
        some = SimpleNamespace(leafShape="dVert", blossomRate=0.2)
        self.assertFalse(self.rules().blossom_options(none))
        self.assertTrue(self.rules().blossom_options(some))
        self.assertFalse(self.rules().leaf_material(none))
        self.assertTrue(self.rules().leaf_material(some))
        self.assertTrue(self.rules().leaf_material(SimpleNamespace(leafShape="rect", blossomRate=0.0)))

    def test_custom_shape(self):
        self.assertTrue(self.rules().custom_shape(SimpleNamespace(shape="8")))
        self.assertFalse(self.rules().custom_shape(SimpleNamespace(shape="7")))


class TreeSummary(unittest.TestCase):
    def test_readable_and_broken(self):
        Scene.reset()
        root = Trees.add()
        query = Service.module("query").TreeQuery
        summary = query.summary(root)
        self.assertTrue(summary.readable)
        self.assertIn("Levels:", summary.text)
        # stored settings that cannot be read (a root without them is no tree: the panel's poll hides it)
        root[Trees.record().SETTINGS] = "{"
        broken = query.summary(root)
        self.assertFalse(broken.readable)
        self.assertIn("Invalid settings JSON", broken.text)


class LoadedSettings(unittest.TestCase):
    def request(self, **changes):
        trees = Service.module("trees")
        current = Addon.module("settings").TreeSettings(Addon.resolve_preset("quaking_aspen.py"))
        values = dict(current=current, defaults=Addon.operator_defaults())
        values.update(changes)
        return trees.SettingsRequest(**values)

    def test_nothing_to_load(self):
        self.assertEqual(Service.trees().loaded(self.request()), [])

    def test_a_preset_is_loaded_complete(self):
        loads = Service.trees().loaded(self.request(preset="weeping_willow"))
        self.assertEqual(len(loads), 1)
        settings = loads[0].settings.values
        self.assertEqual(sorted(settings), sorted(Addon.operator_defaults()))
        self.assertEqual(settings["levels"], Addon.resolve_preset("weeping_willow.py")["levels"])
        self.assertEqual(loads[0].warnings, [])

    def test_an_edit_loads_the_stored_settings(self):
        Scene.reset()
        root = Trees.add(seed=7)
        loads = Service.trees().loaded(self.request(replace=root.name, load_stored=True))
        self.assertEqual(loads[-1].settings.values["seed"], 7)


class OldNameForwarding(unittest.TestCase):
    class Props:
        """A stand-in for an operator's properties: which ids a script set, and unsetting them."""

        def __init__(self, given):
            self.given = set(given)

        def is_property_set(self, name):
            return name in self.given

        def property_unset(self, name):
            self.given.discard(name)

    def settings(self):
        return Addon.module("settings").TreeSettings

    def test_an_old_id_moves_to_its_new_id(self):
        old, new = next(iter(self.settings().RENAMED.items()))
        target = SimpleNamespace(**{old: 3, new: 0})
        props = self.Props([old])
        self.settings().forward_old_names(target, props)
        self.assertEqual(getattr(target, new), 3)
        self.assertNotIn(old, props.given)

    def test_no_old_id_changes_nothing(self):
        old, new = next(iter(self.settings().RENAMED.items()))
        target = SimpleNamespace(**{old: 3, new: 0})
        self.settings().forward_old_names(target, self.Props([new]))
        self.assertEqual(json.dumps(vars(target), sort_keys=True), json.dumps({old: 3, new: 0}, sort_keys=True))
