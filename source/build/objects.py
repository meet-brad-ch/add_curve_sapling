# SPDX-License-Identifier: GPL-3.0-or-later

"""Creating the tree's objects in the scene, and removing them again."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, Self

import bmesh
import bpy
import numpy as np
from bpy.types import ID, Collection, Mesh, Object
from mathutils import Matrix


@dataclass(frozen=True, slots=True)
class ParentLink:
    """How an object hangs from its parent (all parent types, not only OBJECT)."""

    parent: Object | None
    parent_type: Literal["OBJECT", "ARMATURE", "LATTICE", "VERTEX", "VERTEX_3", "BONE"]
    parent_bone: str
    parent_vertices: list[int]

    @classmethod
    def of(cls, ob: Object) -> Self:
        """The current parent link of ob."""
        vertices = [int(v) for v in ob.parent_vertices]  # type: ignore[attr-defined]  # stub: bpy_prop_array is iterable
        return cls(ob.parent, ob.parent_type, ob.parent_bone, vertices)

    def attach(self, ob: Object, parent: Object | None = None) -> None:
        """Parent ob the same way, to `parent` if given (the new tree's object), else to the recorded parent.

        Only sets the parenting; the caller restores the world matrix.
        """
        ob.parent = parent if parent is not None else self.parent
        ob.parent_type = self.parent_type
        if self.parent_type == "BONE":
            ob.parent_bone = self.parent_bone
        if self.parent_type in {"VERTEX", "VERTEX_3"}:
            ob.parent_vertices = self.parent_vertices  # type: ignore[assignment]  # stub: takes a sequence


@dataclass(frozen=True, slots=True)
class AdoptedObject:
    """A user's object the tree took as a child, with where it hung before (restored if the build fails)."""

    ob: Object
    link: ParentLink
    matrix: Matrix


class TreeParts(Protocol):
    """The objects of one generated tree by role (the generator's TreeResult; build/ must not import it)."""

    roles: dict[str, Object]
    objects: "ObjectFactory"

    @property
    def root(self) -> Object:
        """The tree object every other part hangs from."""

    def role(self, name: str) -> Object | None:
        """The object with this role, or None when this tree has none."""


class ObjectFactory:
    """Creates the tree's objects in the target collections and knows each one by its role.

    The role is the object's base name ("tree", "tree_curves", "tree_joints", "tree_wind", "leaves", "treeArm",
    "envelope"); Blender appends ".001" when an older tree still holds the name, and take_base_names() takes it back.
    """

    SUFFIX = re.compile(r"\.\d{3,}$")

    def __init__(self, collections: Sequence[Collection]) -> None:
        if not collections:
            raise ValueError("a tree needs at least one collection to be linked into")
        self.collections = list(collections)
        self.roles: dict[str, Object] = {}
        self.adopted: list[AdoptedObject] = []

    def new(self, role: str, data: ID | None, parent: Object | None = None) -> Object:
        """A new object for this role, linked into every target collection; raises ValueError if the role exists."""
        if role in self.roles:
            raise ValueError(f"the tree already has a '{role}' object")
        ob = bpy.data.objects.new(role, data)
        for collection in self.collections:
            collection.objects.link(ob)
        if parent:
            ob.parent = parent
        self.roles[role] = ob
        return ob

    def adopt(self, ob: Object, parent: Object) -> None:
        """Parent a user's object (the leaf instance object) to one of the tree's; discard() puts it back."""
        self.adopted.append(AdoptedObject(ob, ParentLink.of(ob), ob.matrix_world.copy()))
        ob.parent = parent

    @property
    def created(self) -> list[Object]:
        """The objects created so far, in creation order."""
        return list(self.roles.values())

    def discard(self) -> None:
        """Remove everything created so far and put the adopted objects back (after a failed generation)."""
        for adopted in self.adopted:
            adopted.link.attach(adopted.ob)
            adopted.ob.matrix_world = adopted.matrix
        self.adopted.clear()
        self.remove(self.created)
        self.roles.clear()

    def take_base_names(self) -> None:
        """Rename objects, their data and actions to the names without Blender's .001 suffix."""
        for role, ob in self.roles.items():
            ob.name = role
            for block in self._owned_data(ob):
                block.name = self.SUFFIX.sub("", block.name)

    @classmethod
    def remove(cls, objects: Sequence[Object]) -> None:
        """Delete the objects with the data and actions only they use, in one batch."""
        blocks: list[ID] = list(objects)
        for ob in objects:
            blocks.extend(block for block in cls._owned_data(ob) if block.users == 1)
        bpy.data.batch_remove(blocks)

    @staticmethod
    def _owned_data(ob: Object) -> list[ID]:
        """The object's data and animation action: the blocks it may be the only user of."""
        blocks: list[ID] = [ob.data] if ob.data is not None else []
        animation = ob.animation_data
        if animation and animation.action:
            blocks.append(animation.action)
        if animation:  # a large rig's wind is split over actions in NLA strips
            blocks += [strip.action for track in animation.nla_tracks for strip in track.strips if strip.action]
        return blocks


@dataclass(frozen=True, slots=True)
class VertexGroup:
    """A vertex group to write: its name, and the indices of the vertices in it (all at weight 1.0)."""

    name: str
    indices: np.ndarray


@dataclass(frozen=True, slots=True)
class AttributeSpec:
    """What identifies a mesh attribute that holds data: its name, domain and data type."""

    name: str
    domain: str
    kind: str


class VertexGroupWriter:
    """Vertex groups in one pass: the groups by name, then every weight through a bmesh deform layer.

    VertexGroup.add costs Blender time in proportion to the number of groups (it looks the group up in a list),
    so adding the weights group by group was quadratic in the bones; the deform layer is written in O(1) per vertex.
    """

    @staticmethod
    def assign(ob: Object, groups: list[VertexGroup]) -> None:
        """One group per entry, in order, with each listed vertex in it at weight 1.0 (ob has no groups yet).

        Raises RuntimeError if the bmesh round trip changed the mesh's attributes (it must not lose data).
        """
        for group in groups:
            ob.vertex_groups.new(name=group.name)
        mesh: Mesh = ob.data  # type: ignore[assignment]  # vertex groups are written on mesh objects
        before = VertexGroupWriter.attributes(mesh)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            layer = bm.verts.layers.deform.verify()
            bm.verts.ensure_lookup_table()
            for number, group in enumerate(groups):
                for index in group.indices.tolist():
                    bm.verts[index][layer][number] = 1.0
            bm.to_mesh(mesh)
        finally:
            bm.free()
        after = VertexGroupWriter.attributes(mesh)
        if after != before:
            raise RuntimeError(f"Writing the vertex groups changed the mesh's attributes: {before} -> {after}")

    @staticmethod
    def attributes(mesh: Mesh) -> list[AttributeSpec]:
        """Every attribute that holds data, sorted by name.

        Left out: Blender's internal storage (names starting with "."; bmesh adds topology and UV selection
        layers), attributes on a domain with no elements (bmesh drops sharp_face from a mesh without faces), and
        material_index (bmesh keeps it on its faces and writes the attribute back only when an index is not 0).
        """
        sizes = {
            "POINT": len(mesh.vertices),
            "EDGE": len(mesh.edges),
            "FACE": len(mesh.polygons),
            "CORNER": len(mesh.loops),
        }
        specs = [
            AttributeSpec(a.name, a.domain, a.data_type)
            for a in mesh.attributes
            if not a.name.startswith(".") and a.name != "material_index" and sizes[a.domain]
        ]
        return sorted(specs, key=lambda spec: spec.name)
