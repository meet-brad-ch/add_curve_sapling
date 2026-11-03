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
from golden_cases import CASES
from support.addon import Addon
from support.fingerprint import Fingerprint, FingerprintDiff
from support.golden import Golden
from support.scene import Scene

GOLDEN = Path(__file__).resolve().parent / "golden"


class GoldenTrees(unittest.TestCase):
    def test_golden(self):
        # the fingerprints hash exact float32 values: they hold for the Blender build and platform they came from
        self.assertEqual(sys.platform, "win32", "the golden files are valid on Windows only (README, Decisions)")
        if Golden.record:
            GOLDEN.mkdir(exist_ok=True)
        for name, preset, overrides in CASES:
            with self.subTest(case=name):
                path = GOLDEN / f"{name}.json"
                # The settings a case stands for: the preset as loaded today, with the case's overrides
                current = Addon.resolve_preset(f"{preset}.py")
                current.update({k: Addon.plain(v) for k, v in overrides.items()})
                if Golden.record:
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
                    difference = FingerprintDiff.first(settings, current)
                    self.assertEqual(difference, "", f"{name}: settings drifted from the recording at {difference}")

                result = Scene.generate(settings)
                self.assertEqual(result, {"FINISHED"})
                actual = Fingerprint.scene()

                if Golden.record:
                    record = {"blender": bpy.app.version_string, "settings": settings, "fingerprint": actual}
                    path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                else:
                    difference = FingerprintDiff.first(recorded["fingerprint"], actual)
                    self.assertEqual(difference, "", f"{name} differs at {difference}")
        if Golden.record:
            self.fail("golden files recorded: review the diff, then run the tests without --record-golden")
