# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/build: a tree's chain of parents is bounded."""

import unittest

from support.addon import Addon


class FakeObject:
    """An object with a tree id and a parent, as TreeRecord._top reads them."""

    def __init__(self, name, tree_id):
        self.name = name
        self.parent = None
        self.ids = {Addon.module("build.tree_record").TreeRecord.ID: tree_id}

    def get(self, key):
        return self.ids.get(key)

    def __getitem__(self, key):
        return self.ids[key]


class ParentChain(unittest.TestCase):
    def test_a_loop_of_parents_raises(self):
        record = Addon.module("build.tree_record")
        a = FakeObject("a", "tree")
        b = FakeObject("b", "tree")
        a.parent = b
        b.parent = a
        with self.assertRaisesRegex(record.TreeRecordError, "chain of parents is longer than the objects"):
            record.TreeRecord._top(a)
