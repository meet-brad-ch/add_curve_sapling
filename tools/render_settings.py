# SPDX-License-Identifier: GPL-3.0-or-later

"""Render the pictures of the help pages (docs/manual/pictures/).

    python tools/render_settings.py               # every strip
    python tools/render_settings.py split_angle   # only these strips

It builds and installs the extension in the test profile, then runs tools/render_settings_in_blender.py: one strip
per setting in its Strips.ALL, each the same preset at three values, with the look of the presets page.
"""

import sys

from blender_env import ROOT, BlenderEnv

OUT = ROOT / "docs" / "manual" / "pictures"
SCRIPT = ROOT / "tools" / "render_settings_in_blender.py"


def main() -> int:
    """Render the strips named on the command line (none: all). Returns Blender's exit code."""
    OUT.mkdir(parents=True, exist_ok=True)
    BlenderEnv.install_fresh()
    return BlenderEnv.run_script(SCRIPT, [str(OUT), *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
