# SPDX-License-Identifier: GPL-3.0-or-later

"""Take a picture of each page of the Add Tree panel for the help pages (docs/manual/panel/).

    python tools/capture_panel.py

It builds and installs the extension in the test profile, then starts a Blender window with simulated input
(--enable-event-simulate: the window ignores the real mouse and keyboard) that runs
tools/capture_panel_in_blender.py: it adds a tree from the F3 menu search, opens the Adjust Last Operation panel and
saves each page. The window opens on the desktop for about half a minute and closes by itself. The run fails when
Blender prints FAILED or does not write one picture per page.
"""

import subprocess
import sys

from blender_env import ROOT, BlenderEnv

OUT = ROOT / "docs" / "manual" / "panel"
SCRIPT = ROOT / "tools" / "capture_panel_in_blender.py"
PAGES = 9  # the pages of the panel (Choices.PAGES)


def main() -> int:
    """Capture the pages. Returns 0 when every page has its picture, else 1."""
    OUT.mkdir(parents=True, exist_ok=True)
    BlenderEnv.install_fresh()
    command = [str(BlenderEnv.blender_path()), "--factory-startup", "--enable-event-simulate", "--python", str(SCRIPT)]
    command += ["--", str(OUT)]
    done = subprocess.run(command, env=BlenderEnv.profile_env(), cwd=ROOT, capture_output=True, text=True, check=False)
    lines = done.stdout.splitlines()
    failed = [line for line in lines if line.startswith("FAILED")]
    written = [line for line in lines if line.startswith("WROTE")]
    for line in written + failed:
        print(line)
    if failed or len(written) != PAGES:
        print(f"FAILED: {len(written)} of {PAGES} pages captured (Blender exit code {done.returncode})")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
