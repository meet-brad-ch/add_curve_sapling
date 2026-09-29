# SPDX-License-Identifier: GPL-3.0-or-later

"""Locate Blender and run it against a throwaway user profile.

Tests and golden recording must never touch the owner's Blender profile, and they must exercise
the extension exactly as users get it: built into a zip and installed into a user repository.
"""

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
MODULE = f"bl_ext.{REPO}.sapling_tree_gen"

DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


def blender_path() -> Path:
    """Blender from $BLENDER, else the default 5.2 install, else PATH."""
    candidate = os.environ.get("BLENDER")
    if candidate:
        return Path(candidate)
    if DEFAULT_BLENDER.exists():
        return DEFAULT_BLENDER
    found = shutil.which("blender")
    if found:
        return Path(found)
    sys.exit("Blender not found: set BLENDER to the blender executable.")


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
    (package,) = BUILD.glob("sapling_tree_gen-*.zip")
    run(["--factory-startup", "-c", "extension", "install-file", "-r", REPO, "-e", str(package)])


def run_script(script: Path, script_args: list[str]) -> int:
    """Run a Python script in headless Blender; stream its output; return Blender's exit code."""
    cmd = [str(blender_path()), "-b", "--factory-startup", "--python-exit-code", "1", "--python", str(script)]
    cmd += ["--", *script_args]
    return subprocess.run(cmd, env=profile_env(), cwd=ROOT).returncode
