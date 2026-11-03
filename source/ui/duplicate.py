# SPDX-License-Identifier: GPL-3.0-or-later

"""Duplicating a tree: the Duplicate Sapling Tree operator, and Blender's own Duplicate made whole."""

from typing import TYPE_CHECKING, override

import bpy
from bpy.app.handlers import persistent
from bpy.types import Context, Depsgraph, Event, Object, Operator, Scene

from ..service.copies import TreeCopies
from ..service.query import TreeQuery

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
        return context.mode == "OBJECT" and TreeQuery.is_tree(context.active_object)

    @override
    def execute(self, context: Context) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        TreeCopies.duplicate(context)
        return {"FINISHED"}

    @override
    def invoke(self, context: Context, event: Event) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        result = self.execute(context)
        # move the copy with the mouse, as Shift+D does; a Move that does not start (no 3D view) or is cancelled
        # leaves the copy where the tree stands, as Blender's own Duplicate does, so its result is not an error
        bpy.ops.transform.translate("INVOKE_DEFAULT")
        return result


class CopiedTreeWatcher:
    """Makes a tree object copied by Blender's Duplicate (Shift+D, Alt+D) a whole tree.

    Duplicate copies only the selected objects, so a copy of the tree object lacks the hidden parts, and the
    leaves and blossoms unless they were selected too. After the depsgraph update that shows the copy, the
    parts it lacks are copied from the tree it came from (TreeCopy.complete). The completed copy is whole, so
    the next update finds nothing to do.
    """

    @staticmethod
    @persistent
    def on_update(scene: Scene, depsgraph: Depsgraph) -> None:
        """depsgraph_update_post handler (persistent: it stays across file loads)."""
        updated = [update.id.original for update in depsgraph.updates if isinstance(update.id, Object)]
        TreeCopies.complete(updated)  # type: ignore[arg-type]  # .original of an Object is an Object

    @classmethod
    def register(cls) -> None:
        """Watch the depsgraph updates (on add-on register)."""
        bpy.app.handlers.depsgraph_update_post.append(cls.on_update)

    @classmethod
    def unregister(cls) -> None:
        """Stop watching (on add-on unregister)."""
        bpy.app.handlers.depsgraph_update_post.remove(cls.on_update)
