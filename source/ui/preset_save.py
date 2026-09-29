# SPDX-License-Identifier: GPL-3.0-or-later

"""Saving the panel's settings as a user preset."""

from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator

from ..presets import PresetStore
from ..settings import SettingsError, TreeSettings


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
        except SettingsError as error:
            self.report({"ERROR"}, str(error))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Saved preset {path.stem}")
        return {"FINISHED"}
