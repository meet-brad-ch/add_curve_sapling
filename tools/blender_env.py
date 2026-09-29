# SPDX-License-Identifier: GPL-3.0-or-later

"""Locate Blender and run it against a throwaway user profile.

Tests and golden recording must never touch the owner's Blender profile, and they must exercise
the extension exactly as users get it: built into a zip and installed into a user repository.
"""

import functools
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source"
BUILD = ROOT / "build"
PROFILE = BUILD / "test-profile"
REPO = "user_default"

REQUIRED_VERSION = "Blender 5.2"
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@functools.cache
def blender_path() -> Path:
    """Blender from $BLENDER, else the default 5.2 install, else PATH; it must be Blender 5.2."""
    if "BLENDER" in os.environ:
        path = Path(os.environ["BLENDER"])
        if not path.is_file():
            sys.exit(f"BLENDER={path} does not exist")
    elif DEFAULT_BLENDER.is_file():
        path = DEFAULT_BLENDER
    elif shutil.which("blender"):
        path = Path(str(shutil.which("blender")))
    else:
        sys.exit("Blender not found: set BLENDER to the Blender 5.2 executable")
    require_version(path)
    return path


def require_version(path: Path) -> None:
    """The golden files hold exact float32 values, valid for one Blender version only."""
    version = subprocess.run([str(path), "--version"], capture_output=True, text=True).stdout.splitlines()
    if not version or not version[0].startswith(REQUIRED_VERSION):
        sys.exit(f"{path} is {version[0] if version else 'not Blender'}; the tests need {REQUIRED_VERSION}")


def venv_python() -> Path:
    """Python of the project venv (Python 3.13 with the pinned tools of requirements-dev.txt)."""
    for candidate in (ROOT / ".venv" / "Scripts" / "python.exe", ROOT / ".venv" / "bin" / "python"):
        if candidate.exists():
            return candidate
    sys.exit("No .venv: create it as described in README (How to run).")


def venv_site_packages() -> Path:
    """site-packages of the project venv; Blender imports coverage from there for --coverage."""
    unix = (ROOT / ".venv" / "lib").glob("python3.*/site-packages")
    for candidate in (ROOT / ".venv" / "Lib" / "site-packages", *unix):
        if candidate.is_dir():
            return candidate
    sys.exit("No .venv site-packages: create the venv as described in README (How to run).")


def profile_env() -> dict[str, str]:
    env = dict(os.environ)
    env["BLENDER_USER_RESOURCES"] = str(PROFILE)
    return env


def run(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = [str(blender_path()), *args]
    result = subprocess.run(cmd, env=profile_env(), cwd=ROOT, text=True, capture_output=True)
    if check and result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        sys.exit(f"Failed ({result.returncode}): {' '.join(cmd)}")
    return result


def install_fresh() -> None:
    """Build the extension zip and install it into a new, empty profile."""
    if PROFILE.exists():
        shutil.rmtree(PROFILE)
    PROFILE.mkdir(parents=True)
    for old in BUILD.glob("sapling_tree_gen-*.zip"):
        old.unlink()
    run(["--factory-startup", "-c", "extension", "build", "--source-dir", str(SOURCE), "--output-dir", str(BUILD)])
    packages = list(BUILD.glob("sapling_tree_gen-*.zip"))
    if len(packages) != 1:
        sys.exit(f"expected one built package in {BUILD}, found {[p.name for p in packages]}")
    (package,) = packages
    run(["--factory-startup", "-c", "extension", "install-file", "-r", REPO, "-e", str(package)])


def run_script(script: Path, script_args: list[str]) -> int:
    """Run a Python script in headless Blender; stream its output; return Blender's exit code."""
    cmd = [str(blender_path()), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)]
    cmd += ["--", *script_args]
    return subprocess.run(cmd, env=profile_env(), cwd=ROOT).returncode
