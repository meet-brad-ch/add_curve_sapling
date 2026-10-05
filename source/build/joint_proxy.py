# SPDX-License-Identifier: GPL-3.0-or-later

"""The joint proxy: a hidden mesh with one vertex per curve point and handle, weighted to the bones.

The rig's Armature modifier deforms this mesh by vertex groups, and the root's sweep reads each curve point's
posed position and handles from it (Sample Index by 3 x point index). So the bark is re-swept from the posed curve
every frame, smooth across the joints, and a stem above the Joint Levels follows the nearest bone below it.
"""

import bpy
import numpy as np
from bpy.types import Object

from ..model.joints import Joints
from .objects import ObjectFactory, VertexGroup, VertexGroupWriter


class JointProxy:
    """Builds the "tree_joints" mesh: vertices (co, left handle, right handle) per curve point, one vertex group per
    bone, every vertex in the group of the joint its point follows."""

    ROLE = "tree_joints"
    PER_POINT = 3  # vertex 3i is point i, 3i + 1 its left handle, 3i + 2 its right handle

    def __init__(self, objects: ObjectFactory) -> None:
        self.objects = objects

    def build(self, root: Object, joints: Joints) -> Object:
        """The hidden proxy under the root, with its vertex groups (the rig's Armature modifier is added by the rig)."""
        flat = joints.flat
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
    def groups(cls, joints: Joints) -> list[VertexGroup]:
        """The vertex groups of the proxy, in joint order: the vertices of every point following that joint."""
        return cls.groups_of(np.repeat(joints.point_ordinals(), cls.PER_POINT), joints)

    @staticmethod
    def groups_of(ordinals: np.ndarray, joints: Joints) -> list[VertexGroup]:
        """One vertex group per joint that has vertices, in joint order, for vertices with these joint numbers."""
        order = np.argsort(ordinals, kind="stable")
        counts = np.bincount(ordinals, minlength=len(joints.joint_point))
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        names = joints.names()
        return [VertexGroup(names[i], order[starts[i] : starts[i] + counts[i]]) for i in range(len(names)) if counts[i]]
