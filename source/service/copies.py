# SPDX-License-Identifier: GPL-3.0-or-later

"""Copies of trees: Duplicate Sapling Tree, and completing the copies Blender's Duplicate makes."""

from collections.abc import Iterable

from bpy.types import Context, Object

from ..build.tree_copy import TreeCopy
from ..build.tree_record import TreeRecord


class TreeCopies:
    """Whole, independent copies of trees."""

    @staticmethod
    def duplicate(context: Context) -> Object:
        """Copy the tree of the active object with all its parts; the copy ends selected and active, alone."""
        view_layer = context.view_layer
        if view_layer is None:  # checked before the copy is made, so a failure leaves nothing behind
            raise RuntimeError("The context has no view layer")
        root = TreeRecord.root_of(context.active_object)  # type: ignore[arg-type]  # the caller's poll: a tree
        copy = TreeCopy(root).copy()
        for ob in view_layer.objects:
            ob.select_set(False)
        copy.select_set(True)
        view_layer.objects.active = copy
        return copy

    @staticmethod
    def complete(updated: Iterable[Object]) -> None:
        """Give each copy of a tree among the updated objects the parts it lacks (after Blender's Duplicate)."""
        for found in TreeCopy.copied_roots(list(updated)):
            TreeCopy(found.original).complete(found.copy)
