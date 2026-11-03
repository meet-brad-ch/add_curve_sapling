# SPDX-License-Identifier: GPL-3.0-or-later

"""Trees for the node-tree tests: settings, model joints, modifier inputs, wind joints, the legacy bevel."""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import bpy
import numpy as np

from support.addon import Addon
from support.evaluated import Evaluated
from support.mesh_counts import MeshCounts
from support.model import Model


@dataclass(frozen=True)
class ModelJoints:
    """A tree grown in the model alone (no Blender objects) and its joints."""

    model: Any
    joints: Any


class NodeTrees:
    """Trees for the node-tree tests: settings, model joints, modifier inputs, wind joints."""

    @staticmethod
    def settings(**changes):
        """Quaking aspen settings with 2 levels, no leaves and Bevel at resolution 1, with the changes."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=False, bevel=True, bevelRes=1)
        settings.update(changes)
        return settings

    @staticmethod
    def counts(name) -> MeshCounts:
        """The evaluated mesh's element counts of the object (its temporary mesh is freed after, also on a failure)."""
        ob = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        try:
            return MeshCounts.of(mesh)
        finally:
            ob.to_mesh_clear()

    @staticmethod
    def model_joints(**changes):
        """The Joints of a tree grown in the model alone, with the tree."""
        settings = NodeTrees.settings(**changes)
        model = Model.grow(settings)
        return ModelJoints(model, Model.joints(settings, model))

    @staticmethod
    def empty_leaves(grown):
        """A leaf set with no leaves (the arrays leaf_joints reads), for a tree grown in the model alone."""
        return SimpleNamespace(
            parent_spline=np.zeros(0, np.int64), parent_point=np.zeros(0, np.int64), verts_per_leaf=4
        )

    @staticmethod
    def set_input(ob, name, value):
        """Set an input of the root's "Sapling Tree" modifier, as a user does in the modifier panel."""
        Addon.module("build.node_groups").SharedNodeGroup.set_input(ob.modifiers["Sapling Tree"], name, value)
        ob.update_tag()

    @staticmethod
    def wind_joint_positions(frame, joints):
        """Where the heads of these joints (numbers) are at a frame: the wind curves' evaluated transform at each
        (a joint's own pose turns about its head, so its inclusive transform puts the head where the joints above
        put it)."""
        bpy.context.scene.frame_set(frame)
        wind = bpy.data.objects["tree_wind"].evaluated_get(bpy.context.evaluated_depsgraph_get()).data
        n = len(wind.position_data)
        co = np.empty(n * 3, np.float32)
        wind.position_data.foreach_get("vector", co)
        flat = np.empty(n * 16, np.float32)
        wind.attributes["fk_incl"].data.foreach_get("value", flat)
        matrices = flat.reshape(n, 4, 4).transpose(0, 2, 1)  # stored by columns
        heads = np.einsum("nij,nj->ni", matrices[:, :3, :3], co.reshape(-1, 3)) + matrices[:, :3, 3]
        return heads[joints]


class LegacyBevel:
    """The bark as the old tree drew it: a legacy curve with the same points and handles, bevelled by Blender."""

    @staticmethod
    def legacy_curve(curves):
        """A legacy Curve datablock with the Curves' points, handles, handle types and radii."""
        data = bpy.data.curves.new("legacy_bevel", "CURVE")
        data.dimensions = "3D"
        attributes = curves.attributes
        co = Evaluated.floats(curves.position_data, "vector", 3).reshape(-1, 3)
        left = Evaluated.floats(attributes["handle_left"].data, "vector", 3).reshape(-1, 3)
        right = Evaluated.floats(attributes["handle_right"].data, "vector", 3).reshape(-1, 3)
        radius = Evaluated.floats(attributes["radius"].data, "value", 1)
        h1 = Evaluated.ints(attributes["handle_type_left"].data, "value")
        h2 = Evaluated.ints(attributes["handle_type_right"].data, "value")
        start = 0
        for c in curves.curves:
            size = len(c.points)
            span = slice(start, start + size)
            points = data.splines.new("BEZIER").bezier_points
            points.add(size - 1)
            points.foreach_set("handle_left_type", h1[span].tolist())
            points.foreach_set("handle_right_type", h2[span].tolist())
            points.foreach_set("co", co[span].ravel())
            points.foreach_set("handle_left", left[span].ravel())
            points.foreach_set("handle_right", right[span].ravel())
            points.foreach_set("radius", radius[span])
            start += size
        return data

    @classmethod
    def counts(cls, settings):
        """The mesh element counts of the old bevel: the tree's curves swept with the settings in a temporary object."""
        data = cls.legacy_curve(Evaluated.tree_curves().data)
        data.bevel_depth = 1.0 if settings["bevel"] else 0.0
        data.bevel_resolution = settings["bevelRes"]
        data.resolution_u = settings["resU"]
        ob = bpy.data.objects.new("legacy_bevel", data)
        bpy.context.scene.collection.objects.link(ob)
        try:
            return NodeTrees.counts(ob.name)
        finally:
            bpy.data.objects.remove(ob)
            bpy.data.curves.remove(data)
