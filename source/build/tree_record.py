# SPDX-License-Identifier: GPL-3.0-or-later

"""Which objects belong to a generated tree, and the settings it was generated with."""

import uuid

import bpy

from ..settings import TreeSettings


class TreePlacement:
    """Where a replaced tree was, so its replacement goes to the same place."""

    def __init__(self, matrix, parent, parent_inverse, collections, foreign_children):
        self.matrix = matrix
        self.parent = parent
        self.parent_inverse = parent_inverse
        self.collections = collections
        self.foreign_children = foreign_children  # [(object, name of its tree parent, world matrix)]


class TreeRecord:
    """Tags a tree's objects with one id and stores its settings on the root object."""

    ID = "sapling_tree"
    SETTINGS = "sapling_settings"

    @classmethod
    def store(cls, result, settings):
        tree_id = uuid.uuid4().hex
        for ob in result.created:
            ob[cls.ID] = tree_id
        result.root[cls.SETTINGS] = settings.to_json()

    @classmethod
    def root_of(cls, ob):
        """The root object of the tree `ob` belongs to, or None."""
        if ob is None or not ob.get(cls.ID):
            return None
        while ob.parent and ob.parent.get(cls.ID) == ob[cls.ID]:
            ob = ob.parent
        return ob if cls.SETTINGS in ob else None

    @classmethod
    def settings(cls, root):
        return TreeSettings.from_json(root[cls.SETTINGS])

    @classmethod
    def remove(cls, root):
        """Delete the tree (objects and their data); return its placement.

        Objects the user parented to the tree (e.g. the leaf instance object) are kept, unparented
        with their world transform; the placement lists them for re-parenting.
        """
        tree_id = root[cls.ID]
        owned = [ob for ob in bpy.data.objects if ob.get(cls.ID) == tree_id]
        foreign = []
        for ob in owned:
            for child in ob.children:
                if child.get(cls.ID) != tree_id:
                    foreign.append((child, ob.name, child.matrix_world.copy()))
        for child, _parent, matrix in foreign:
            child.parent = None
            child.matrix_world = matrix

        placement = TreePlacement(
            root.matrix_world.copy(),
            root.parent,
            root.matrix_parent_inverse.copy(),
            list(root.users_collection),
            foreign,
        )
        for ob in owned:
            data = ob.data
            action = ob.animation_data.action if ob.animation_data else None
            bpy.data.objects.remove(ob)
            if data is not None and data.users == 0:
                cls._remove_data(data)
            if action is not None and action.users == 0:
                bpy.data.actions.remove(action)
        return placement

    @staticmethod
    def _remove_data(data):
        for collection in (bpy.data.curves, bpy.data.meshes, bpy.data.armatures):
            if data.name in collection and collection[data.name] == data:
                collection.remove(data)
                return

    @staticmethod
    def restore(result, placement, view_layer):
        """Put a new tree where the replaced one was, and re-attach the user's objects."""
        root = result.root
        if placement.parent:
            root.parent = placement.parent
            root.matrix_parent_inverse = placement.parent_inverse
        root.matrix_world = placement.matrix
        view_layer.update()  # the tree's world matrices, for re-parenting below
        by_name = {ob.name: ob for ob in result.created}
        for child, parent_name, matrix in placement.foreign_children:
            parent = by_name.get(parent_name)
            if parent:
                child.parent = parent
                child.matrix_world = matrix
