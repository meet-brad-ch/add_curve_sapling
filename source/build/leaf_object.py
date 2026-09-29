# SPDX-License-Identifier: GPL-3.0-or-later

"""The leaves object: a mesh of leaf quads, or points/faces that instance a leaf object."""

import bpy

from ..model.leaves import LeafShape


class LeafObjectBuilder:
    """Creates the leaves mesh object from a LeafSet."""

    UV_LAYER = "leafUV"

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self, leaves, tree):
        p = self.params
        mesh = bpy.data.meshes.new("leaves")
        ob = self.objects.new("leaves", mesh, parent=tree)
        mesh.from_pydata(leaves.vertices, (), leaves.faces)

        if leaves.shape == LeafShape.INSTANCE_FACES:
            ob.instance_type = "FACES"
            ob.use_instance_faces_scale = True
            ob.instance_faces_scale = 10.0
            self._attach_instance_object(ob)
        elif leaves.shape == LeafShape.INSTANCE_POINTS:
            ob.instance_type = "VERTS"
            ob.use_instance_vertices_rotation = True
            self._attach_instance_object(ob)

        if leaves.shape in (LeafShape.HEX, LeafShape.RECT):
            self._add_uvs(mesh, leaves.shape, p.leaf_scale_x)
        mesh.validate()
        return ob

    def _attach_instance_object(self, leaves_ob):
        name = self.params.leaf_instance_object
        instance = bpy.data.objects.get(name) if name != "NONE" else None
        if instance:
            instance.parent = leaves_ob

    def _add_uvs(self, mesh, shape, scale_x):
        """Each leaf maps onto the full 0..1 UV square, narrowed by Leaf Scale X."""
        u1 = 0.5 * (1 - scale_x)
        u2 = 1 - u1
        if shape == LeafShape.RECT:
            per_leaf = [u2, 0, u2, 1, u1, 1, u1, 0]
        else:
            per_leaf = [0.5, 0, u1, 1 / 3, u1, 2 / 3, 0.5, 1, 0.5, 0, 0.5, 1, u2, 2 / 3, u2, 1 / 3]
        layer = mesh.uv_layers.new(name=self.UV_LAYER)
        layer.data.foreach_set("uv", per_leaf * (len(mesh.loops) * 2 // len(per_leaf)))
