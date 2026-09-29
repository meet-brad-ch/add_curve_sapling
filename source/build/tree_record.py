# SPDX-License-Identifier: GPL-3.0-or-later

"""Which objects make up a generated tree, its settings, and where it sits in the scene."""

import uuid
from dataclasses import dataclass

import bpy
from bpy.types import Object
from mathutils import Matrix

from ..settings import SettingsError, TreeSettings
from .objects import ObjectFactory


class TreeRecordError(SettingsError):
    """A Sapling tree that cannot be edited: not a tree, or its record is broken."""


class TreeRecord:
    """Each object of a tree carries the tree's id and its role; the root also holds the settings.

    A tree's objects are its root and the root's descendants with the same id, so duplicating a tree
    (which copies the custom properties) never makes one tree own the other's objects.
    """

    ID = "sapling_tree"
    ROLE = "sapling_role"
    SETTINGS = "sapling_settings"

    @classmethod
    def tag(cls, result, settings):
        tree_id = uuid.uuid4().hex
        for role, ob in result.roles.items():
            ob[cls.ID] = tree_id
            ob[cls.ROLE] = role
        result.root[cls.SETTINGS] = settings.to_json()

    @classmethod
    def is_tree(cls, ob):
        """Whether ob belongs to an intact Sapling tree (for menus and panels)."""
        return ob is not None and cls.ID in ob and cls.SETTINGS in cls._top(ob)

    @classmethod
    def root_of(cls, ob):
        """The root object of the tree ob belongs to; raises TreeRecordError otherwise."""
        if cls.ID not in ob:
            raise TreeRecordError(f"'{ob.name}' is not part of a Sapling tree")
        top = cls._top(ob)
        if cls.SETTINGS not in top:
            raise TreeRecordError(f"'{ob.name}' belongs to a Sapling tree whose root '{top.name}' lost its settings")
        return top

    @classmethod
    def owned(cls, root):
        return [root, *(ob for ob in root.children_recursive if ob.get(cls.ID) == root[cls.ID])]

    @classmethod
    def claim(cls, root):
        """Give this tree a new id when another object carries the same one (a duplicated tree)."""
        owned = cls.owned(root)
        holders = [ob for ob in bpy.data.objects if ob.get(cls.ID) == root[cls.ID]]
        if len(holders) != len(owned):
            tree_id = uuid.uuid4().hex
            for ob in owned:
                ob[cls.ID] = tree_id

    @classmethod
    def settings(cls, root):
        return TreeSettings.from_json(root[cls.SETTINGS])

    @classmethod
    def remove(cls, root):
        ObjectFactory.remove(cls.owned(root))

    @classmethod
    def _top(cls, ob):
        while ob.parent is not None and ob.parent.get(cls.ID) == ob[cls.ID]:
            ob = ob.parent
        return ob


@dataclass
class ParentLink:
    """How an object hangs from its parent (all parent types, not only OBJECT)."""

    parent: Object | None
    parent_type: str
    parent_bone: str
    parent_vertices: tuple

    @classmethod
    def of(cls, ob):
        return cls(ob.parent, ob.parent_type, ob.parent_bone, tuple(ob.parent_vertices))

    def attach(self, ob, parent=None):
        ob.parent = parent if parent is not None else self.parent
        ob.parent_type = self.parent_type
        if self.parent_type == "BONE":
            ob.parent_bone = self.parent_bone
        if self.parent_type in {"VERTEX", "VERTEX_3"}:
            ob.parent_vertices = self.parent_vertices


@dataclass
class AttachedObject:
    """A user's object parented to part of a tree (e.g. the leaf instance object)."""

    ob: Object
    role: str
    link: ParentLink
    matrix: Matrix


class TreePlacement:
    """Where a tree sits (transform, parent, collections) and the user's objects attached to it."""

    def __init__(self, root, owned):
        self.matrix = root.matrix_world.copy()
        self.link = ParentLink.of(root)
        self.parent_inverse = root.matrix_parent_inverse.copy()
        self.collections = list(root.users_collection)
        if not self.collections:
            raise TreeRecordError(f"'{root.name}' is in no collection")
        tree_id = root[TreeRecord.ID]
        self.attached = [
            AttachedObject(child, ob[TreeRecord.ROLE], ParentLink.of(child), child.matrix_world.copy())
            for ob in owned
            for child in ob.children
            if child.get(TreeRecord.ID) != tree_id
        ]

    def detach(self):
        """Unparent the user's objects, keeping them where they are, before the old tree goes."""
        for item in self.attached:
            item.ob.parent = None
            item.ob.matrix_world = item.matrix

    def apply(self, result, view_layer):
        """Put the new tree where the old one was; re-attach the user's objects by role.

        Returns the names of objects whose part of the tree no longer exists (they stay unparented).
        """
        root = result.root
        self.link.attach(root)
        root.matrix_parent_inverse = self.parent_inverse
        root.matrix_world = self.matrix
        view_layer.update()  # the new tree's world matrices, for re-parenting below
        unattached = []
        for item in self.attached:
            if item.role not in result.roles:
                unattached.append(item.ob.name)
                continue
            item.link.attach(item.ob, result.roles[item.role])
            item.ob.matrix_world = item.matrix
        return unattached
