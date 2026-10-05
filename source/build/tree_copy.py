# SPDX-License-Identifier: GPL-3.0-or-later

"""Duplicating a whole tree: every object it owns, the hidden parts too, as an independent tree."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

import bpy
from bpy.types import ID, Object

from .tree_record import TreeRecord
from .tree_root import CurveSource


@dataclass(frozen=True, slots=True)
class CopiedRoot:
    """A tree object Blender's Duplicate copied without the tree's parts, and the tree it was copied from."""

    original: Object
    copy: Object


class TreeCopy:
    """Copies a tree's objects with their own data, relinks them to each other and gives them a new tree id.

    Blender's Duplicate copies only selected objects, and hidden objects cannot be selected, so it never copies
    the tree's hidden parts (curves, wind joints, joint proxy). Here every object the tree owns is copied: its
    data too (meshes, curves, armature), while materials and wind actions stay shared (removing a tree deletes
    only data no other object uses). Parents, Armature modifiers and node group object inputs that point at a
    part of the tree point at its copy. The user's objects attached to the tree stay with the original, except
    a face-instanced leaf object: face instancing draws the leaves object's children, so it is copied too.
    """

    def __init__(self, original: Object) -> None:
        self.original = original
        self.copies: dict[Object, Object] = {}

    def copy(self) -> Object:
        """The copied tree's root, in the original's collections and place."""
        return self.complete(self._duplicate(self.original, own_data=True))

    def complete(self, target: Object) -> Object:
        """Make `target`, a copy of the original's root, a whole tree: the parts copied with it are kept (their
        tree id and role match), every other part is copied; then all are relinked under a new tree id."""
        existing = {ob[TreeRecord.ROLE]: ob for ob in TreeRecord.owned(target)[1:]}
        owned = TreeRecord.owned(self.original)
        for ob in owned:
            if ob is self.original:
                self.copies[ob] = target
            else:
                role = ob[TreeRecord.ROLE]
                self.copies[ob] = existing[role] if role in existing else self._duplicate(ob, own_data=True)
        for ob in owned:
            if ob.instance_type == "FACES" and not self.copies[ob].children:
                for child in ob.children:
                    self.copies[child] = self._duplicate(child, own_data=False)
        for original, duplicate in self.copies.items():
            if original.parent in self.copies:
                duplicate.parent = self.copies[original.parent]
            self._relink_modifiers(duplicate)
        tree_id = uuid.uuid4().hex
        for ob in owned:
            self.copies[ob][TreeRecord.ID] = tree_id
        return target

    @staticmethod
    def copied_roots(objects: Iterable[Object]) -> list[CopiedRoot]:
        """The tree roots among `objects` that Blender's Duplicate copied without the tree's curves, each with the
        intact tree of the same id it came from."""
        found = []
        for ob in objects:
            if TreeRecord.SETTINGS not in ob or TreeCopy._is_whole(ob):  # type: ignore[operator]  # stub: ID lacks __contains__
                continue
            original = next(
                (
                    other
                    for other in bpy.data.objects
                    if other is not ob
                    and other.get(TreeRecord.ID) == ob.get(TreeRecord.ID)
                    and TreeCopy._is_whole(other)
                ),
                None,
            )
            if original is not None:
                found.append(CopiedRoot(original, ob))
        return found

    @staticmethod
    def _is_whole(root: Object) -> bool:
        """Whether a tree root has its curves (every tree does; a root copied by Duplicate does not)."""
        return any(ob[TreeRecord.ROLE] == CurveSource.ROLE for ob in TreeRecord.owned(root)[1:])

    @staticmethod
    def _duplicate(ob: Object, own_data: bool) -> Object:
        """A copy of ob (modifiers, custom properties, parent inverse) linked into ob's collections."""
        duplicate = ob.copy()
        if own_data and ob.data is not None:
            data: ID = ob.data.copy()
            duplicate.data = data  # type: ignore[assignment]  # stub: Object.data takes the data's own type
        for collection in ob.users_collection:
            collection.objects.link(duplicate)
        return duplicate

    def _relink_modifiers(self, ob: Object) -> None:
        """Point ob's Armature modifiers and node group object inputs at the copies of the tree's parts."""
        for modifier in ob.modifiers:
            if modifier.type == "ARMATURE" and modifier.object in self.copies:  # type: ignore[attr-defined]  # stub: Modifier base class
                modifier.object = self.copies[modifier.object]  # type: ignore[attr-defined]  # stub: as above
            elif modifier.type == "NODES" and modifier.node_group is not None:  # type: ignore[attr-defined]  # stub: as above
                for item in modifier.node_group.interface.items_tree:  # type: ignore[attr-defined]  # stub: as above
                    if item.item_type != "SOCKET" or item.socket_type != "NodeSocketObject":
                        continue
                    # Blender 5.2: modifier inputs are typed sockets, no longer ID properties
                    socket = getattr(modifier.properties.inputs, item.identifier)  # type: ignore[attr-defined]  # stub: as above
                    if isinstance(socket.value, Object) and socket.value in self.copies:
                        socket.value = self.copies[socket.value]
