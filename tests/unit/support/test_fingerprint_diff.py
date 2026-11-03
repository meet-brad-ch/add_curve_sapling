# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of tests/support: the first difference between two fingerprints, as the golden test reports it."""

import unittest

from support.fingerprint import FingerprintDiff


class FirstDifference(unittest.TestCase):
    """FingerprintDiff.first names the path and the kind of the first difference between two fingerprints
    (a value, a missing or unexpected key, a list length), depth first in key order."""

    def test_equal_fingerprints_have_no_difference(self):
        tree = {"a": [1, {"b": 2.0}], "c": "x"}
        self.assertEqual(FingerprintDiff.first(tree, {"a": [1, {"b": 2.0}], "c": "x"}), "")

    def test_a_plain_value_at_the_top(self):
        self.assertEqual(FingerprintDiff.first(1, 2), ": 1 -> 2")

    def test_a_changed_value_names_its_path(self):
        self.assertEqual(FingerprintDiff.first({"a": [1, {"b": 2}]}, {"a": [1, {"b": 3}]}), "/a[1]/b: 2 -> 3")

    def test_a_missing_and_an_unexpected_key(self):
        self.assertEqual(FingerprintDiff.first({"a": 1, "b": 2}, {"a": 1}), "/b: missing")
        self.assertEqual(FingerprintDiff.first({"a": 1}, {"a": 1, "b": 2}), "/b: unexpected")

    def test_a_list_length(self):
        self.assertEqual(FingerprintDiff.first({"a": [1, 2]}, {"a": [1]}), "/a: length 2 -> 1")

    def test_a_dict_against_a_list_is_a_value_change(self):
        self.assertEqual(FingerprintDiff.first({"a": {}}, {"a": []}), "/a: {} -> []")

    def test_the_first_difference_is_depth_first_in_key_order(self):
        # "a" sorts first, and everything below "a" comes before "b", also a key missing at "b"
        expected = {"b": 1, "a": {"y": [5, 6], "x": 1}}
        actual = {"a": {"y": [5, 7], "x": 1}}
        self.assertEqual(FingerprintDiff.first(expected, actual), "/a/y[1]: 6 -> 7")

    def test_a_missing_key_comes_before_a_later_value_change(self):
        expected = {"a": 1, "b": 1, "c": 1}
        actual = {"a": 1, "c": 2}
        self.assertEqual(FingerprintDiff.first(expected, actual), "/b: missing")
