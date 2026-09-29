# SPDX-License-Identifier: GPL-3.0-or-later

"""Test entry point, run inside headless Blender by tools/run_tests.py.

blender -b --factory-startup --python tests/run.py -- [-k=PATTERN ...] [--record-golden]
"""

import sys
import unittest
from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))

import helpers  # noqa: E402  (needs the sys.path entry above)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    patterns = [a.removeprefix("-k=") for a in argv if a.startswith("-k=")]
    helpers.RECORD_GOLDEN = "--record-golden" in argv

    bpy.ops.preferences.addon_enable(module=helpers.MODULE)
    if helpers.MODULE not in sys.modules:
        raise SystemExit(f"the add-on {helpers.MODULE} did not enable")

    loader = unittest.TestLoader()
    if patterns:
        loader.testNamePatterns = [f"*{p}*" for p in patterns]
    suite = loader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
    result = unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)
    if result.testsRun == 0:
        print(f"no tests matched {patterns}")
        return 1
    return 0 if result.wasSuccessful() else 1


sys.exit(main())
