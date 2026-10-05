# SPDX-License-Identifier: GPL-3.0-or-later

"""The joint proxy: a hidden mesh with one vertex per curve point and handle, weighted to the bones.

The rig's Armature modifier deforms this mesh by vertex groups, and the root's sweep reads each curve point's
posed position and handles from it (Sample Index by 3 x point index). So the bark is re-swept from the posed curve
every frame, smooth across the joints, and a stem above the Joint Levels follows the nearest bone below it.
"""

import bpy
import numpy as np
from bpy.types import Object

from ..model.curve_data import CurveData
from ..model.params import TreeParams
from ..model.stem import BoneName
from .node_wind import WindJoints
from .objects import ObjectFactory, VertexGroupWriter


class JointProxy:
    """Builds the "tree_joints" mesh: vertices (co, left handle, right handle) per curve point, one vertex group per
    bone, every vertex in the group of the joint its point follows."""

    ROLE = "tree_joints"
    PER_POINT = 3  # vertex 3i is point i, 3i + 1 its left handle, 3i + 2 its right handle

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, root: Object, curve: CurveData, joints: WindJoints) -> Object:
        """The hidden proxy under the root, with its vertex groups (the rig's Armature modifier is added by the rig)."""
        flat = curve.flatten()
        mesh = bpy.data.meshes.new(self.ROLE)
        vertices = np.stack([flat.co, flat.left, flat.right], axis=1).reshape(-1, 3).astype(np.float32)
        mesh.vertices.add(len(vertices))
        mesh.vertices.foreach_set("co", vertices.ravel())
        mesh.update()
        ob = self.objects.new(self.ROLE, mesh, parent=root)
        # a part the root reads: hidden itself, still evaluated for the root (Object > Visibility shows it again)
        ob.hide_viewport = True
        ob.hide_render = True
        VertexGroupWriter.assign(ob, self.groups(joints))
        return ob

    @classmethod
    def groups(cls, joints: WindJoints) -> dict[str, list[int]]:
        """Vertex indices per bone name, in joint order: the vertices of every point following that joint."""
        ordinals = np.repeat(joints.ordinals(joints.point_joints()), cls.PER_POINT)
        order = np.argsort(ordinals, kind="stable")
        counts = np.bincount(ordinals, minlength=len(joints.joint_point))
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        names = cls.bone_names(joints)
        return {names[i]: order[starts[i] : starts[i] + counts[i]].tolist() for i in range(len(names)) if counts[i]}

    @staticmethod
    def bone_names(joints: WindJoints) -> list[str]:
        """The rig's bone name of every joint (ArmatureBuilder names a bone after the point it starts at)."""
        splines, points = joints.joint_spline.tolist(), joints.joint_n.tolist()
        return [BoneName.of(spline, point) for spline, point in zip(splines, points, strict=True)]
