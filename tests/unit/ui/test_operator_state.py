# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/ui: operator state."""

import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon
from support.operator_stand_in import OperatorStandIn


class RedoPanel(unittest.TestCase):
    """In the redo panel, a change of page or other UI state keeps the tree (execute passes through); a setting
    change regenerates it; a settings error cancels with its message. Blender sets is_repeat only for its own redo,
    so execute runs on a stand-in operator."""

    def execute(self, stand_in):
        """Run the add operator's execute on the stand-in operator and return its result."""
        return Addon.module("ui.operators").AddTreeOperator.execute(stand_in, bpy.context)

    def test_ui_state_passes_through(self):
        stand_in = OperatorStandIn.make(do_update=False).operator
        self.assertEqual(self.execute(stand_in), {"PASS_THROUGH"})


class UpdateCallbacks(unittest.TestCase):
    """A setting's update callback decides whether the next run regenerates the tree."""

    def properties(self):
        """The add-on's TreeProperties class (the settings and their update callbacks)."""
        return Addon.module("ui.properties").TreeProperties

    def test_generation_and_ui_settings(self):
        props = SimpleNamespace(do_update=False)
        self.properties().update_tree(props, None)
        self.assertTrue(props.do_update)
        self.properties().no_update_tree(props, None)
        self.assertFalse(props.do_update)


class RigDefault(unittest.TestCase):
    """The rig default that TreeSettings uses for old settings is the default of the Armature Rig setting."""

    def test_the_settings_rig_default_is_the_propertys(self):
        """TreeSettings.RIG_DEFAULT (what a left-out rig setting means for old settings) is useRig's default."""
        default = Addon.operator_defaults()["useRig"]
        self.assertEqual(default, Addon.module("settings").TreeSettings.RIG_DEFAULT)


class PlainValues(unittest.TestCase):
    """TreeSettings.plain turns a vector into a list, and refuses a nested or an unknown value."""

    def settings(self):
        """The add-on's settings module."""
        return Addon.module("settings")

    def test_a_vector_becomes_a_list(self):
        self.assertEqual(self.settings().TreeSettings.plain((1.0, 2.0)), [1.0, 2.0])

    def test_a_nested_or_unknown_value_is_refused(self):
        settings = self.settings()
        for value in ([[1.0]], None, object()):
            with self.subTest(value=value), self.assertRaises(settings.SettingsError):
                settings.TreeSettings.plain(value)
