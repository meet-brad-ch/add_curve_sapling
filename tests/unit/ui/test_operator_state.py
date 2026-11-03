# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/ui: operator state."""

import unittest
from types import SimpleNamespace

import bpy
from support.addon import Addon


class RedoPanel(unittest.TestCase):
    """In the redo panel, a change of page or other UI state keeps the tree (execute passes through); a setting
    change regenerates it; a settings error cancels with its message. Blender sets is_repeat only for its own redo,
    so execute runs on a stand-in operator."""

    def operator(self, **values):
        reports = []
        stand_in = SimpleNamespace(
            options=SimpleNamespace(is_repeat=True), report=lambda kind, text: reports.append(text), **values
        )
        operator = Addon.module("ui.operators").AddTreeOperator
        stand_in.ui_change_only = lambda: operator.ui_change_only(stand_in)
        return stand_in, reports

    def execute(self, stand_in):
        return Addon.module("ui.operators").AddTreeOperator.execute(stand_in, bpy.context)

    def test_ui_state_passes_through(self):
        stand_in, _reports = self.operator(do_update=False)
        self.assertEqual(self.execute(stand_in), {"PASS_THROUGH"})


class UpdateCallbacks(unittest.TestCase):
    """A setting's update callback decides whether the next run regenerates the tree."""

    def properties(self):
        return Addon.module("ui.properties").TreeProperties

    def test_generation_and_ui_settings(self):
        props = SimpleNamespace(do_update=False)
        self.properties().update_tree(props, None)
        self.assertTrue(props.do_update)
        self.properties().no_update_tree(props, None)
        self.assertFalse(props.do_update)
