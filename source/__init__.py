# SPDX-FileCopyrightText: 2011-2026 Sapling Tree Gen authors (see README)
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Sapling Tree Gen: parametric trees (Weber-Penn) with leaves, pruning, armature and wind."""

import bpy

from .ui.operators import AddTreeOperator, SavePresetOperator
from .ui.panels import Menus, TreePanel


class Registration:
    """The classes and menu entries this add-on registers."""

    CLASSES = (AddTreeOperator, SavePresetOperator, TreePanel)

    @classmethod
    def register(cls):
        for klass in cls.CLASSES:
            bpy.utils.register_class(klass)
        Menus.register()

    @classmethod
    def unregister(cls):
        Menus.unregister()
        for klass in reversed(cls.CLASSES):
            bpy.utils.unregister_class(klass)


def register():
    Registration.register()


def unregister():
    Registration.unregister()
