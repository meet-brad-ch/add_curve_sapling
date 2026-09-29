# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators: add (or re-generate) a tree, save a preset."""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from ..build.tree_record import TreePlacement, TreeRecord
from ..generator import TreeGenerator
from ..presets import PresetStore
from ..settings import SettingsError, TreeSettings
from .pages import SettingsPages
from .properties import TreeProperties


class PresetChoice:
    """Enum items for the preset list; Blender needs the strings kept alive (T83360)."""

    _items: list[tuple[str, str, str]] = []

    @staticmethod
    def items(props, context):
        cls = PresetChoice
        cls._items.clear()
        for entry in PresetStore.for_addon().entries():
            if entry.builtin:
                cls._items.append((entry.name, entry.name.replace("_", " ").title(), "Built-in preset"))
            elif entry.problem:
                cls._items.append((entry.name, f"{entry.name} (cannot load)", entry.problem))
            else:
                cls._items.append((entry.name, entry.name, "Your preset"))
        return cls._items


class AddTreeOperator(TreeProperties, Operator):
    """Add a parametric tree (or re-generate a Sapling tree with changed settings)"""

    bl_idname = "curve.tree_add"
    bl_label = "Sapling: Add Tree"
    bl_options = {"REGISTER", "UNDO"}

    DEFAULT_PRESET = "callistemon"

    def mark_preset(self, context):
        # Update callbacks cannot report errors (they only reach the console), so execute() loads it.
        self.preset_pending = True
        self.do_update = True

    preset: EnumProperty(
        name="Preset", description="Load the settings of a preset", items=PresetChoice.items, update=mark_preset
    )
    preset_pending: BoolProperty(name="Preset Pending", default=False, options={"HIDDEN", "SKIP_SAVE"})
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
        # In the redo panel, changing a page or other UI state keeps the tree as it is
        if self.options.is_repeat and not self.do_update:
            return {"PASS_THROUGH"}
        try:
            return self._generate(context)
        except SettingsError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

    def defaults(self):
        """The default of every generation property (what a preset does not set)."""
        names = TreeProperties.generation_names()
        return TreeSettings.defaults_from_rna(self.properties.bl_rna.properties, names).values

    def _load_preset(self):
        self.preset_pending = False
        settings = PresetStore.for_addon().load(self.preset).complete(self.defaults())
        settings.apply_to(self, TreeProperties.generation_names())
        if self.limitImport:
            self.levels = min(self.levels, 2)
            self.showLeaves = False

    def _generate(self, context):
        if self.preset_pending:
            self._load_preset()
        old_root = self._tree_to_replace(context) if self.replace else None
        placement = None
        collections = [context.collection]
        if old_root is not None:
            placement = TreePlacement(old_root, TreeRecord.owned(old_root))
            collections = placement.collections

        # The new tree is complete before the old one is touched: a failure leaves the old tree as it was
        settings = TreeSettings.from_properties(self, TreeProperties.stored_names())
        result = TreeGenerator(self, context, collections).generate()
        TreeRecord.tag(result, settings)

        if placement is None:
            result.root.location = context.scene.cursor.location
        else:
            placement.detach()
            TreeRecord.remove(old_root)
            result.objects.take_base_names()
            unattached = placement.apply(result, context.view_layer)
            if unattached:
                self.report({"WARNING"}, f"Left unparented (their part of the tree is gone): {', '.join(unattached)}")
        for ob in context.selected_objects:
            ob.select_set(False)
        result.root.select_set(True)
        context.view_layer.objects.active = result.root
        return {"FINISHED"}

    def _tree_to_replace(self, context):
        """The root of the tree named by `replace`, with its stored settings applied (first run only)."""
        ob = bpy.data.objects.get(self.replace)
        if ob is None:
            raise SettingsError(f"No object named '{self.replace}'")
        root = TreeRecord.root_of(ob)
        TreeRecord.claim(root)
        if self.load_stored:
            TreeRecord.settings(root).apply_to(self, TreeProperties.stored_names())
            self.load_stored = False
        context.view_layer.update()  # current world matrices of the tree and the user's objects
        return root
