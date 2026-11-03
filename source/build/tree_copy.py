# SPDX-License-Identifier: GPL-3.0-or-later

"""Duplicating a whole tree: every object it owns, the hidden parts too, as an independent tree."""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

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
        owned = TreeRecord.owned(self.original)
        self._copy_parts(target, owned)
        self._copy_face_instances(owned)
        self._relink_all()
        self._retag(owned)
        return target

    def _copy_parts(self, target: Object, owned: list[Object]) -> None:
        """Map every part of the original to its copy: the target for the root, the part Duplicate copied with it
        (same role), or a new copy."""
        existing = {ob[TreeRecord.ROLE]: ob for ob in TreeRecord.owned(target)[1:]}
        for ob in owned:
            self.copies[ob] = self._copy_of_part(ob, target, existing)

    def _copy_of_part(self, ob: Object, target: Object, existing: dict[str, Object]) -> Object:
        """The copy of one part of the original."""
        if ob is self.original:
            return target
        role = ob[TreeRecord.ROLE]
        if role in existing:
            return existing[role]
        return self._duplicate(ob, own_data=True)

    def _copy_face_instances(self, owned: list[Object]) -> None:
        """A face-instancing part's children (the user's leaf object) are copied when its copy has none."""
        for ob in owned:
            if ob.instance_type == "FACES" and not self.copies[ob].children:
                for child in ob.children:
                    self.copies[child] = self._duplicate(child, own_data=False)

    def _relink_all(self) -> None:
        """Parent every copy to the copy of its original's parent and point its modifiers at the copies."""
        for original, duplicate in self.copies.items():
            if original.parent in self.copies:
                duplicate.parent = self.copies[original.parent]
            self._relink_modifiers(duplicate)

    def _retag(self, owned: list[Object]) -> None:
        """Give the copies of the tree's own parts a new tree id, so the copy is a tree of its own."""
        tree_id = uuid.uuid4().hex
        for ob in owned:
            self.copies[ob][TreeRecord.ID] = tree_id

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
            if modifier.type == "ARMATURE":
                self._relink_armature(modifier)
            elif modifier.type == "NODES" and modifier.node_group is not None:  # type: ignore[attr-defined]  # stub: Modifier base class
                self._relink_node_inputs(modifier)

    def _relink_armature(self, modifier: Any) -> None:
        """An Armature modifier that deforms by a part of the tree deforms by that part's copy."""
        if modifier.object in self.copies:
            modifier.object = self.copies[modifier.object]

    def _relink_node_inputs(self, modifier: Any) -> None:
        """A node modifier's object inputs that name a part of the tree name that part's copy."""
        for item in modifier.node_group.interface.items_tree:
            if item.item_type != "SOCKET" or item.socket_type != "NodeSocketObject":
                continue
            # Blender 5.2: modifier inputs are typed sockets, no longer ID properties
            socket = getattr(modifier.properties.inputs, item.identifier)
            if isinstance(socket.value, Object) and socket.value in self.copies:
                socket.value = self.copies[socket.value]
