# SPDX-License-Identifier: GPL-3.0-or-later

"""The preset menu's choices and saving the panel's settings as a preset."""

from dataclasses import dataclass
from pathlib import Path

from ..presets import PresetStore
from ..settings import TreeSettings


@dataclass(frozen=True)
class PresetChoiceItem:
    """One entry of the preset menu: its id, the label shown and the tooltip."""

    name: str
    label: str
    description: str


class PresetService:
    """The built-in and user presets as the panel offers them."""

    @staticmethod
    def choices() -> list[PresetChoiceItem]:
        """Built-in presets, then the user's; a user file that cannot be loaded says why in its tooltip."""
        items = []
        for entry in PresetStore.for_addon().entries():
            items.append(PresetService.choice(entry.name, entry.builtin, entry.problem))
        return items

    @staticmethod
    def choice(name: str, builtin: bool, problem: str | None) -> PresetChoiceItem:
        """The menu entry of one preset."""
        if builtin:
            return PresetChoiceItem(name, name.replace("_", " ").title(), "Built-in preset")
        if problem:
            return PresetChoiceItem(name, f"{name} (cannot load)", problem)
        return PresetChoiceItem(name, name, "Your preset")

    @staticmethod
    def save(name: str, settings_json: str, overwrite: bool) -> Path:
        """Save the settings (the panel's JSON) as the user preset `name`; raises SettingsError on a bad name,
        bad settings, or an existing preset without overwrite."""
        settings = TreeSettings.from_json(settings_json)
        return PresetStore.for_addon().save(name, settings, overwrite)
