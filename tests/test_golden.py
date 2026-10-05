# SPDX-License-Identifier: GPL-3.0-or-later

"""Generated trees must stay identical to the recorded golden fingerprints.

The golden files are only valid for the Blender build they were recorded with (float math in libm
can differ by one ulp between builds). Re-record with `python tools/run_tests.py --record-golden`,
and commit every intentional re-record on its own, with the reason in the message.
"""

import json
import sys
import unittest
from pathlib import Path

import bpy
import helpers
from golden_cases import CASES

GOLDEN = Path(__file__).resolve().parent / "golden"


def first_difference(expected, actual, path="") -> str:
    """Human-readable location of the first difference between two fingerprints."""
    if isinstance(expected, dict) and isinstance(actual, dict):
        return dict_difference(expected, actual, path)
    if isinstance(expected, list) and isinstance(actual, list):
        return list_difference(expected, actual, path)
    return "" if expected == actual else f"{path}: {expected!r} -> {actual!r}"


def dict_difference(expected, actual, path) -> str:
    for key in sorted(set(expected) | set(actual)):
        if key not in actual:
            return f"{path}/{key}: missing"
        if key not in expected:
            return f"{path}/{key}: unexpected"
        found = first_difference(expected[key], actual[key], f"{path}/{key}")
        if found:
            return found
    return ""


def list_difference(expected, actual, path) -> str:
    if len(expected) != len(actual):
        return f"{path}: length {len(expected)} -> {len(actual)}"
    for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
        found = first_difference(e, a, f"{path}[{i}]")
        if found:
            return found
    return ""


class GoldenTrees(unittest.TestCase):
    def test_golden(self):
        # the fingerprints hash exact float32 values: they hold for the Blender build and platform they came from
        self.assertEqual(sys.platform, "win32", "the golden files are valid on Windows only (README, Decisions)")
        if helpers.Golden.record:
            GOLDEN.mkdir(exist_ok=True)
        for name, preset, overrides in CASES:
            with self.subTest(case=name):
                path = GOLDEN / f"{name}.json"
                # The settings a case stands for: the preset as loaded today, with the case's overrides
                current = helpers.resolve_preset(f"{preset}.py")
                current.update({k: helpers.plain(v) for k, v in overrides.items()})
                if helpers.Golden.record:
                    settings = current
                else:
                    self.assertTrue(path.exists(), f"no golden file {path.name}; record it first")
                    recorded = json.loads(path.read_text(encoding="utf-8"))
                    self.assertEqual(
                        recorded["blender"],
                        bpy.app.version_string,
                        f"{name} was recorded with Blender {recorded['blender']}: run the tests on that version",
                    )
                    settings = recorded["settings"]
                    difference = first_difference(settings, current)
                    self.assertEqual(difference, "", f"{name}: settings drifted from the recording at {difference}")

                result = helpers.generate(settings)
                self.assertEqual(result, {"FINISHED"})
                actual = helpers.fingerprint()

                if helpers.Golden.record:
                    record = {"blender": bpy.app.version_string, "settings": settings, "fingerprint": actual}
                    path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                else:
                    difference = first_difference(recorded["fingerprint"], actual)
                    self.assertEqual(difference, "", f"{name} differs at {difference}")
        if helpers.Golden.record:
            self.fail("golden files recorded: review the diff, then run the tests without --record-golden")
