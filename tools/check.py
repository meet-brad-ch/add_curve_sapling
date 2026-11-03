# SPDX-License-Identifier: GPL-3.0-or-later

"""The gate: lint, format, types, the requirements, manifest, then the test suite with line and branch coverage.

python tools/check.py          # everything (run before merging)
python tools/check.py --fast   # without the Blender test suite (the pre-commit hook)
python tools/check.py --all-blenders   # the full gate on each supported Blender, one after another

--all-blenders takes each version's executable from BLENDER_<major>_<minor> (e.g. BLENDER_5_3); the first
supported version falls back to the default install. The runs never overlap: each reinstalls the extension
into the one build/test-profile.
"""

import argparse
import os
import subprocess
import sys

from blender_env import (
    DEFAULT_BLENDER,
    ROOT,
    SOURCE,
    SUPPORTED_VERSIONS,
    install_fresh,
    run,
    run_script,
    venv_python,
    venv_site_packages,
)

# Coverage of the add-on the test suite must reach, in percent (the gate prints the measured values)
LINE_COVERAGE_MIN = 99
BRANCH_COVERAGE_MIN = 96
# vulture: every folder of code (tools/vulture_whitelist.py holds the names used only by name)
DEAD_CODE = ["source", "tools", "tests", "--exclude", "source/presets,build,.venv", "--min-confidence", "60"]


def step(title: str, cmd: list[str]) -> bool:
    print(f"== {title}", flush=True)
    ok = subprocess.run(cmd, cwd=ROOT).returncode == 0
    print(f"== {title}: {'ok' if ok else 'FAILED'}", flush=True)
    return ok


def blender_of(version: str) -> str:
    """The executable of a supported version: BLENDER_<major>_<minor>, or the default install for the first
    version; "" when neither is there."""
    variable = "BLENDER_" + version.removeprefix("Blender ").replace(".", "_")
    if variable in os.environ:
        return os.environ[variable]
    if version == SUPPORTED_VERSIONS[0] and DEFAULT_BLENDER.is_file():
        return str(DEFAULT_BLENDER)
    return ""


def all_blenders(python: str) -> int:
    """The full gate once per supported Blender, one after another, then one result line per version."""
    results = {}
    for version in SUPPORTED_VERSIONS:
        path = blender_of(version)
        if not path:
            variable = "BLENDER_" + version.removeprefix("Blender ").replace(".", "_")
            print(f"== {version}: FAILED, set {variable} to its blender executable", flush=True)
            results[version] = False
            continue
        print(f"== {version}: {path}", flush=True)
        environment = {**os.environ, "BLENDER": path}
        results[version] = subprocess.run([python, "tools/check.py"], cwd=ROOT, env=environment).returncode == 0
    for version, ok in results.items():
        print(f"== {version}: {'ok' if ok else 'FAILED'}", flush=True)
    return 0 if all(results.values()) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true", help="skip the Blender test suite")
    parser.add_argument("--all-blenders", action="store_true", help="the full gate on each supported Blender")
    args = parser.parse_args()

    python = str(venv_python())
    if args.all_blenders:
        return all_blenders(python)
    results = [
        step("ruff check", [python, "-m", "ruff", "check", "."]),
        step("ruff format", [python, "-m", "ruff", "format", "--check", "."]),
        step("mypy", [python, "-m", "mypy"]),
        step("requirements", [python, "tools/requirements_check.py"]),
        # a thin UI: every function of source/ui/ at cyclomatic complexity 3 or less (the logic is in source/service/)
        step("thin UI", [python, "-m", "lizard", "-C", "3", "-w", "source/ui"]),
        # no dead code: vulture with the checked whitelist of names Blender and unittest call by name
        step("dead code", [python, "-m", "vulture", *DEAD_CODE]),
    ]
    print("== extension validate", flush=True)
    validate = run(["--factory-startup", "-c", "extension", "validate", str(SOURCE)], check=False)
    if validate.returncode != 0:
        sys.stdout.write(validate.stdout + validate.stderr)
    results.append(validate.returncode == 0)
    print(f"== extension validate: {'ok' if results[-1] else 'FAILED'}", flush=True)
    if not args.fast:
        install_fresh()
        coverage = [
            f"--line-min={LINE_COVERAGE_MIN}",
            f"--branch-min={BRANCH_COVERAGE_MIN}",
            f"--site={venv_site_packages()}",
        ]
        results.append(run_script(ROOT / "tests" / "run.py", coverage) == 0)
        print("== tests:", "ok" if results[-1] else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
