# SPDX-License-Identifier: GPL-3.0-or-later

"""The full gate: lint, format check, manifest validation, test suite.

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


def main() -> int:
    results = [
        step("ruff check", ["ruff", "check", "."]),
        step("ruff format", ["ruff", "format", "--check", "."]),
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
