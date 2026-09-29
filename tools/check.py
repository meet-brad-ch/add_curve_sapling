# SPDX-License-Identifier: GPL-3.0-or-later

"""The full gate: lint, format check, type check, manifest validation, test suite.

python tools/check.py
"""

import subprocess
import sys

from blender_env import ROOT, SOURCE, install_fresh, run, run_script


def step(title: str, cmd: list[str]) -> bool:
    print(f"== {title}", flush=True)
    ok = subprocess.run(cmd, cwd=ROOT).returncode == 0
    print(f"== {title}: {'ok' if ok else 'FAILED'}", flush=True)
    return ok


def venv_python() -> str:
    """mypy runs from the project venv (Python 3.13 with the Blender 5.2 stubs), see README."""
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return str(candidate)
    sys.exit("No .venv: create it as described in README (How to run).")


def main() -> int:
    results = [
        step("ruff check", ["ruff", "check", "."]),
        step("ruff format", ["ruff", "format", "--check", "."]),
        step("mypy", [venv_python(), "-m", "mypy"]),
    ]
    print("== extension validate", flush=True)
    run(["--factory-startup", "-c", "extension", "validate", str(SOURCE)])
    print("== extension validate: ok", flush=True)
    install_fresh()
    results.append(run_script(ROOT / "tests" / "run.py", []) == 0)
    print("== tests:", "ok" if results[-1] else "FAILED")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
