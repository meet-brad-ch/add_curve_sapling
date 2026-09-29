# SPDX-License-Identifier: GPL-3.0-or-later

"""The leaves object: a mesh of leaf quads, or points/faces that instance a leaf object."""

import bpy
from mathutils import Vector

from ..model.leaves import LeafShape
from ..settings import SettingsError
from .tree_record import TreeRecord


class LeafObjectBuilder:
    """Creates the leaves mesh object from a LeafSet."""

    ROLE = "leaves"
    UV_LAYER = "leafUV"

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self, leaves, tree):
        p = self.params
        mesh = bpy.data.meshes.new(self.ROLE)
        ob = self.objects.new(self.ROLE, mesh, parent=tree)
        mesh.from_pydata(leaves.vertices, (), leaves.faces)

        if leaves.shape == LeafShape.INSTANCE_FACES:
            ob.instance_type = "FACES"
            ob.use_instance_faces_scale = True
            ob.instance_faces_scale = 10.0
            self._attach_instance_object(ob)
        elif leaves.shape == LeafShape.INSTANCE_POINTS:
            self._store_rotations(mesh, leaves)

        if leaves.shape in (LeafShape.HEX, LeafShape.RECT):
            self._add_uvs(mesh, leaves.shape, p.leaf_scale_x)
        mesh.validate()
        return ob

    def finish(self, leaves_ob, leaves):
        """Last modifier on the leaves: instance the leaf object on the points (after the armature)."""
        if leaves.shape == LeafShape.INSTANCE_POINTS:
            LeafInstancerNodes.add_modifier(leaves_ob, self.instance_object(self.params))

    @staticmethod
    def instance_object(params):
        """The object instanced as the leaf; raises SettingsError when instanced leaves have none."""
        name = params.leaf_instance_name
        instance = bpy.data.objects.get(name)
        if instance is None:
            raise SettingsError(
                f"Instanced leaves need a Leaf Object (Leaves page); '{name}' is not an object"
                if name
                else "Instanced leaves need a Leaf Object (Leaves page)"
            )
        if instance.get(TreeRecord.ID):
            raise SettingsError(f"Leaf Object '{name}' is part of a Sapling tree; choose your own leaf object")
        return instance

    def _attach_instance_object(self, leaves_ob):
        self.instance_object(self.params).parent = leaves_ob

    @staticmethod
    def _store_rotations(mesh, leaves):
        """Per leaf, the rotation Blender's vertex instancing used to derive from the vertex normal.

        Vertex normals cannot be set since Blender 4.1, so the instancer reads this attribute instead.
        """
        normals = leaves.normals
        rotations: list[float] = []
        for i in range(0, len(normals), 3):
            q = Vector(normals[i : i + 3]).to_track_quat("Y", "Z")
            rotations.extend((q.w, q.x, q.y, q.z))
        attribute = mesh.attributes.new(LeafInstancerNodes.ROTATION, "QUATERNION", "POINT")
        attribute.data.foreach_set("value", rotations)

    def _add_uvs(self, mesh, shape, scale_x):
        """Each leaf maps onto the full 0..1 UV square, narrowed by Leaf Scale X."""
        u1 = 0.5 * (1 - scale_x)
        u2 = 1 - u1
        if shape == LeafShape.RECT:
            per_leaf = [u2, 0, u2, 1, u1, 1, u1, 0]
        else:
            per_leaf = [0.5, 0, u1, 1 / 3, u1, 2 / 3, 0.5, 1, 0.5, 0, 0.5, 1, u2, 2 / 3, u2, 1 / 3]
        layer = mesh.uv_layers.new(name=self.UV_LAYER)
        layer.uv.foreach_set("vector", per_leaf * (len(mesh.loops) * 2 // len(per_leaf)))


class LeafInstancerNodes:
    """Geometry nodes that put one instance of the leaf object on each leaf point, rotated per leaf."""

    GROUP = "Sapling Leaf Instancer"
    VERSION = 1
    ROTATION = "leaf_rotation"
    OBJECT_INPUT = "Leaf Object"
    VERSION_KEY = "sapling_version"

    @classmethod
    def add_modifier(cls, leaves_ob, instance):
        group = cls.node_group()
        modifier = leaves_ob.modifiers.new("Leaf Instances", "NODES")
        modifier.node_group = group
        socket = next(i for i in group.interface.items_tree if getattr(i, "name", "") == cls.OBJECT_INPUT)
        # Blender 5.2: modifier inputs are typed sockets, no longer ID properties
        getattr(modifier.properties.inputs, socket.identifier).value = instance
        return modifier

    @classmethod
    def node_group(cls):
        """The shared node group, rebuilt if it is missing or from another version."""
        group = bpy.data.node_groups.get(cls.GROUP)
        if group is not None and group.bl_idname != "GeometryNodeTree":
            raise SettingsError(f"Node group '{cls.GROUP}' exists but is not a Geometry Nodes group; rename it")
        if group is not None and group.get(cls.VERSION_KEY) == cls.VERSION:
            return group
        if group is None:
            group = bpy.data.node_groups.new(cls.GROUP, "GeometryNodeTree")
        cls._build(group)
        group[cls.VERSION_KEY] = cls.VERSION
        return group

    @classmethod
    def _build(cls, group):
        group.nodes.clear()
        group.interface.clear()
        group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
        group.interface.new_socket(cls.OBJECT_INPUT, in_out="INPUT", socket_type="NodeSocketObject")
        group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")

        nodes = group.nodes
        links = group.links
        inputs = nodes.new("NodeGroupInput")
        output = nodes.new("NodeGroupOutput")
        info = nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "ORIGINAL"  # the leaf object's own geometry, around its origin
        info.inputs["As Instance"].default_value = True
        rotation = nodes.new("GeometryNodeInputNamedAttribute")
        rotation.data_type = "QUATERNION"
        rotation.inputs["Name"].default_value = cls.ROTATION
        instancer = nodes.new("GeometryNodeInstanceOnPoints")

        links.new(inputs.outputs["Geometry"], instancer.inputs["Points"])
        links.new(inputs.outputs[cls.OBJECT_INPUT], info.inputs["Object"])
        links.new(info.outputs["Geometry"], instancer.inputs["Instance"])
        links.new(rotation.outputs["Attribute"], instancer.inputs["Rotation"])
        links.new(instancer.outputs["Instances"], output.inputs["Geometry"])
        for x, node in enumerate((inputs, info, instancer, output)):
            node.location = (x * 220, 0)
        rotation.location = (220, -200)
