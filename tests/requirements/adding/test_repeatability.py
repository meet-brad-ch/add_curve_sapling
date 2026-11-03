# SPDX-License-Identifier: GPL-3.0-or-later

"""Adding a tree: repeatability (the requirements each class or test names)."""

import json
import sys
import unittest
import unittest.mock

import bpy
import numpy as np
from support.addon import Addon
from support.fingerprint import Fingerprint, FingerprintDiff
from support.golden import Golden
from support.golden_cases import CASES
from support.model import Model
from support.paths import Paths
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0013")
class GoldenTrees(unittest.TestCase):
    """Each golden case (a preset with overrides) gives the fingerprint that its golden file records (Windows only)."""

    def test_golden(self):
        # the fingerprints hash exact float32 values: they hold for the Blender build and platform they came from
        self.assertEqual(sys.platform, "win32", "the golden files are valid on Windows only (README, Decisions)")
        golden = Paths.GOLDEN
        if Golden.record:
            golden.mkdir(parents=True, exist_ok=True)
        for name, preset, overrides in CASES:
            with self.subTest(case=name):
                path = golden / f"{name}.json"
                # The settings a case stands for: the preset as loaded today, with the case's overrides
                current = Addon.resolve_preset(f"{preset}.py")
                current.update({k: Addon.plain(v) for k, v in overrides.items()})
                if Golden.record:
                    settings = current
                else:
                    self.assertTrue(path.exists(), f"no golden file {path.name}; record it first")
                    recorded = json.loads(path.read_text(encoding="utf-8"))
                    # one data set for every supported version (support/golden.py): the comparison proves it
                    self.assertTrue(Golden.running_supported(), f"Blender {bpy.app.version_string} is not supported")
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


@Verifies("SWR-0013")
class PrunedTrees(unittest.TestCase):
    """Pruning on the grid: the kept stems fit the envelope, the removed ones are stubs without sprouts."""

    @staticmethod
    def overshoots(params, curve, grown):
        """Per kept stem end, its distance from the axis over the envelope's limit there (1 = on the envelope)."""
        flat = curve.flatten()
        scale = params.scale
        ends = flat.co[flat.start[1:] - 1].astype(np.float64)
        sizes = flat.sizes
        over = []
        for i, end in enumerate(ends):
            level = Model.level_index(grown, i)
            if sizes[i] < 2 or (level == 0 and end[2] < params.prune_base_clamped * scale):
                continue
            ratio = (scale - end[2]) / (scale * max(1 - params.prune_base_clamped, 1e-6))
            limit = params.prune_width * params.envelope(ratio)
            if limit > 0:
                over.append(np.hypot(end[0], end[1]) / scale / limit)
        return np.array(over)

    def test_two_growths_are_identical(self):
        """The same settings give the same arrays, bit for bit, every time."""
        model = Model.grow_preset(preset="cambridge_oak")
        first = model.curve
        model = Model.grow_preset(preset="cambridge_oak")
        second = model.curve
        a = first.flatten()
        b = second.flatten()
        for name in ("co", "left", "right", "radius", "h1", "h2", "start"):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name), err_msg=name)
