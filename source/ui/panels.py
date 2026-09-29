# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the add-on shows up: Add > Curve, Object menu and the Sapling sidebar tab."""

import bpy
from bpy.types import Panel

from ..build.tree_record import TreeRecord


class TreeEditButton:
    """The "Edit Sapling Tree" button: re-opens the Add Tree operator on a tree's settings."""

    @staticmethod
    def draw(layout, context, text="Edit Sapling Tree"):
        root = TreeRecord.root_of(context.active_object)
        if root:
            layout.operator("curve.tree_add", text=text, icon="OUTLINER_OB_CURVE").replace = root.name


class TreePanel(Panel):
    """Sidebar tab shown when the active object belongs to a Sapling tree."""

    bl_idname = "VIEW3D_PT_sapling_tree"
    bl_label = "Sapling Tree"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Sapling"

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT" and TreeRecord.root_of(context.active_object) is not None

    def draw(self, context):
        root = TreeRecord.root_of(context.active_object)
        settings = TreeRecord.settings(root).values
        col = self.layout.column()
        col.label(text=f"Root: {root.name}")
        col.label(text=f"Levels: {settings.get('levels')}   Seed: {settings.get('seed')}")
        TreeEditButton.draw(col, context)


class Menus:
    """Menu entries, appended to Blender's menus on register."""

    @staticmethod
    def add_curve(menu, context):
        menu.layout.operator("curve.tree_add", text="Sapling Tree Gen", icon="CURVE_DATA")

    @staticmethod
    def object_menu(menu, context):
        if TreeRecord.root_of(context.active_object):
            menu.layout.separator()
            TreeEditButton.draw(menu.layout, context)

    @classmethod
    def register(cls):
        bpy.types.VIEW3D_MT_curve_add.append(cls.add_curve)
        bpy.types.VIEW3D_MT_object.append(cls.object_menu)

    @classmethod
    def unregister(cls):
        bpy.types.VIEW3D_MT_curve_add.remove(cls.add_curve)
        bpy.types.VIEW3D_MT_object.remove(cls.object_menu)
