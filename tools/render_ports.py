# SPDX-License-Identifier: GPL-3.0-or-later

"""Render ported presets next to tree-gen's own trees, to check a port by eye.

    python tools/render_ports.py <tree-gen clone> <out folder> palm fan_palm:fan_palm weeping_willow:willow
    python tools/render_ports.py <clone> <out> palm --presets <ported folder> --presets source/presets

Each argument is a tree-gen species (parametric/tree_params/<species>.py), optionally `:preset_name`. For each,
one PNG per view (front, top) goes to the out folder: tree-gen's tree on the left, then the preset from each
--presets folder (default: source/presets), all with the same seed. The out folder should be outside the repo.
"""

import argparse
import sys
from pathlib import Path

from blender_env import ROOT, SOURCE, install_fresh, run_script


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("treegen", type=Path, help="a git clone of https://github.com/friggog/tree-gen")
    parser.add_argument("out", type=Path, help="the folder the PNG files go to")
    parser.add_argument("species", nargs="+", help="tree-gen species, optionally species:preset_name")
    parser.add_argument("--presets", type=Path, action="append", help="a folder of preset files (repeatable)")
    parser.add_argument("--seed", type=int, default=1, help="the seed of every tree (tree-gen needs one above 0)")
    args = parser.parse_args()

    if not (args.treegen / "parametric" / "tree_params").is_dir():
        sys.exit(f"{args.treegen} is not a tree-gen checkout (no parametric/tree_params)")
    if args.seed < 1:
        sys.exit("--seed must be 1 or more: tree-gen draws a random seed for 0")
    folders = args.presets or [SOURCE / "presets"]
    missing = [str(folder) for folder in folders if not folder.is_dir()]
    if missing:
        sys.exit(f"not a folder: {', '.join(missing)}")
    args.out.mkdir(parents=True, exist_ok=True)
    install_fresh()
    script_args = [
        str(args.treegen.resolve()),
        str(args.out.resolve()),
        str(args.seed),
        ",".join(str(folder.resolve()) for folder in folders),
        *args.species,
    ]
    return run_script(ROOT / "tools" / "render_ports_in_blender.py", script_args)


if __name__ == "__main__":
    sys.exit(main())
