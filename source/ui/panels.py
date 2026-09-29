# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the add-on shows up: Add > Curve, Object menu and the Sapling sidebar tab."""

import bpy
from bpy.types import Panel

from ..build.tree_record import TreeRecord
from .operators import AddTreeOperator


class TreeEditButton:
    """The "Edit Sapling Tree" button: re-opens the Add Tree operator on a tree's settings."""

    @staticmethod
    def draw(layout, root):
        button = layout.operator(AddTreeOperator.bl_idname, text="Edit Sapling Tree", icon="OUTLINER_OB_CURVE")
        button.replace = root.name


class TreePanel(Panel):
    """Sidebar tab shown when the active object belongs to a Sapling tree."""

    bl_idname = "VIEW3D_PT_sapling_tree"
    bl_label = "Sapling Tree"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sapling"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and TreeRecord.is_tree(context.active_object)

    def draw(self, context):
        layout = self.layout
        if layout is None:
            raise RuntimeError("Panel.draw without a layout")
        root = TreeRecord.root_of(context.active_object)
        settings = TreeRecord.settings(root).values
        col = layout.column()
        col.label(text=f"Root: {root.name}")
        col.label(text=f"Levels: {settings['levels']}   Seed: {settings['seed']}")
        TreeEditButton.draw(col, root)


class Menus:
    """Menu entries, appended to Blender's menus on register."""

    @staticmethod
    def add_curve(menu, context):
        menu.layout.operator(AddTreeOperator.bl_idname, text="Sapling Tree Gen", icon="CURVE_DATA")

    @staticmethod
    def object_menu(menu, context):
        if TreeRecord.is_tree(context.active_object):
            menu.layout.separator()
            TreeEditButton.draw(menu.layout, TreeRecord.root_of(context.active_object))

    @classmethod
    def register(cls):
        # The stubs type menu draw functions as (context); Blender calls them with (menu, context).
        bpy.types.VIEW3D_MT_curve_add.append(cls.add_curve)  # type: ignore[arg-type]
        bpy.types.VIEW3D_MT_object.append(cls.object_menu)  # type: ignore[arg-type]

    @classmethod
    def unregister(cls):
        bpy.types.VIEW3D_MT_curve_add.remove(cls.add_curve)  # type: ignore[arg-type]
        bpy.types.VIEW3D_MT_object.remove(cls.object_menu)  # type: ignore[arg-type]
