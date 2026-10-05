# SPDX-License-Identifier: GPL-3.0-or-later

"""The gate: lint, format, types, manifest, then the test suite with line and branch coverage.

python tools/check.py          # everything (run before merging)
python tools/check.py --fast   # without the Blender test suite (the pre-commit hook)
"""

import argparse
import subprocess
import sys

from blender_env import ROOT, SOURCE, install_fresh, run, run_script, venv_python, venv_site_packages

# Coverage of the add-on the test suite must reach, in percent (the gate prints the measured values)
LINE_COVERAGE_MIN = 99
BRANCH_COVERAGE_MIN = 96


def step(title: str, cmd: list[str]) -> bool:
    print(f"== {title}", flush=True)
    ok = subprocess.run(cmd, cwd=ROOT).returncode == 0
    print(f"== {title}: {'ok' if ok else 'FAILED'}", flush=True)
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fast", action="store_true", help="skip the Blender test suite")
    args = parser.parse_args()

    python = str(venv_python())
    results = [
        step("ruff check", [python, "-m", "ruff", "check", "."]),
        step("ruff format", [python, "-m", "ruff", "format", "--check", "."]),
        step("mypy", [python, "-m", "mypy"]),
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
