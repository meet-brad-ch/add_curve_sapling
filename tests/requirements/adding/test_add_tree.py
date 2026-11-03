# SPDX-License-Identifier: GPL-3.0-or-later

"""Adding a tree: add tree (the requirements each class or test names)."""

import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon
from support.layout import RecordingLayout
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


@Verifies("SWR-0012")
class Placement(unittest.TestCase):
    def test_new_tree_at_cursor_selected_and_active(self):
        Scene.reset()
        other = bpy.data.objects.new("other", None)
        bpy.context.scene.collection.objects.link(other)
        other.select_set(True)
        bpy.context.scene.cursor.location = (1.0, 2.0, 3.0)
        try:
            settings = Addon.resolve_preset("quaking_aspen.py")
            self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        finally:
            bpy.context.scene.cursor.location = (0.0, 0.0, 0.0)
        root = bpy.context.active_object
        self.assertEqual(Trees.root_of(root), root)
        self.assertEqual(root.location.to_tuple(), (1.0, 2.0, 3.0))
        self.assertEqual(bpy.context.selected_objects, [root])


@Verifies("SWR-0143")
class NoActiveCollection(unittest.TestCase):
    """Without an active collection the operator cancels with a message (not a traceback), and makes nothing."""

    def test_add_without_a_collection_cancels(self):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        with bpy.context.temp_override(collection=None), self.assertRaisesRegex(RuntimeError, "No active collection"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
        self.assertEqual(len(bpy.data.objects), 0)


@Verifies("SWR-0015")
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
        return Addon.module("ui.operators").AddTreeOperator.execute(stand_in, bpy.context)

    def test_a_setting_change_regenerates(self):
        stand_in, _reports = self.operator(do_update=True, _generate=lambda context: {"FINISHED"})
        self.assertEqual(self.execute(stand_in), {"FINISHED"})


@Verifies("SWR-0015")
class UpdateCallbacks(unittest.TestCase):
    """A setting's update callback decides whether the next run regenerates the tree."""

    def properties(self):
        return Addon.module("ui.properties").TreeProperties

    def test_a_leaf_setting_regenerates_only_with_leaves_shown(self):
        for shown in (False, True):
            with self.subTest(show_leaves=shown):
                props = SimpleNamespace(showLeaves=shown, do_update=not shown)
                self.properties().update_leaves(props, None)
                self.assertEqual(props.do_update, shown)


@Verifies("SWR-0011", "SWR-0026")
class TreeUi(unittest.TestCase):
    """The sidebar panel and the menu entries, on a generated tree."""

    def panels(self):
        return Addon.module("ui.panels")

    def test_menu_entries(self):
        root = Trees.add_with_leaves()
        menus = self.panels().Menus
        add_menu = RecordingLayout()
        menus.add_curve(SimpleNamespace(layout=add_menu), None)
        self.assertEqual([b.idname for b in add_menu.buttons], ["curve.tree_add"])

        object_menu = RecordingLayout()
        menus.object_menu(SimpleNamespace(layout=object_menu), SimpleNamespace(active_object=root.children[0]))
        self.assertEqual([b.idname for b in object_menu.buttons], ["curve.tree_add", "sapling.tree_duplicate"])
        self.assertEqual(object_menu.buttons[0].replace, root.name)

        not_a_tree = RecordingLayout()
        menus.object_menu(SimpleNamespace(layout=not_a_tree), SimpleNamespace(active_object=Scene.add_leaf_card()))
        self.assertEqual(not_a_tree.buttons, [])
