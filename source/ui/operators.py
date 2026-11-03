# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators: add (or re-generate) a tree, save a preset."""

from typing import TYPE_CHECKING, Any, override

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Context, Event, Operator

from ..service.presets import PresetService
from ..service.trees import MakeRequest, SettingsRequest, TreeService
from ..service.vocabulary import SettingErrors
from ..settings import TreeSettings
from .pages import SettingsPages
from .properties import EnumItem, OldSettingNames, TreeProperties

if TYPE_CHECKING:
    from bpy.stub_internal.rna_enums import OperatorReturnItems


class PresetChoice:
    """Enum items for the preset list; Blender needs the strings kept alive (T83360), so the items live here."""

    _items: list[tuple[str, str, str]] = []  # Blender's enum item tuples, the boundary EnumItem.item feeds

    @staticmethod
    def items(props: Any, context: Context | None) -> list[tuple[str, str, str]]:
        """Built-in presets, then the user's; a user file that cannot be loaded says why in its tooltip."""
        records = [EnumItem(item.name, item.label, item.description) for item in PresetService.choices()]
        PresetChoice._items[:] = EnumItem.items(records)
        return PresetChoice._items


class AddTreeOperator(TreeProperties, OldSettingNames, Operator):
    """Add a parametric tree (or re-generate a Sapling tree with changed settings)"""

    bl_idname = "curve.tree_add"
    bl_label = "Sapling: Add Tree"
    bl_options = {"REGISTER", "UNDO"}

    DEFAULT_PRESET = "callistemon"

    def mark_preset(self, context: Context) -> None:
        """Update callback of `preset`: the next run loads the chosen preset and regenerates the tree."""
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

    @override
    @classmethod
    def poll(cls, context: Context) -> bool:  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        return context.mode == "OBJECT"

    @override
    def draw(self, context: Context) -> None:  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        SettingsPages.draw(self, self.layout)  # type: ignore[arg-type]  # stub: layout is optional; an operator's draw always has one

    @override
    def invoke(self, context: Context, event: Event) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        if not self.replace:
            self.preset = self.DEFAULT_PRESET
        self.do_update = True
        return self.execute(context)

    @override
    def execute(self, context: Context) -> "set[OperatorReturnItems]":  # type: ignore[override]  # stub: context is Context | None; Blender always passes one
        if self.ui_change_only():
            return {"PASS_THROUGH"}
        try:
            self.make(context)
        except SettingErrors.TYPES as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        return {"FINISHED"}

    def ui_change_only(self) -> bool:
        """In the redo panel, a page change or other UI state keeps the tree as it is."""
        return self.options.is_repeat and not self.do_update

    def make(self, context: Context) -> None:
        """Set the settings the service loads (Blender converts them on the properties), then make the tree."""
        TreeSettings.forward_old_names(self, self.properties)
        service = TreeService(context, TreeProperties.generation_names(), TreeProperties.stored_names())
        for loaded in service.loaded(self.settings_request()):
            loaded.settings.apply_to(self, loaded.names)
            self.report_warnings(loaded.warnings)
        self.preset_pending = False
        self.load_stored = False
        settings = TreeSettings.from_properties(self, TreeProperties.stored_names())
        outcome = service.make(MakeRequest(settings, self.replace))
        self.report_warnings(outcome.warnings)

    def settings_request(self) -> SettingsRequest:
        """What the service needs to choose the settings: the panel's, the defaults, a pending preset, an edit."""
        current = TreeSettings.from_properties(self, TreeProperties.stored_names())
        preset = self.preset if self.preset_pending else ""
        return SettingsRequest(current, self.defaults(), preset, self.replace, self.load_stored)

    def report_warnings(self, warnings: list[str]) -> None:
        """Show each warning in Blender's report area."""
        for warning in warnings:
            self.report({"WARNING"}, warning)

    def defaults(self) -> dict[str, Any]:
        """The default of every generation property (what a preset does not set)."""
        names = TreeProperties.generation_names()
        return TreeSettings.defaults_from_rna(self.properties.bl_rna.properties, names).values
