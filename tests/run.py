# SPDX-License-Identifier: GPL-3.0-or-later

"""Test entry point, run inside headless Blender by tools/run_tests.py.

blender -b --factory-startup --python tests/run.py -- [-k=PATTERN ...] [--record-golden]
                                                    [--coverage=MIN --site=VENV_SITE_PACKAGES]
"""

import sys
import unittest
from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parent
BUILD = TESTS.parent / "build"
sys.path.insert(0, str(TESTS))

import helpers  # noqa: E402  (needs the sys.path entry above)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    patterns = [a.removeprefix("-k=") for a in argv if a.startswith("-k=")]
    helpers.RECORD_GOLDEN = "--record-golden" in argv
    options = dict(a.removeprefix("--").split("=", 1) for a in argv if a.startswith(("--coverage=", "--site=")))
    coverage = start_coverage(options["site"]) if "coverage" in options else None

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
    if coverage is not None and not coverage_reached(coverage, float(options["coverage"])):
        return 1
    return 0 if result.wasSuccessful() else 1


def start_coverage(site_packages):
    """Branch coverage of the add-on, started before it is enabled (so registration code counts)."""
    sys.path.append(site_packages)
    import coverage

    measure = coverage.Coverage(branch=True, source_pkgs=[helpers.MODULE], data_file=str(BUILD / ".coverage"))
    measure.start()
    return measure


def coverage_reached(measure, minimum):
    measure.stop()
    measure.save()
    total = measure.report(file=sys.stdout, show_missing=True, skip_covered=True, precision=1)
    print(f"branch coverage {total:.1f} % (minimum {minimum:.0f} %)")
    return total >= minimum


sys.exit(main())
