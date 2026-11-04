# SPDX-License-Identifier: GPL-3.0-or-later

"""Render the media of the Extensions Platform listing into docs/listing/.

    python tools/render_listing.py

It builds and installs the extension in the test profile, then runs tools/render_listing_in_blender.py: the featured
picture (featured.jpg), the gallery pictures (gallery_<preset>.jpg, 1920 x 1080) and the icon (icon.png,
256 x 256). The pictures have the look of the presets page. They are CC0 and uploaded on the listing page by hand.
"""

import sys

from blender_env import ROOT, BlenderEnv

OUT = ROOT / "docs" / "listing"
SCRIPT = ROOT / "tools" / "render_listing_in_blender.py"


def main() -> int:
    """Render the listing media. Returns Blender's exit code."""
    OUT.mkdir(parents=True, exist_ok=True)
    BlenderEnv.install_fresh()
    return BlenderEnv.run_script(SCRIPT, [str(OUT)])


if __name__ == "__main__":
    sys.exit(main())
