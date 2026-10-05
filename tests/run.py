# SPDX-License-Identifier: GPL-3.0-or-later

"""Test entry point, run inside headless Blender by tools/run_tests.py.

blender -b --factory-startup --python tests/run.py -- [-k=PATTERN ...] [--record-golden]
                                                    [--line-min=MIN --branch-min=MIN --site=VENV_SITE_PACKAGES]
"""

import json
import sys
import unittest
from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parent
BUILD = TESTS.parent / "build"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "tools"))  # blender_env: the add-on's module name

import helpers  # noqa: E402  (needs the sys.path entries above)


def main() -> int:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    patterns = [a.removeprefix("-k=") for a in argv if a.startswith("-k=")]
    helpers.Golden.record = "--record-golden" in argv
    options = {}
    for argument in argv:
        if argument.startswith(("--line-min=", "--branch-min=", "--site=")):
            name, value = argument.removeprefix("--").split("=", 1)
            options[name] = value
    if ("site" in options) != ({"line-min", "branch-min"} <= options.keys()):
        raise SystemExit("--site, --line-min and --branch-min go together")
    coverage = start_coverage(options["site"]) if "site" in options else None

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
    minimums = (float(options["line-min"]), float(options["branch-min"])) if coverage is not None else None
    if minimums is not None and not coverage_reached(coverage, *minimums):
        return 1
    return 0 if result.wasSuccessful() else 1


def start_coverage(site_packages):
    """Branch coverage of the add-on, started before it is enabled (so registration code counts)."""
    sys.path.append(site_packages)
    import coverage

    measure = coverage.Coverage(branch=True, source_pkgs=[helpers.MODULE], data_file=str(BUILD / ".coverage"))
    measure.start()
    return measure


def coverage_reached(measure, line_min, branch_min):
    """Print the report and the line and branch coverage; whether both reach their minimum.

    coverage.py's report total combines lines and branches, so the two are read from its JSON totals.
    """
    measure.stop()
    measure.save()
    measure.report(file=sys.stdout, show_missing=True, skip_covered=True, precision=1)
    report = BUILD / "coverage.json"
    measure.json_report(outfile=str(report))
    totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
    line = 100 * totals["covered_lines"] / totals["num_statements"]
    branch = 100 * totals["covered_branches"] / totals["num_branches"]
    print(f"line coverage {line:.1f} % (minimum {line_min:.0f} %)")
    print(f"branch coverage {branch:.1f} % (minimum {branch_min:.0f} %)")
    return line >= line_min and branch >= branch_min


sys.exit(main())
