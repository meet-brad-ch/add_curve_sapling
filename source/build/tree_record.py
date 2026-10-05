# SPDX-License-Identifier: GPL-3.0-or-later

"""Which objects make up a generated tree, its settings, where it sits in the scene, and editing it in place."""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import bpy
from bpy.types import Collection, Object, ViewLayer
from mathutils import Matrix

from ..settings import SettingsError, TreeSettings
from .objects import ObjectFactory, ParentLink, TreeParts


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
    def tag(cls, result: TreeParts, settings: TreeSettings) -> None:
        """Mark a new tree's objects with a fresh id and their roles, and store the settings on its root."""
        tree_id = uuid.uuid4().hex
        for role, ob in result.roles.items():
            ob[cls.ID] = tree_id
            ob[cls.ROLE] = role
        result.root[cls.SETTINGS] = settings.to_json()

    @classmethod
    def is_tree(cls, ob: Object | None) -> bool:
        """Whether ob belongs to an intact Sapling tree (for menus and panels)."""
        return ob is not None and cls.ID in ob and cls.SETTINGS in cls._top(ob)  # type: ignore[operator]  # stub: ID lacks __contains__

    @classmethod
    def root_of(cls, ob: Object) -> Object:
        """The root object of the tree ob belongs to; raises TreeRecordError otherwise."""
        if cls.ID not in ob:  # type: ignore[operator]  # stub: ID lacks __contains__
            raise TreeRecordError(f"'{ob.name}' is not part of a Sapling tree")
        top = cls._top(ob)
        if cls.SETTINGS not in top:  # type: ignore[operator]  # stub: ID lacks __contains__
            raise TreeRecordError(f"'{ob.name}' belongs to a Sapling tree whose root '{top.name}' lost its settings")
        return top

    @classmethod
    def owned(cls, root: Object) -> list[Object]:
        """The root and its descendants that carry the root's tree id (not the user's objects parented to it)."""
        return [root, *(ob for ob in root.children_recursive if ob.get(cls.ID) == root[cls.ID])]

    @classmethod
    def claim(cls, root: Object) -> None:
        """Give this tree a new id when another object carries the same one (a duplicated tree)."""
        owned = cls.owned(root)
        holders = [ob for ob in bpy.data.objects if ob.get(cls.ID) == root[cls.ID]]
        if len(holders) != len(owned):
            tree_id = uuid.uuid4().hex
            for ob in owned:
                ob[cls.ID] = tree_id

    @classmethod
    def settings(cls, root: Object) -> TreeSettings:
        """The settings stored on the root when the tree was generated; raises SettingsError when unreadable."""
        return TreeSettings.from_json(root[cls.SETTINGS])

    @classmethod
    def remove(cls, root: Object) -> None:
        """Delete the tree's own objects with their data; the user's attached objects stay."""
        ObjectFactory.remove(cls.owned(root))

    @classmethod
    def _top(cls, ob: Object) -> Object:
        """The farthest ancestor carrying ob's tree id (the root, if the tree is intact)."""
        while ob.parent is not None and ob.parent.get(cls.ID) == ob[cls.ID]:
            ob = ob.parent
        return ob


@dataclass(frozen=True, slots=True)
class AttachedObject:
    """A user's object parented to part of a tree (e.g. the leaf instance object)."""

    ob: Object
    role: str
    link: ParentLink
    matrix: Matrix


class TreePlacement:
    """Where a tree sits (transform, parent, collections) and the user's objects attached to it."""

    def __init__(self, root: Object, owned: list[Object]) -> None:
        self.root = root
        # The root's own transform: with the same parent link and parent inverse it puts the new root
        # exactly where the old one was (setting matrix_world misplaces vertex-parented roots)
        self.basis = root.matrix_basis.copy()
        self.link = ParentLink.of(root)
        self.parent_inverse = root.matrix_parent_inverse.copy()
        self.collections: list[Collection] = list(root.users_collection)
        if not self.collections:
            raise TreeRecordError(f"'{root.name}' is in no collection")
        tree_id = root[TreeRecord.ID]
        self.attached = [
            AttachedObject(child, ob[TreeRecord.ROLE], ParentLink.of(child), child.matrix_world.copy())
            for ob in owned
            for child in ob.children
            if child.get(TreeRecord.ID) != tree_id
        ]

    def detach(self) -> None:
        """Unparent the user's objects, keeping them where they are, before the old tree goes."""
        for item in self.attached:
            item.ob.parent = None
            item.ob.matrix_world = item.matrix

    def apply(self, result: TreeParts, view_layer: ViewLayer) -> list[str]:
        """Put the new tree where the old one was; re-attach the user's objects by role.

        Returns the names of objects whose part of the tree no longer exists (they stay unparented).
        Updates the view layer.
        """
        root = result.root
        self.link.attach(root)
        root.matrix_parent_inverse = self.parent_inverse
        root.matrix_basis = self.basis
        view_layer.update()  # the new tree's world matrices, for re-parenting below
        unattached: list[str] = []
        for item in self.attached:
            if item.role not in result.roles:
                unattached.append(item.ob.name)
                continue
            item.link.attach(item.ob, result.roles[item.role])
            item.ob.matrix_world = item.matrix
        return unattached


@dataclass(frozen=True, slots=True)
class StoredSettings:
    """The settings a tree was made with, completed with the defaults of the settings it does not have."""

    settings: TreeSettings
    missing: list[str]


class TreeEdit:
    """Editing a tree in place: its stored settings, and putting the new tree where the old one was."""

    def __init__(self, name: str, view_layer: ViewLayer) -> None:
        ob = bpy.data.objects.get(name)
        if ob is None:
            raise TreeRecordError(f"No object named '{name}'")
        self.root: Object = TreeRecord.root_of(ob)
        TreeRecord.claim(self.root)
        view_layer.update()  # current world matrices of the tree and the user's objects
        self.placement: TreePlacement = TreePlacement(self.root, TreeRecord.owned(self.root))

    @property
    def collections(self) -> list[Collection]:
        """The collections the tree is in (the new tree goes into the same ones)."""
        return self.placement.collections

    def stored(self, defaults: Mapping[str, Any]) -> StoredSettings:
        """The settings stored on the tree under their current ids, completed from `defaults` (a tree made before a
        setting existed gets that setting's default, as an older preset does)."""
        settings = TreeRecord.settings(self.root).rename_keys()
        missing = settings.missing(defaults)
        return StoredSettings(settings.complete(defaults), missing)

    def replace(self, result: TreeParts, view_layer: ViewLayer) -> list[str]:
        """The old tree goes and the new one takes its place and names; returns the names of the user's objects
        whose part of the tree no longer exists."""
        self.placement.detach()
        TreeRecord.remove(self.root)
        result.objects.take_base_names()
        return self.placement.apply(result, view_layer)
