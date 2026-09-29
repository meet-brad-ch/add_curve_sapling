# SPDX-License-Identifier: GPL-3.0-or-later

"""Creating the tree's objects in the scene, and removing them again."""

import re
from collections.abc import Sequence

import bpy
from bpy.types import ID, Collection, Object


class ObjectFactory:
    """Creates the tree's objects in the target collections and knows each one by its role.

    The role is the object's base name ("tree", "leaves", "treeArm", "treemesh", "envelope"); Blender
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
        if ob.animation_data and ob.animation_data.action:
            blocks.append(ob.animation_data.action)
        return blocks
