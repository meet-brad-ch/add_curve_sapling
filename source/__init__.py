# SPDX-FileCopyrightText: 2011-2026 Sapling Tree Gen authors (see README)
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sapling Tree Gen: parametric trees (Weber-Penn) with leaves, pruning, armature and wind."""

import bpy
from bpy.types import Operator, Panel

from .presets import PresetStore
from .ui.operators import AddTreeOperator
from .ui.panels import Menus, TreePanel
from .ui.preset_save import SavePresetOperator


class Registration:
    """The classes and menu entries this add-on registers."""

    CLASSES: tuple[type[Operator] | type[Panel], ...] = (AddTreeOperator, SavePresetOperator, TreePanel)

    @classmethod
    def register(cls) -> None:
        """Register the classes and menu entries; raises RuntimeError when the built-in presets are missing."""
        builtin = [e.name for e in PresetStore.for_addon().entries() if e.builtin]
        if AddTreeOperator.DEFAULT_PRESET not in builtin:
            raise RuntimeError(f"Sapling built-in presets are missing ({builtin}); reinstall the extension")
        for klass in cls.CLASSES:
            bpy.utils.register_class(klass)
        Menus.register()

    @classmethod
    def unregister(cls) -> None:
        """Remove the menu entries and unregister the classes, in reverse order of registration."""
        Menus.unregister()
        for klass in reversed(cls.CLASSES):
            bpy.utils.unregister_class(klass)


def register() -> None:
    """Blender's entry point when the add-on is enabled."""
    Registration.register()


def unregister() -> None:
    """Blender's entry point when the add-on is disabled."""
    Registration.unregister()
