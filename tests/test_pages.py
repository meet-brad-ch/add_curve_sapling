# SPDX-License-Identifier: GPL-3.0-or-later

"""The settings pages, sidebar panel and menu entries, drawn into a recording layout.

Blender draws no UI in background mode, so the draw code runs against a stand-in layout.
"""

import unittest
from types import SimpleNamespace

import bpy
import helpers


class RecordingLayout:
    """Stands in for bpy.types.UILayout: records the properties, buttons and labels drawn, in order."""

    def __init__(self):
        self.props = []
        self.buttons = []
        self.labels = []

    def prop(self, props, name, **options):
        self.props.append(name)

    def prop_search(self, props, name, search_data, search_property, **options):
        self.props.append(name)

    def operator(self, idname, **options):
        button = SimpleNamespace(idname=idname, **options)
        self.buttons.append(button)
        return button

    def label(self, text="", **options):
        self.labels.append(text)

    def separator(self):
        pass

    def row(self):
        return self

    def column(self):
        return self

    def box(self):
        return self

    def split(self):
        return self


def add_tree():
    helpers.reset_scene()
    settings = {**helpers.resolve_preset("quaking_aspen.py"), "showLeaves": True}
    if bpy.ops.curve.tree_add(**settings, do_update=True) != {"FINISHED"}:
        raise AssertionError("tree_add failed")
    return helpers.active_object()


class SettingsPages(unittest.TestCase):
    PAGES = 8

    def draw(self, **changes):
        """The properties drawn on every page, with the operator's defaults plus `changes`."""
        pages = helpers.module("ui.pages").SettingsPages
        drawn_per_page = []
        for page in range(self.PAGES):
            values = {**helpers.operator_defaults(), "leafDupliObj": "", "presetName": "", "overwrite": False}
            props = SimpleNamespace(**{**values, "chooseSet": str(page), **changes})
            layout = RecordingLayout()
            pages.draw(props, layout)
            drawn_per_page.append(layout.props)
        return drawn_per_page

    def test_every_page_draws_existing_properties(self):
        properties = set(helpers.operator_property_names())
        for page, drawn in enumerate(self.draw()):
            with self.subTest(page=page):
                self.assertEqual(drawn[0], "chooseSet")
                self.assertGreater(len(drawn), 3)
                self.assertEqual(set(drawn) - properties, set())

    def test_every_generation_property_is_on_a_page(self):
        drawn = set()
        for changes in ({}, {"shape": "8", "leafShape": "dFace", "blossomRate": 0.5}):
            for page in self.draw(**changes):
                drawn.update(page)
        hidden = {"bend"}  # Leaf Bend has no control, as in earlier versions
        self.assertEqual(set(helpers.generation_names()) - drawn - hidden, set())

    def test_conditional_fields(self):
        geometry, leaves = 0, 5
        self.assertNotIn("customShape", self.draw()[geometry])
        self.assertIn("customShape", self.draw(shape="8")[geometry])
        self.assertIn("leafMaterial", self.draw(leafShape="hex")[leaves])
        self.assertNotIn("leafDupliObj", self.draw(leafShape="hex")[leaves])
        instanced = self.draw(leafShape="dVert")[leaves]
        self.assertIn("leafDupliObj", instanced)
        self.assertNotIn("leafMaterial", instanced)
        self.assertNotIn("blossomShape", self.draw()[leaves])
        blossoming = self.draw(leafShape="dVert", blossomRate=0.5)[leaves]
        self.assertIn("blossomShape", blossoming)
        self.assertIn("leafMaterial", blossoming)


class TreeUi(unittest.TestCase):
    """The sidebar panel and the menu entries, on a generated tree."""

    def panels(self):
        return helpers.module("ui.panels")

    def test_panel_shows_for_tree_parts_only(self):
        root = add_tree()
        panel = self.panels().TreePanel
        self.assertTrue(panel.poll(SimpleNamespace(mode="OBJECT", active_object=root)))
        self.assertFalse(panel.poll(SimpleNamespace(mode="EDIT_CURVE", active_object=root)))
        self.assertFalse(panel.poll(SimpleNamespace(mode="OBJECT", active_object=None)))
        card = helpers.add_leaf_card()
        self.assertFalse(panel.poll(SimpleNamespace(mode="OBJECT", active_object=card)))

    def test_panel_draws_the_edit_button_for_the_root(self):
        root = add_tree()
        child = root.children[0]
        layout = RecordingLayout()
        self.panels().TreePanel.draw(SimpleNamespace(layout=layout), SimpleNamespace(active_object=child))
        settings = helpers.stored_settings(root)
        self.assertEqual(layout.labels[0], f"Root: {root.name}")
        self.assertIn(f"Seed: {settings['seed']}", layout.labels[1])
        (button,) = layout.buttons
        self.assertEqual((button.idname, button.replace), ("curve.tree_add", root.name))

    def test_panel_draw_without_a_layout_fails(self):
        root = add_tree()
        with self.assertRaisesRegex(RuntimeError, "without a layout"):
            self.panels().TreePanel.draw(SimpleNamespace(layout=None), SimpleNamespace(active_object=root))

    def test_panel_shows_a_broken_record(self):
        """A draw method cannot report: a record that cannot be read shows its reason, and no Edit button."""
        root = add_tree()
        root[helpers.module("build.tree_record").TreeRecord.SETTINGS] = "{"
        layout = RecordingLayout()
        self.panels().TreePanel.draw(SimpleNamespace(layout=layout), SimpleNamespace(active_object=root))
        self.assertEqual(layout.labels[0], f"Root: {root.name}")
        self.assertIn("Invalid settings JSON", layout.labels[1])
        self.assertEqual(layout.buttons, [])

    def test_menu_entries(self):
        root = add_tree()
        menus = self.panels().Menus
        add_menu = RecordingLayout()
        menus.add_curve(SimpleNamespace(layout=add_menu), None)
        self.assertEqual([b.idname for b in add_menu.buttons], ["curve.tree_add"])

        object_menu = RecordingLayout()
        menus.object_menu(SimpleNamespace(layout=object_menu), SimpleNamespace(active_object=root.children[0]))
        self.assertEqual([(b.idname, b.replace) for b in object_menu.buttons], [("curve.tree_add", root.name)])

        not_a_tree = RecordingLayout()
        menus.object_menu(SimpleNamespace(layout=not_a_tree), SimpleNamespace(active_object=helpers.add_leaf_card()))
        self.assertEqual(not_a_tree.buttons, [])
