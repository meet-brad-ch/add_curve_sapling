# SPDX-License-Identifier: GPL-3.0-or-later

"""The golden trees' data: recording or comparing, and the Blender versions it holds for."""

import bpy
from blender_env import SUPPORTED_VERSIONS


class Golden:
    """Whether the golden test records new golden files (tests/run.py --record-golden) instead of comparing.

    One data set serves every supported Blender version: Blender 5.2.2 and 5.3.0 beta build bit-identical trees
    for all 77 cases (compared 2026-11-03). The gate runs on each supported version, so a version that differs
    fails at the first differing field; only then would a version need its own data."""

    record = False

    @staticmethod
    def running_supported() -> bool:
        """Whether the running Blender is a supported version."""
        return f"Blender {bpy.app.version_string}".startswith(SUPPORTED_VERSIONS)
