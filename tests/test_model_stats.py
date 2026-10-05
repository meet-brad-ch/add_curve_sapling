# SPDX-License-Identifier: GPL-3.0-or-later

"""Statistical regression of the array model: trees stay the same kind of tree.

The goldens pin exact geometry; the model's random scheme may change deliberately, so this records per case
the stem counts per level, the stem lengths' mean and spread per level, the bounding box and the leaf count,
and allows a tolerance. Record with --record-golden (the goldens' switch), review, then run without it.
"""

import json
import random
import unittest
from pathlib import Path
from typing import Any

import helpers
import numpy as np

STATS = Path(__file__).resolve().parent / "golden" / "model_stats.json"
CASES = {
    "quaking_aspen": ("quaking_aspen", {}),
    "callistemon_unpruned": ("callistemon", {"prune": False}),
    "trunks_3": ("quaking_aspen", {"levels": 2, "trunks": 3}),
    "rings": ("quaking_aspen", {"levels": 2, "nrings": 4}),
    "rotate_mode": ("quaking_aspen", {"levels": 2, "rMode": "rotate"}),
    "random_mode": ("quaking_aspen", {"levels": 2, "rMode": "random"}),
    "levels_5": ("quaking_aspen", {"levels": 5, "branches": (0, 8, 3, 2), "closeTip": True}),
    "palmate": ("quaking_aspen", {"levels": 2, "leaves": -5, "showLeaves": True}),
    "attract_out": ("callistemon", {"prune": False, "attractOut": (0, 0.5, 0.5, 0)}),
}
COUNT_TOLERANCE = 0.15
LENGTH_TOLERANCE = 0.10
BOX_TOLERANCE = 0.10


def stats(preset, changes):
    settings = helpers.resolve_preset(f"{preset}.py")
    settings.update(changes)
    model = helpers.grow_model(settings)
    params = model.params
    grown = model.grown
    flat = model.curve.flatten()
    starts = [0, *grown.level_ends]
    out: dict[str, Any] = {"levels": []}
    for level in range(len(grown.level_ends)):
        splines = range(starts[level], starts[level + 1])
        lengths = [
            float(np.linalg.norm(np.diff(flat.co[flat.start[i] : flat.start[i + 1]], axis=0), axis=1).sum())
            for i in splines
        ]
        out["levels"].append(
            {"stems": len(splines), "length_mean": float(np.mean(lengths)), "length_std": float(np.std(lengths))}
        )
    out["box"] = (flat.co.max(axis=0) - flat.co.min(axis=0)).tolist()
    out["leaves"] = int(
        helpers.module("model.leaves").LeafGenerator(params, random.Random(1)).generate(grown.sprouts).leaves.count
    )
    return out


class ModelStatistics(unittest.TestCase):
    def test_cases(self):
        recorded = json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}
        current = {name: stats(*case) for name, case in CASES.items()}
        if helpers.Golden.record:
            STATS.write_text(json.dumps(current, indent=1, sort_keys=True) + "\n", encoding="utf-8")
            self.fail("model statistics recorded: review the diff, then run without --record-golden")
        for name, now in current.items():
            with self.subTest(case=name):
                self.assertIn(name, recorded, "no recording; record it first")
                self.compare(recorded[name], now)

    def compare(self, old, now):
        self.assertEqual(len(old["levels"]), len(now["levels"]))
        for was, is_ in zip(old["levels"], now["levels"], strict=True):
            self.within(was["stems"], is_["stems"], COUNT_TOLERANCE, "stems")
            self.within(was["length_mean"], is_["length_mean"], LENGTH_TOLERANCE, "length mean")
            self.within(was["length_std"], is_["length_std"], LENGTH_TOLERANCE, "length std")
        for axis, (was, is_) in enumerate(zip(old["box"], now["box"], strict=True)):
            self.within(was, is_, BOX_TOLERANCE, f"box axis {axis}")
        self.assertEqual(old["leaves"], now["leaves"])

    def within(self, was, is_, tolerance, what):
        if was == 0:
            self.assertEqual(is_, 0, what)
        else:
            self.assertLessEqual(abs(is_ - was) / abs(was), tolerance, f"{what}: {was} -> {is_}")
