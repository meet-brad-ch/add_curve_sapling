# SPDX-License-Identifier: GPL-3.0-or-later

"""Duplicating a whole tree: every object it owns, the hidden parts too, as an independent tree."""

import uuid

from bpy.types import ID, Object

from .tree_record import TreeRecord


class TreeCopy:
    """Copies a tree's objects with their own data, relinks them to each other and gives them a new tree id.

    Blender's Duplicate copies only selected objects, and hidden objects cannot be selected, so it never copies
    the tree's hidden parts (curves, wind joints, joint proxy). Here every object the tree owns is copied: its
    data too (meshes, curves, armature), while materials and wind actions stay shared (removing a tree deletes
    only data no other object uses). Parents, Armature modifiers and node group object inputs that point at a
    part of the tree point at its copy. The user's objects attached to the tree stay with the original, except
    a face-instanced leaf object: face instancing draws the leaves object's children, so it is copied too.
    """

    def __init__(self, root: Object) -> None:
        self.root = root
        self.copies: dict[Object, Object] = {}

    def copy(self) -> Object:
        """The copied tree's root, in the original's collections and place."""
        owned = TreeRecord.owned(self.root)
        for ob in owned:
            self.copies[ob] = self._duplicate(ob, own_data=True)
        for ob in owned:
            if ob.instance_type == "FACES":
                for child in ob.children:
                    if child not in self.copies:
                        self.copies[child] = self._duplicate(child, own_data=False)
        for original, duplicate in self.copies.items():
            if original.parent in self.copies:
                duplicate.parent = self.copies[original.parent]
            self._relink_modifiers(duplicate)
        tree_id = uuid.uuid4().hex
        for ob in owned:
            self.copies[ob][TreeRecord.ID] = tree_id
        return self.copies[self.root]

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
