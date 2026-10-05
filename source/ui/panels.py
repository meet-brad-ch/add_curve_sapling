# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the add-on shows up: Add > Curve, Object menu and the Sapling sidebar tab."""

from typing import override

import bpy
from bpy.types import Context, Menu, Object, Panel, UILayout

from ..build.tree_record import TreeRecord
from ..settings import SettingsError
from .duplicate import DuplicateTreeOperator
from .operators import AddTreeOperator


class TreeEditButton:
    """The "Edit Sapling Tree" and "Duplicate Sapling Tree" buttons of a tree."""

    @staticmethod
    def draw(layout: UILayout, root: Object) -> None:
        """Add the buttons to layout: Edit re-opens the Add Tree operator set to replace the tree whose root is
        `root`; Duplicate copies the active object's tree."""
        button = layout.operator(AddTreeOperator.bl_idname, text="Edit Sapling Tree", icon="OUTLINER_OB_CURVE")
        button.replace = root.name
        layout.operator(DuplicateTreeOperator.bl_idname, text="Duplicate Sapling Tree", icon="DUPLICATE")


class TreePanel(Panel):
    """Sidebar tab shown when the active object belongs to a Sapling tree."""

    bl_idname = "VIEW3D_PT_sapling_tree"
    bl_label = "Sapling Tree"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sapling"

    @override
    @classmethod
    def poll(cls, context: Context) -> bool:  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        return context.mode == "OBJECT" and TreeRecord.is_tree(context.active_object)

    @override
    def draw(self, context: Context) -> None:  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        layout = self.layout
        if layout is None:
            raise RuntimeError("Panel.draw without a layout")
        root = TreeRecord.root_of(context.active_object)  # type: ignore[arg-type]  # poll: the active object is a tree
        col = layout.column()
        col.label(text=f"Root: {root.name}")
        try:
            settings = TreeRecord.settings(root).values
        except SettingsError as error:  # a draw method cannot report: the panel shows the problem instead
            col.label(text=str(error), icon="ERROR")
            return
        col.label(text=f"Levels: {settings['levels']}   Seed: {settings['seed']}")
        TreeEditButton.draw(col, root)


class Menus:
    """Menu entries, appended to Blender's menus on register."""

    @staticmethod
    def add_curve(menu: Menu, context: Context) -> None:
        """Add > Curve entry: add a new tree."""
        menu.layout.operator(AddTreeOperator.bl_idname, text="Sapling Tree Gen", icon="CURVE_DATA")  # type: ignore[union-attr]  # stub: layout is optional; a menu's draw always has one

    @staticmethod
    def object_menu(menu: Menu, context: Context) -> None:
        """Object menu entry, only when the active object belongs to a Sapling tree: edit that tree."""
        if TreeRecord.is_tree(context.active_object):
            menu.layout.separator()  # type: ignore[union-attr]  # stub: layout is optional; a menu's draw always has one
            TreeEditButton.draw(menu.layout, TreeRecord.root_of(context.active_object))  # type: ignore[arg-type]  # a menu's draw has a layout; is_tree() above checked the active object

    @classmethod
    def register(cls) -> None:
        """Append the entries to Blender's menus (on add-on register)."""
        # The stubs type menu draw functions as (context); Blender calls them with (menu, context).
        bpy.types.VIEW3D_MT_curve_add.append(cls.add_curve)  # type: ignore[arg-type]  # stub: menu draw functions take (context); Blender calls them with (menu, context)
        bpy.types.VIEW3D_MT_object.append(cls.object_menu)  # type: ignore[arg-type]  # stub: menu draw functions take (context); Blender calls them with (menu, context)

    @classmethod
    def unregister(cls) -> None:
        """Remove the entries from Blender's menus (on add-on unregister)."""
        bpy.types.VIEW3D_MT_curve_add.remove(cls.add_curve)  # type: ignore[arg-type]  # stub: menu draw functions take (context); Blender calls them with (menu, context)
        bpy.types.VIEW3D_MT_object.remove(cls.object_menu)  # type: ignore[arg-type]  # stub: menu draw functions take (context); Blender calls them with (menu, context)
