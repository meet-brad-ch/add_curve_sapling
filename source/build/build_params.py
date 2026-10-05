# SPDX-License-Identifier: GPL-3.0-or-later

"""The settings that decide what Blender makes of the grown tree (the model's TreeParams decide how it grows)."""

from typing import Any

from ..model.params import PlainParams, TreeParams, WindParams


class BuildParams(PlainParams):
    """Plain copies of the build settings, with the model's parameters (`tree`) and the wind's (`wind`)."""

    def __init__(self, settings: Any, tree: TreeParams, wind: WindParams) -> None:
        s = settings
        self.tree = tree
        self.wind = wind
        self.bevel_depth = 1.0 if s.bevel else 0.0
        self.bevel_res = int(s.bevelRes)
        self.res_u = int(s.resU)
        self.use_armature = bool(s.useRig)
        self.preview_armature = bool(s.fastPreview)
        self.armature_animation = bool(s.windAnim)
        self.leaf_animation = bool(s.leafFlutter)
        self.make_mesh = bool(s.makeMesh)
        self.leaf_material = bool(s.leafMaterial)
        self.leaf_instance_name = str(s.leafDupliObj)
        self._freeze()
