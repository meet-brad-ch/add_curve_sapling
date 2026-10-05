# SPDX-License-Identifier: GPL-3.0-or-later

"""Duplicate Sapling Tree: an independent copy of the whole tree, then moved as Blender's Duplicate does."""

from typing import TYPE_CHECKING, override

import bpy
from bpy.types import Context, Event, Operator

from ..build.tree_copy import TreeCopy
from ..build.tree_record import TreeRecord

if TYPE_CHECKING:
    from bpy.stub_internal.rna_enums import OperatorReturnItems


class DuplicateTreeOperator(Operator):
    """Duplicate the Sapling tree with all its parts (also the hidden ones) as an independent tree"""

    bl_idname = "sapling.tree_duplicate"
    bl_label = "Duplicate Sapling Tree"
    bl_options = {"REGISTER", "UNDO"}

    @override
    @classmethod
    def poll(cls, context: Context) -> bool:  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        return context.mode == "OBJECT" and TreeRecord.is_tree(context.active_object)

    @override
    def execute(self, context: Context) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        root = TreeRecord.root_of(context.active_object)  # type: ignore[arg-type]  # poll: the active object is a tree
        copy = TreeCopy(root).copy()
        view_layer = context.view_layer
        for ob in view_layer.objects:  # type: ignore[union-attr]  # an operator context has a view layer
            ob.select_set(False)
        copy.select_set(True)
        view_layer.objects.active = copy  # type: ignore[union-attr]  # as above
        return {"FINISHED"}

    @override
    def invoke(self, context: Context, event: Event) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        result = self.execute(context)
        bpy.ops.transform.translate("INVOKE_DEFAULT")  # move the copy with the mouse, as Shift+D does
        return result
