# SPDX-License-Identifier: GPL-3.0-or-later

"""Test entry point, run inside headless Blender by tools/run_tests.py.

blender -b --factory-startup --python tests/run.py -- [-k=PATTERN ...] [--record-golden]
                                                    [--line-min=MIN --branch-min=MIN --site=VENV_SITE_PACKAGES]
"""

import json
import sys
import unittest
from dataclasses import dataclass, field
from pathlib import Path

import bpy

TESTS = Path(__file__).resolve().parent
BUILD = TESTS.parent / "build"
sys.path.insert(0, str(TESTS))
sys.path.insert(0, str(TESTS.parent / "tools"))  # blender_env: the add-on's module name

from support.addon import Addon  # noqa: E402  (needs the sys.path entries above)
from support.golden import Golden  # noqa: E402


@dataclass(frozen=True)
class RunOptions:
    """The run's arguments (after Blender's "--"): the test name patterns, golden recording, and the coverage
    minimums with the venv's site-packages (all three, or none: no coverage)."""

    patterns: list[str] = field(default_factory=list)
    record_golden: bool = False
    site: str = ""
    line_min: float = 0.0
    branch_min: float = 0.0

    COVERAGE_OPTIONS = ("--line-min=", "--branch-min=", "--site=")

    @classmethod
    def parse(cls, argv: list[str]) -> "RunOptions":
        """The options of Blender's command line. Raises SystemExit when the coverage options are not all there."""
        arguments = cls.arguments(argv)
        patterns = [a.removeprefix("-k=") for a in arguments if a.startswith("-k=")]
        coverage = cls.coverage_values(arguments)
        if not coverage:
            return cls(patterns=patterns, record_golden="--record-golden" in arguments)
        if coverage.keys() != {"site", "line-min", "branch-min"}:
            raise SystemExit("--site, --line-min and --branch-min go together")
        return cls(
            patterns=patterns,
            record_golden="--record-golden" in arguments,
            site=coverage["site"],
            line_min=float(coverage["line-min"]),
            branch_min=float(coverage["branch-min"]),
        )

    @staticmethod
    def arguments(argv: list[str]) -> list[str]:
        """The arguments after Blender's "--" (none when there is no "--")."""
        if "--" not in argv:
            return []
        start = argv.index("--") + 1
        return argv[start:]

    @classmethod
    def coverage_values(cls, arguments: list[str]) -> dict[str, str]:
        """The coverage options given, by name without the leading "--"."""
        values = {}
        for argument in arguments:
            if argument.startswith(cls.COVERAGE_OPTIONS):
                name, value = argument.removeprefix("--").split("=", 1)
                values[name] = value
        return values

    @property
    def measures_coverage(self) -> bool:
        """Whether the run measures the add-on's coverage."""
        return self.site != ""


class CoverageRun:
    """Branch coverage of the add-on, started before it is enabled (so registration code counts)."""

    def __init__(self, site_packages: str) -> None:
        """Start measuring, with the coverage package from the venv's `site_packages`."""
        sys.path.append(site_packages)
        import coverage

        self.measure = coverage.Coverage(branch=True, source_pkgs=[Addon.MODULE], data_file=str(BUILD / ".coverage"))
        self.measure.start()

    def reached(self, line_min: float, branch_min: float) -> bool:
        """Print the report and the line and branch coverage; whether both reach their minimum.

        coverage.py's report total combines lines and branches, so the two are read from its JSON totals.
        """
        self.measure.stop()
        self.measure.save()
        self.measure.report(file=sys.stdout, show_missing=True, skip_covered=True, precision=1)
        report = BUILD / "coverage.json"
        self.measure.json_report(outfile=str(report))
        totals = json.loads(report.read_text(encoding="utf-8"))["totals"]
        line = 100 * totals["covered_lines"] / totals["num_statements"]
        branch = 100 * totals["covered_branches"] / totals["num_branches"]
        print(f"line coverage {line:.1f} % (minimum {line_min:.0f} %)")
        print(f"branch coverage {branch:.1f} % (minimum {branch_min:.0f} %)")
        return line >= line_min and branch >= branch_min


class TestRun:
    """The suite in this Blender: enable the add-on, discover and run the tests, then check the coverage."""

    def __init__(self, options: RunOptions) -> None:
        """A run with the parsed command line `options`."""
        self.options = options

    def run(self) -> int:
        """The process exit code: 0 when every test passed (and the coverage reached its minimums)."""
        Golden.record = self.options.record_golden
        coverage = None
        if self.options.measures_coverage:
            coverage = CoverageRun(self.options.site)
        self.enable_addon()
        result = self.run_suite()
        if result.testsRun == 0:
            print(f"no tests matched {self.options.patterns}")
            return 1
        if coverage is not None and not coverage.reached(self.options.line_min, self.options.branch_min):
            return 1
        if not result.wasSuccessful():
            return 1
        return 0

    @staticmethod
    def enable_addon() -> None:
        """Enable the installed add-on. Raises SystemExit when Blender did not load it."""
        bpy.ops.preferences.addon_enable(module=Addon.MODULE)
        if Addon.MODULE not in sys.modules:
            raise SystemExit(f"the add-on {Addon.MODULE} did not enable")

    def run_suite(self) -> unittest.TestResult:
        """Every test under tests/ (only those matching a -k pattern, when given)."""
        loader = unittest.TestLoader()
        if self.options.patterns:
            loader.testNamePatterns = [f"*{p}*" for p in self.options.patterns]
        suite = loader.discover(str(TESTS), pattern="test_*.py", top_level_dir=str(TESTS))
        return unittest.TextTestRunner(stream=sys.stdout, verbosity=2).run(suite)


sys.exit(TestRun(RunOptions.parse(sys.argv)).run())
