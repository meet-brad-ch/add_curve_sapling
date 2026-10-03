# SPDX-License-Identifier: GPL-3.0-or-later

"""Port tree-gen species to built-in presets (the mapping is in tools/port_treegen_in_blender.py).

    git clone https://github.com/friggog/tree-gen <dir>
    python tools/port_treegen.py <dir> black_tupelo weeping_willow:willow ...

Each argument is a tree-gen species (parametric/tree_params/<species>.py), optionally `:preset_name`.
The presets are written to source/presets; render and check each one before committing it.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from blender_env import ROOT, SOURCE, install_fresh, run_script


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("treegen", type=Path, help="a git clone of https://github.com/friggog/tree-gen")
    parser.add_argument("species", nargs="+", help="tree-gen species, optionally species:preset_name")
    args = parser.parse_args()

    if not (args.treegen / "parametric" / "tree_params").is_dir():
        sys.exit(f"{args.treegen} is not a tree-gen checkout (no parametric/tree_params)")
    commit = subprocess.run(
        ["git", "-C", str(args.treegen), "rev-parse", "--short=7", "HEAD"], capture_output=True, text=True, check=True
    ).stdout.strip()
    install_fresh()
    script_args = [str(args.treegen.resolve()), commit, str(SOURCE / "presets"), *args.species]
    return run_script(ROOT / "tools" / "port_treegen_in_blender.py", script_args)


if __name__ == "__main__":
    sys.exit(main())
