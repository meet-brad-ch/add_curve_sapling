# SPDX-License-Identifier: GPL-3.0-or-later

"""The installed add-on: its modules, its settings and its presets."""

import sys
from typing import Any

import bpy
from blender_env import MODULE


class Addon:
    """The installed add-on: its modules, its settings and its presets."""

    MODULE = MODULE

    @staticmethod
    def module(name: str) -> Any:
        """A module of the installed add-on, e.g. module("build.tree_record")."""
        return sys.modules[f"{MODULE}.{name}"]

    @classmethod
    def stored_settings(cls, root: Any) -> dict:
        """The settings stored on a generated tree's root."""
        return cls.module("build.tree_record").TreeRecord.settings(root).values

    @classmethod
    def generation_names(cls) -> list[str]:
        """The add-on's own list of properties that shape a tree."""
        return cls.module("ui.properties").TreeProperties.generation_names()

    @staticmethod
    def operator_property_names() -> list[str]:
        """Every property of the Add Tree operator."""
        rna = bpy.ops.curve.tree_add.get_rna_type()
        return [p.identifier for p in rna.properties if p.identifier != "rna_type"]

    @classmethod
    def operator_defaults(cls) -> dict:
        """The default of every generation property."""
        properties = bpy.ops.curve.tree_add.get_rna_type().properties
        return cls.module("settings").TreeSettings.defaults_from_rna(properties, cls.generation_names()).values

    @classmethod
    def plain(cls, value: Any) -> Any:
        """Convert bpy/mathutils values to JSON-friendly Python values (None stays None)."""
        if value is None:
            return None
        return cls.module("settings").TreeSettings.plain(value)

    @classmethod
    def preset_store(cls) -> Any:
        """The add-on's preset store."""
        return cls.module("presets").PresetStore.for_addon()

    @classmethod
    def resolve_preset(cls, filename: str) -> dict:
        """Full settings of a built-in preset, completed with the defaults as the operator does it."""
        preset = cls.preset_store().load(filename.removesuffix(".py"))
        completed = preset.complete(cls.operator_defaults()).values
        return {key: cls.plain(value) for key, value in completed.items()}
