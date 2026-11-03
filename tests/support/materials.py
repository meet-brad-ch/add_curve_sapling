# SPDX-License-Identifier: GPL-3.0-or-later

"""The materials an object renders with, and their shader nodes."""

import bpy


class Materials:
    """The materials an object renders with, and their shader nodes."""

    @staticmethod
    def evaluated(name):
        """The materials an object renders with (a node modifier's mesh carries its own)."""
        ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        return [slot.material.name if slot.material else None for slot in ob.material_slots]

    @staticmethod
    def principled(material):
        return next(n for n in material.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
