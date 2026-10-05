# SPDX-License-Identifier: GPL-3.0-or-later

"""Make Mesh: the bark baked into the root's own mesh, weighted to the rig's bones or following the node wind.

The live sweep is evaluated once at rest and copied into a plain mesh that replaces the root's empty mesh and its
"Sapling Tree" modifier: the tree exports as it is (with the rig, as a skinned mesh), at the price of fixed Bevel
inputs and a heavier playback (every vertex is deformed). Each vertex knows its joint through the joint number
written on the curve points as a float (Resample Curve interpolates it inside a segment, and the floor gives the
joint the segment starts with) and so gets the bone's vertex group, or the joint number for the Follow Wind
modifier.
"""

from typing import Any

import bpy
import numpy as np
from bpy.types import Context, Object

from ..model.params import TreeParams
from .armature import ArmatureBuilder
from .joint_proxy import JointProxy
from .node_groups import SharedNodeGroup
from .node_wind import NodeWind, WindJoints
from .objects import VertexGroupWriter
from .tree_root import TreeRootBuilder


class BarkBake:
    """Bakes the root's sweep into its mesh, and binds the mesh to the rig or the node wind."""

    ORDINAL = "sapling_ordinal"
    # Resample Curve gives a vertex inside a segment the fraction of the way to the next joint: round down to its own
    ROUNDING = 1e-3

    def __init__(self, params: TreeParams, context: Context) -> None:
        self.params = params
        self.context = context

    def bake(
        self, root: Object, curves_ob: Object, joints: WindJoints, armature_ob: Object | None, wind_ob: Object | None
    ) -> None:
        """Replace the root's live sweep by the baked mesh; with `armature_ob` weighted to its bones, with the node
        wind's curves `wind_ob` following them."""
        p = self.params
        ordinals = joints.ordinals(joints.point_joints())
        attribute: Any = curves_ob.data.attributes.new(self.ORDINAL, "FLOAT", "POINT")  # type: ignore[union-attr]  # a Curves object; Any: the data type depends on the kind
        attribute.data.foreach_set("value", ordinals.astype(np.float32))
        mesh = self._realized(root)
        curves_ob.data.attributes.remove(attribute)  # type: ignore[union-attr]  # as above
        vertex_ordinals = self._vertex_ordinals(mesh, len(joints.joint_point))
        mesh.attributes.remove(mesh.attributes[self.ORDINAL])
        if NodeWind.JOINT in mesh.attributes:
            # the curve points' joint numbers, rounded inside the segments by the resample: the float ordinal above
            # gives every vertex its joint; the Follow Wind modifier gets its own, exact numbers below
            mesh.attributes.remove(mesh.attributes[NodeWind.JOINT])
        old = root.data
        root.data = mesh
        bpy.data.meshes.remove(old)  # type: ignore[arg-type]  # the root's data is a mesh
        mesh.name = TreeRootBuilder.ROLE
        root.modifiers.remove(root.modifiers[TreeRootBuilder.MODIFIER])
        if armature_ob is not None:
            VertexGroupWriter.assign(root, JointProxy.groups_of(vertex_ordinals, joints))
            modifier = ArmatureBuilder.deform(root, armature_ob, by_envelopes=False)
            modifier.show_viewport = not p.preview_armature
        elif wind_ob is not None:
            NodeWind.follow(root, wind_ob, vertex_ordinals.astype(np.int32))
        if p.preview_armature:
            root.display_type = "BOUNDS"  # a baked tree has no curves to show instead

    def _realized(self, root: Object) -> bpy.types.Mesh:
        """The sweep at rest (no wind, no rig pose, no preview) as a new mesh with the sweep's attributes."""
        modifier = root.modifiers[TreeRootBuilder.MODIFIER]
        for name in ("Wind", "Rig", "Fast Preview"):
            SharedNodeGroup.set_input(modifier, name, False)  # type: ignore[arg-type]  # the root's modifier runs nodes
        depsgraph = self.context.evaluated_depsgraph_get()
        mesh = bpy.data.meshes.new_from_object(root.evaluated_get(depsgraph))
        if len(mesh.vertices) == 0:
            raise RuntimeError("the baked bark has no vertices")
        return mesh

    @classmethod
    def _vertex_ordinals(cls, mesh: bpy.types.Mesh, joint_count: int) -> np.ndarray:
        """The joint number of every vertex, from the interpolated ordinal attribute."""
        values = np.empty(len(mesh.vertices), np.float32)
        attribute: Any = mesh.attributes[cls.ORDINAL]  # Any: the data type depends on the attribute's kind
        attribute.data.foreach_get("value", values)
        ordinals = np.floor(values + cls.ROUNDING).astype(np.int64)
        if ordinals.min() < 0 or ordinals.max() >= joint_count:
            raise RuntimeError(
                f"baked joint numbers {ordinals.min()}..{ordinals.max()} outside the {joint_count} joints"
            )
        return ordinals
