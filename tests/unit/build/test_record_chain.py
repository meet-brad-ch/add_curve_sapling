# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/build: a tree's chain of parents is bounded."""

import unittest

from support.addon import Addon


class FakeObject:
    """An object with a tree id and a parent, as TreeRecord._top reads them."""

    def __init__(self, name, tree_id):
        """Make an object with the name and the tree id, and no parent."""
        self.name = name
        self.parent = None
        self.ids = {Addon.module("build.tree_record").TreeRecord.ID: tree_id}

    def get(self, key):
        """The custom property with the key, or None."""
        return self.ids.get(key)

    def __getitem__(self, key):
        """The custom property with the key (KeyError if it is missing)."""
        return self.ids[key]


class ParentChain(unittest.TestCase):
    """A loop of parents makes TreeRecord._top fail with a TreeRecordError, not loop forever."""

    def test_a_loop_of_parents_raises(self):
        record = Addon.module("build.tree_record")
        a = FakeObject("a", "tree")
        b = FakeObject("b", "tree")
        a.parent = b
        b.parent = a
        with self.assertRaisesRegex(record.TreeRecordError, "chain of parents is longer than the objects"):
            record.TreeRecord._top(a)
