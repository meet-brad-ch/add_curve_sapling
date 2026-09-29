# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators: add (or re-generate) a tree, save a preset."""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from ..build.tree_record import TreeRecord
from ..generator import TreeGenerator
from ..presets import PresetError, PresetStore
from ..settings import TreeSettings
from .pages import SettingsPages
from .properties import TreeProperties


class PresetChoice:
    """Enum items for the preset list; Blender needs the strings kept alive (T83360)."""

    _items: list[tuple[str, str, str]] = []

    @staticmethod
    def items(props, context):
        cls = PresetChoice
        cls._items.clear()
        for name, builtin in PresetStore.for_addon().names():
            label = name.replace("_", " ").title()
            cls._items.append((name, label, "Built-in preset" if builtin else "Your preset"))
        return cls._items


class AddTreeOperator(TreeProperties, Operator):
    """Add a parametric tree (or re-generate a Sapling tree with changed settings)"""

    bl_idname = "curve.tree_add"
    bl_label = "Sapling: Add Tree"
    bl_options = {"REGISTER", "UNDO"}

    DEFAULT_PRESET = "callistemon"

    def apply_preset(self, context):
        try:
            settings = PresetStore.for_addon().load(self.preset)
        except PresetError as error:
            self.report({"ERROR"}, str(error))
            return
        settings.apply_to(self, TreeProperties.generation_names())
        if self.limitImport:
            self.levels = min(self.levels, 2)
            self.showLeaves = False
        self.do_update = True

    preset: EnumProperty(
        name="Preset", description="Load the settings of a preset", items=PresetChoice.items, update=apply_preset
    )
    replace: StringProperty(
        name="Replace", description="Name of the Sapling tree root to re-generate", options={"HIDDEN", "SKIP_SAVE"}
    )
    load_stored: BoolProperty(
        name="Load Stored Settings",
        description="Start from the settings stored on the tree being replaced (cleared after the first run, so "
        "redo keeps your changes)",
        default=True,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"

    def draw(self, context):
        SettingsPages.draw(self, self.layout)

    def invoke(self, context, event):
        if not self.replace:
            self.preset = self.DEFAULT_PRESET
        self.do_update = True
        return self.execute(context)

    def execute(self, context):
        if not self.do_update:
            return {"PASS_THROUGH"}

        placement = None
        collection = None
        if self.replace:
            root = TreeRecord.root_of(bpy.data.objects.get(self.replace))
            if root is None:
                self.report({"ERROR"}, f"'{self.replace}' is not a Sapling tree")
                return {"CANCELLED"}
            if self.load_stored:
                TreeRecord.settings(root).apply_to(self, TreeProperties.stored_names())
                self.load_stored = False
            context.view_layer.update()  # current world matrices of the tree and the user's objects
            placement = TreeRecord.remove(root)
            collection = placement.collections[0] if placement.collections else None

        result = TreeGenerator(self, context, collection).generate()
        TreeRecord.store(result, TreeSettings.from_properties(self, TreeProperties.stored_names()))

        if placement:
            TreeRecord.restore(result, placement, context.view_layer)
        else:
            result.root.location = context.scene.cursor.location
        for ob in context.selected_objects:
            ob.select_set(False)
        result.root.select_set(True)
        context.view_layer.objects.active = result.root
        return {"FINISHED"}


class SavePresetOperator(Operator):
    """Save the current tree settings as a preset"""

    bl_idname = "sapling.preset_save"
    bl_label = "Save Preset"
    bl_options = {"INTERNAL"}

    name: StringProperty(name="Name")
    overwrite: BoolProperty(name="Overwrite")
    settings: StringProperty(name="Settings", options={"HIDDEN"})

    def execute(self, context):
        try:
            path = PresetStore.for_addon().save(self.name, TreeSettings.from_json(self.settings), self.overwrite)
        except PresetError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved preset {path.stem}")
        return {"FINISHED"}
