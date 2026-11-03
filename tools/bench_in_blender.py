# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/bench.py: median generation time per built-in preset, leaves on."""

import json
import statistics
import sys
import time
from pathlib import Path

import bpy

ROOT = Path(__file__).resolve().parent.parent
GOLDEN = ROOT / "tests" / "golden"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)

RUNS = 5


class BenchScene:
    """The benchmark's empty scene."""

    @staticmethod
    def clear() -> None:
        """Remove the objects and the curve, mesh, armature and action data of the last tree, so each run starts
        empty."""
        data = bpy.data
        bpy.data.batch_remove([*data.objects, *data.curves, *data.meshes, *data.armatures, *data.actions])


def main() -> None:
    """Time each built-in preset (the median of RUNS runs, in ms) in this Blender and write the times to the file after
    '--'."""
    out = Path(sys.argv[sys.argv.index("--") + 1])
    bpy.ops.preferences.addon_enable(module=MODULE)
    result = {}
    for path in sorted(GOLDEN.glob("preset_*.json")):
        settings = json.loads(path.read_text(encoding="utf-8"))["settings"]
        settings["showLeaves"] = True
        times = []
        for _ in range(RUNS):
            BenchScene.clear()
            start = time.perf_counter()
            if bpy.ops.curve.tree_add(**settings, do_update=True) != {"FINISHED"}:
                raise RuntimeError(f"{path.stem} did not generate")
            times.append(time.perf_counter() - start)
        result[path.stem.removeprefix("preset_")] = round(statistics.median(times) * 1000, 1)
    out.write_text(json.dumps(result, indent=1, sort_keys=True), encoding="utf-8")


main()
