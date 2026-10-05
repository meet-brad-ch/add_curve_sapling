# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators: add (or re-generate) a tree, save a preset."""

from typing import TYPE_CHECKING, Any, override

from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Collection, Context, Event, Operator

from ..build.tree_record import TreeEdit
from ..generator import TreeGenerator
from ..presets import PresetStore
from ..settings import SettingsError, TreeSettings
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
        records = []
        for entry in PresetStore.for_addon().entries():
            if entry.builtin:
                records.append(EnumItem(entry.name, entry.name.replace("_", " ").title(), "Built-in preset"))
            elif entry.problem:
                records.append(EnumItem(entry.name, f"{entry.name} (cannot load)", entry.problem))
            else:
                records.append(EnumItem(entry.name, entry.name, "Your preset"))
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
        # In the redo panel, changing a page or other UI state keeps the tree as it is
        if self.options.is_repeat and not self.do_update:
            return {"PASS_THROUGH"}
        try:
            return self._generate(context)
        except SettingsError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}

    def defaults(self) -> dict[str, Any]:
        """The default of every generation property (what a preset does not set)."""
        names = TreeProperties.generation_names()
        return TreeSettings.defaults_from_rna(self.properties.bl_rna.properties, names).values

    def _load_preset(self) -> None:
        """Apply the chosen preset, with the defaults for settings it does not have (reported as a warning)."""
        self.preset_pending = False
        defaults = self.defaults()
        settings = PresetStore.for_addon().load(self.preset)
        missing = settings.missing(defaults)
        settings.complete(defaults)
        if self.limitImport:
            settings.limit_import()
        settings.apply_to(self, TreeProperties.generation_names())
        if missing:
            self.report(
                {"WARNING"},
                f"Preset '{self.preset}' does not have {len(missing)} settings: {', '.join(missing)}. "
                "The defaults were used. Save the preset again to store them.",
            )

    def _load_stored(self, edit: TreeEdit) -> None:
        """Apply the settings stored on the tree being edited (first run only; a warning names the settings the
        tree does not have)."""
        stored = edit.stored(self.defaults())
        stored.settings.apply_to(self, TreeProperties.stored_names())
        self.load_stored = False
        if stored.missing:
            self.report(
                {"WARNING"},
                f"Tree '{edit.root.name}' was made by an older version and does not have {len(stored.missing)} "
                f"settings: {', '.join(stored.missing)}. The defaults were used. The edited tree stores them.",
            )

    def _generate(self, context: Context) -> "set[OperatorReturnItems]":
        self.forward_old_names()
        if self.preset_pending:
            self._load_preset()
        view_layer = context.view_layer
        edit = TreeEdit(self.replace, view_layer) if self.replace else None  # type: ignore[arg-type]  # an operator context has a view layer
        if edit is not None and self.load_stored:
            self._load_stored(edit)
        collections = edit.collections if edit is not None else [self._active_collection(context)]

        # The new tree is complete before the old one is touched: a failure leaves the old tree as it was
        settings = TreeSettings.from_properties(self, TreeProperties.stored_names())
        generator = TreeGenerator(self, context, collections)
        result = generator.generate(settings)
        for warning in generator.warnings:
            self.report({"WARNING"}, warning)

        if edit is None:
            result.root.location = context.scene.cursor.location  # type: ignore[union-attr]  # an operator context has a scene
        else:
            unattached = edit.replace(result, view_layer)  # type: ignore[arg-type]  # an operator context has a view layer
            if unattached:
                self.report({"WARNING"}, f"Left unparented (their part of the tree is gone): {', '.join(unattached)}")
        for ob in context.selected_objects:  # type: ignore[union-attr]  # an operator context has selected objects
            ob.select_set(False)
        result.root.select_set(True)
        view_layer.objects.active = result.root  # type: ignore[union-attr]  # an operator context has a view layer
        return {"FINISHED"}

    @staticmethod
    def _active_collection(context: Context) -> Collection:
        """The collection a new tree goes into; a SettingsError when the context has none."""
        if context.collection is None:
            raise SettingsError("No active collection to add the tree to")
        return context.collection
