# SPDX-License-Identifier: GPL-3.0-or-later

"""The leaves object: a mesh of leaf quads, or points/faces that instance a leaf object."""

import bpy
from bpy.types import Mesh, NodeTree, Object, QuaternionAttribute
from mathutils import Vector

from ..model.leaves import LeafSet, LeafShape
from ..model.params import TreeParams
from ..settings import SettingsError
from .node_groups import SharedNodeGroup
from .objects import ObjectFactory
from .tree_record import TreeRecord


class LeafObjectBuilder:
    """Creates the leaves mesh object from a LeafSet."""

    ROLE = "leaves"
    UV_LAYER = "leafUV"

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, leaves: LeafSet, tree: Object) -> Object:
        """The leaves object under the tree, before any armature; instanced leaves also get their instance set up.

        Face instancing parents the leaf object to the leaves; point instancing stores each leaf's rotation
        (the node modifier comes in finish()); hex and rect leaves get UVs.
        """
        p = self.params
        mesh = bpy.data.meshes.new(self.ROLE)
        ob = self.objects.new(self.ROLE, mesh, parent=tree)
        mesh.from_pydata(leaves.vertices, (), leaves.faces)

        if leaves.shape == LeafShape.INSTANCE_FACES:
            ob.instance_type = "FACES"
            ob.use_instance_faces_scale = True
            ob.instance_faces_scale = LeafShape.FACE_INSTANCE_SCALE
            self._attach_instance_object(ob)
        elif leaves.shape == LeafShape.INSTANCE_POINTS:
            self._store_rotations(mesh, leaves)

        if leaves.shape in (LeafShape.HEX, LeafShape.RECT):
            self._add_uvs(mesh, leaves.shape, p.leaf_scale_x)
        mesh.validate()
        return ob

    def finish(self, leaves_ob: Object, leaves: LeafSet) -> None:
        """Last modifier on the leaves: instance the leaf object on the points (after the armature)."""
        if leaves.shape == LeafShape.INSTANCE_POINTS:
            LeafInstancerNodes.add_modifier(leaves_ob, self.instance_object(self.params))

    @staticmethod
    def instance_object(params: TreeParams) -> Object:
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

    def _attach_instance_object(self, leaves_ob: Object) -> None:
        self.instance_object(self.params).parent = leaves_ob

    @staticmethod
    def _store_rotations(mesh: Mesh, leaves: LeafSet) -> None:
        """Per leaf, the rotation Blender's vertex instancing used to derive from the vertex normal.

        Vertex normals cannot be set since Blender 4.1, so the instancer reads this attribute instead.
        """
        normals = leaves.normals
        rotations: list[float] = []
        for i in range(0, len(normals), 3):
            q = Vector(normals[i : i + 3]).to_track_quat("Y", "Z")
            rotations.extend((q.w, q.x, q.y, q.z))
        attribute: QuaternionAttribute = mesh.attributes.new(LeafInstancerNodes.ROTATION, "QUATERNION", "POINT")  # type: ignore[assignment]  # stub: new() returns the base class
        attribute.data.foreach_set("value", rotations)

    def _add_uvs(self, mesh: Mesh, shape: str, scale_x: float) -> None:
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

    @classmethod
    def add_modifier(cls, leaves_ob: Object, instance: Object) -> None:
        """A Geometry Nodes modifier on the leaves that instances `instance` on each point."""
        group = SharedNodeGroup.ensure(cls.GROUP, cls.VERSION, cls._build)
        modifier = SharedNodeGroup.add_modifier(leaves_ob, "Leaf Instances", group)
        SharedNodeGroup.set_input(modifier, cls.OBJECT_INPUT, instance)

    @classmethod
    def _build(cls, group: NodeTree) -> None:
        """Fill the empty group: Group Input -> Instance on Points (Object Info, rotation attribute) -> Output."""
        # stub: the interface is optional, and socket_type is typed as 'DEFAULT' only (it takes socket idnames)
        group.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only
        group.interface.new_socket(cls.OBJECT_INPUT, in_out="INPUT", socket_type="NodeSocketObject")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only
        group.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only

        nodes = group.nodes
        links = group.links
        inputs = nodes.new("NodeGroupInput")
        output = nodes.new("NodeGroupOutput")
        info = nodes.new("GeometryNodeObjectInfo")
        info.transform_space = "ORIGINAL"  # type: ignore[attr-defined]  # the leaf object's own geometry, around its origin
        info.inputs["As Instance"].default_value = True  # type: ignore[attr-defined]  # stub: NodeSocket base class
        rotation = nodes.new("GeometryNodeInputNamedAttribute")
        rotation.data_type = "QUATERNION"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        rotation.inputs["Name"].default_value = cls.ROTATION  # type: ignore[attr-defined]  # stub: NodeSocket base class
        instancer = nodes.new("GeometryNodeInstanceOnPoints")

        links.new(inputs.outputs["Geometry"], instancer.inputs["Points"])
        links.new(inputs.outputs[cls.OBJECT_INPUT], info.inputs["Object"])
        links.new(info.outputs["Geometry"], instancer.inputs["Instance"])
        links.new(rotation.outputs["Attribute"], instancer.inputs["Rotation"])
        links.new(instancer.outputs["Instances"], output.inputs["Geometry"])
        for x, node in enumerate((inputs, info, instancer, output)):
            node.location = (x * 220, 0)
        rotation.location = (220, -200)
