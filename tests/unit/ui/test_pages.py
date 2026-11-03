# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/ui: pages."""

import unittest
from types import SimpleNamespace

from support.addon import Addon
from support.trees import Trees


class TreeUi(unittest.TestCase):
    """The sidebar panel and the menu entries, on a generated tree."""

    def panels(self):
        return Addon.module("ui.panels")

    def test_panel_draw_without_a_layout_fails(self):
        root = Trees.add_with_leaves()
        with self.assertRaisesRegex(RuntimeError, "without a layout"):
            self.panels().TreePanel.draw(SimpleNamespace(layout=None), SimpleNamespace(active_object=root))
