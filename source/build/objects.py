# SPDX-License-Identifier: GPL-3.0-or-later

"""Creating the tree's objects in the scene, and removing them again."""

import re
from collections.abc import Mapping, Sequence

import bmesh
import bpy
from bpy.types import ID, Collection, Mesh, Object


class ObjectFactory:
    """Creates the tree's objects in the target collections and knows each one by its role.

    The role is the object's base name ("tree", "tree_curves", "tree_joints", "leaves", "treeArm", "treemesh",
    "envelope"); Blender
    appends ".001" when an older tree still holds the name, and take_base_names() takes it back.
    """

    SUFFIX = re.compile(r"\.\d{3,}$")

    def __init__(self, collections: Sequence[Collection]) -> None:
        if not collections:
            raise ValueError("a tree needs at least one collection to be linked into")
        self.collections = list(collections)
        self.roles: dict[str, Object] = {}

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

    @property
    def created(self) -> list[Object]:
        """The objects created so far, in creation order."""
        return list(self.roles.values())

    def discard(self) -> None:
        """Remove everything created so far (after a failed generation)."""
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


class VertexGroupWriter:
    """Vertex groups in one pass: the groups by name, then every weight through a bmesh deform layer.

    VertexGroup.add costs Blender time in proportion to the number of groups (it looks the group up in a list),
    so adding the weights group by group was quadratic in the bones; the deform layer is written in O(1) per vertex.
    """

    @staticmethod
    def assign(ob: Object, groups: Mapping[str, Sequence[int]]) -> None:
        """One group per name, in order, with each listed vertex in it at weight 1.0 (ob has no groups yet).

        Raises RuntimeError if the bmesh round trip changed the mesh's attributes (it must not lose data).
        """
        for name in groups:
            ob.vertex_groups.new(name=name)
        mesh: Mesh = ob.data  # type: ignore[assignment]  # vertex groups are written on mesh objects
        before = VertexGroupWriter.attributes(mesh)
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            layer = bm.verts.layers.deform.verify()
            bm.verts.ensure_lookup_table()
            for group, indices in enumerate(groups.values()):
                for index in indices:
                    bm.verts[index][layer][group] = 1.0
            bm.to_mesh(mesh)
        finally:
            bm.free()
        after = VertexGroupWriter.attributes(mesh)
        if after != before:
            raise RuntimeError(f"Writing the vertex groups changed the mesh's attributes: {before} -> {after}")

    @staticmethod
    def attributes(mesh: Mesh) -> list[tuple[str, str, str]]:
        """(name, domain, type) of every attribute that holds data, sorted.

        Left out: Blender's internal storage (names starting with "."; bmesh adds topology and UV selection
        layers), and attributes on a domain with no elements (bmesh drops sharp_face from a mesh without faces).
        """
        sizes = {
            "POINT": len(mesh.vertices),
            "EDGE": len(mesh.edges),
            "FACE": len(mesh.polygons),
            "CORNER": len(mesh.loops),
        }
        return sorted(
            (a.name, a.domain, a.data_type) for a in mesh.attributes if not a.name.startswith(".") and sizes[a.domain]
        )
