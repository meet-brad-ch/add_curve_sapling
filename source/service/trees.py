# SPDX-License-Identifier: GPL-3.0-or-later

"""Adding and editing a tree: every decision between the panel's settings and the generator, without the UI.

The operator in ui/operators.py only moves values: it asks `loaded` for the settings to show, sets them on its
properties (Blender converts and clamps them there), reads them back and passes them to `make`. Tests call the
service directly.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from bpy.types import Collection, Context, Object

from ..build.tree_record import TreeEdit
from ..generator import TreeGenerator
from ..presets import PresetStore
from ..settings import SettingsError, TreeSettings


@dataclass(frozen=True)
class SettingsRequest:
    """Which settings the panel shall show before a tree is made."""

    current: TreeSettings  # the panel's settings now (the generation settings and the leaf object)
    defaults: Mapping[str, Any]  # the default of every generation setting
    preset: str = ""  # a preset to load ("": none)
    replace: str = ""  # the tree being edited ("": a new tree)
    load_stored: bool = False  # an edit starts from the settings stored on the tree


@dataclass(frozen=True)
class LoadedSettings:
    """The settings for the panel to show, the names to set, and what the user should know about them."""

    settings: TreeSettings
    names: list[str]
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class MakeRequest:
    """A tree to make: its settings, and where it goes."""

    settings: TreeSettings  # the generation settings and the leaf object, as the panel holds them
    replace: str = ""  # the tree to replace ("": add a new tree)


@dataclass(frozen=True)
class TreeOutcome:
    """The tree made, and what the user should know about it."""

    root: Object
    warnings: list[str]


class TreeService:
    """Adds and edits trees in a Blender context: preset and stored settings, the generator, placement."""

    def __init__(self, context: Context, generation_names: list[str], stored_names: list[str]) -> None:
        """A service for this context; the names are the generation settings and those a tree stores."""
        self.context = context
        self.generation_names = generation_names
        self.stored_names = stored_names

    def loaded(self, request: SettingsRequest) -> list[LoadedSettings]:
        """The settings for the panel to set, in order: the chosen preset, then the edited tree's stored settings
        (they win when both apply). Empty: the panel keeps its settings."""
        loads = []
        if request.preset:
            loads.append(self.preset_settings(request))
        if request.replace and request.load_stored:
            loads.append(self.stored_settings(request))
        return loads

    def preset_settings(self, request: SettingsRequest) -> LoadedSettings:
        """The chosen preset completed with the defaults; a warning names the settings it lacks."""
        settings = PresetStore.for_addon().load(request.preset)
        missing = settings.missing(request.defaults)
        settings.complete(request.defaults)
        warnings = []
        if missing:
            warnings.append(
                f"Preset '{request.preset}' does not have {len(missing)} settings: {', '.join(missing)}. "
                "The defaults were used. Save the preset again to store them."
            )
        return LoadedSettings(settings, self.generation_names, warnings)

    def stored_settings(self, request: SettingsRequest) -> LoadedSettings:
        """The settings stored on the edited tree; a warning names those an older tree lacks."""
        edit = TreeEdit(request.replace, self.view_layer())
        stored = edit.stored(request.defaults)
        warnings = []
        if stored.missing:
            warnings.append(
                f"Tree '{edit.root.name}' was made by an older version and does not have {len(stored.missing)} "
                f"settings: {', '.join(stored.missing)}. The defaults were used. The edited tree stores them."
            )
        return LoadedSettings(stored.settings, self.stored_names, warnings)

    def make(self, request: MakeRequest) -> TreeOutcome:
        """Make the tree: a new one at the 3D cursor, or one that replaces the edited tree. The new tree is
        complete before the old one is touched, so a failure leaves the old tree as it was. The new tree ends
        selected and active, alone."""
        edit = None
        if request.replace:
            edit = TreeEdit(request.replace, self.view_layer())
        if edit is not None:
            collections = edit.collections
        else:
            collections = [self.active_collection()]
        properties = SimpleNamespace(**request.settings.values)
        generator = TreeGenerator(properties, self.context, collections)
        result = generator.generate(request.settings)
        warnings = list(generator.warnings)
        if edit is None:
            result.root.location = self.context.scene.cursor.location  # type: ignore[union-attr]  # a context with a scene
        else:
            warnings += self.replaced(edit, result)
        self.select_only(result.root)
        return TreeOutcome(result.root, warnings)

    def replaced(self, edit: TreeEdit, result: Any) -> list[str]:
        """Put the new tree in the edited tree's place; a warning names the user's objects left unparented."""
        unattached = edit.replace(result, self.view_layer())
        if not unattached:
            return []
        return [f"Left unparented (their part of the tree is gone): {', '.join(unattached)}"]

    def select_only(self, root: Object) -> None:
        """Make the tree the only selected object, and the active one."""
        for ob in self.context.selected_objects:  # type: ignore[union-attr]  # a context with selected objects
            ob.select_set(False)
        root.select_set(True)
        self.view_layer().objects.active = root

    def active_collection(self) -> Collection:
        """The collection a new tree goes into; a SettingsError when the context has none."""
        if self.context.collection is None:
            raise SettingsError("No active collection to add the tree to")
        return self.context.collection

    def view_layer(self) -> Any:
        """The context's view layer (an operator's context always has one)."""
        return self.context.view_layer
