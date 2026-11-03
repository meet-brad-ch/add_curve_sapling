# SPDX-License-Identifier: GPL-3.0-or-later

"""Locate Blender and run it against a throwaway user profile.

Tests and golden recording must never touch the owner's Blender profile, and they must exercise
the extension exactly as users get it: built into a zip and installed into a user repository.
"""

import functools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "source"
BUILD = ROOT / "build"
PROFILE = BUILD / "test-profile"
REPO = "user_default"


def extension_id() -> str:
    """The extension's id from the manifest (tomllib needs Python 3.11; the tools run on 3.10, and the id line is
    plain)."""
    manifest = (SOURCE / "blender_manifest.toml").read_text(encoding="utf-8")
    match = re.search(r'^id = "([^"]+)"$', manifest, re.MULTILINE)
    if match is None:
        sys.exit("source/blender_manifest.toml has no id line")
    return match.group(1)


# The installed add-on's module: bl_ext.<repository>.<extension id>
MODULE = f"bl_ext.{REPO}.{extension_id()}"

# The Blender versions the extension supports (docs/requirements.md SWR-0001); the first is the default

SUPPORTED_VERSIONS = ("Blender 5.2", "Blender 5.3")
DEFAULT_BLENDER = Path(r"C:\Program Files\Blender Foundation\Blender 5.2\blender.exe")


@functools.cache
def blender_path() -> Path:
    """Blender from $BLENDER, else the default 5.2 install, else PATH; it must be a supported version."""
    if "BLENDER" in os.environ:
        path = Path(os.environ["BLENDER"])
        if not path.is_file():
            sys.exit(f"BLENDER={path} does not exist")
    elif DEFAULT_BLENDER.is_file():
        path = DEFAULT_BLENDER
    elif shutil.which("blender"):
        path = Path(str(shutil.which("blender")))
    else:
        sys.exit(f"Blender not found: set BLENDER to the executable of one of {SUPPORTED_VERSIONS}")
    require_version(path)
    return path


def require_version(path: Path) -> None:
    """The tests run on a supported Blender only (the golden files hold exact float32 values of each)."""
    answer = subprocess.run([str(path), "--version"], capture_output=True, text=True)
    if answer.returncode != 0:
        sys.exit(f"{path} --version failed with code {answer.returncode}: {answer.stderr.strip()}")
    version = answer.stdout.splitlines()
    first = "not Blender"
    if version:
        first = version[0]
    if not first.startswith(SUPPORTED_VERSIONS):
        sys.exit(f"{path} is {first}; the tests need one of {SUPPORTED_VERSIONS}")


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
