# SPDX-License-Identifier: GPL-3.0-or-later

"""Data read back from Blender: stored arrays, evaluated meshes, the tree's curves, modifier inputs, F-curves."""

from typing import Any

import bpy
import numpy as np
from bpy_extras import anim_utils

from support.addon import Addon


class Evaluated:
    """Data read back from Blender: stored arrays, evaluated meshes, the tree's curves, modifier inputs, F-curves."""

    @staticmethod
    def floats(collection: Any, attr: str, width: int) -> np.ndarray:
        """Exact stored values (Blender keeps float32), so any drift at all changes the hash."""
        buf = np.empty(len(collection) * width, dtype=np.float32)
        collection.foreach_get(attr, buf)
        return buf

    @staticmethod
    def ints(collection: Any, attr: str, width: int = 1) -> np.ndarray:
        """Stored integer values."""
        buf = np.empty(len(collection) * width, dtype=np.int32)
        collection.foreach_get(attr, buf)
        return buf

    @staticmethod
    def vertices(name: str, frame: int | None = None) -> np.ndarray:
        """An object's evaluated vertex positions (at a frame), as an (n, 3) array."""
        if frame is not None:
            bpy.context.scene.frame_set(frame)
        ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        out = np.empty(len(mesh.vertices) * 3, np.float32)
        mesh.vertices.foreach_get("co", out)
        ob.to_mesh_clear()
        return out.reshape(-1, 3)

    @staticmethod
    def tree_curves() -> Any:
        """The tree's curve source, a Curves object."""
        return bpy.data.objects["tree_curves"]

    @classmethod
    def spline_points(cls) -> list[list[tuple[tuple[float, ...], float]]]:
        """Per spline of the tree, its points as ((x, y, z), radius)."""
        curves = cls.tree_curves().data
        co = cls.floats(curves.position_data, "vector", 3).reshape(-1, 3)
        radius = cls.floats(curves.attributes["radius"].data, "value", 1)
        out = []
        start = 0
        for c in curves.curves:
            size = len(c.points)
            out.append([(tuple(float(v) for v in co[i]), float(radius[i])) for i in range(start, start + size)])
            start += size
        return out

    @staticmethod
    def modifier_inputs(ob: Any) -> dict:
        """The input values of an object's node modifiers (objects by name)."""
        out = {}
        for modifier in ob.modifiers:
            if modifier.type != "NODES" or modifier.node_group is None:
                continue
            values = {}
            for item in modifier.node_group.interface.items_tree:
                if getattr(item, "in_out", "") != "INPUT" or item.socket_type == "NodeSocketGeometry":
                    continue
                value = getattr(modifier.properties.inputs, item.identifier).value
                values[item.name] = value.name if hasattr(value, "name") else Addon.plain(value)
            out[modifier.name] = {"group": modifier.node_group.name, "inputs": values}
        return out

    @staticmethod
    def fcurves_of(ob: Any) -> list:
        """Every F-curve animating ob: its action's, then those of the actions in its NLA strips (a large rig)."""
        ad = ob.animation_data
        if not ad:
            return []
        slots = [(ad.action, ad.action_slot)] if ad.action and ad.action_slot else []
        slots += [(s.action, s.action_slot) for track in ad.nla_tracks for s in track.strips if s.action]
        out = []
        for action, slot in slots:
            channelbag = anim_utils.action_get_channelbag_for_slot(action, slot)
            out += list(channelbag.fcurves) if channelbag else []
        return out
