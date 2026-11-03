# SPDX-License-Identifier: GPL-3.0-or-later

"""Trees made, edited and found through the public operator."""

import bpy

from support.addon import Addon
from support.model import Model
from support.scene import Scene


class Trees:
    """Trees made, edited and found through the public operator."""

    @staticmethod
    def record():
        """The add-on's TreeRecord class (a tree's ownership, stored settings and parts)."""
        return Addon.module("build.tree_record").TreeRecord

    @staticmethod
    def add(**overrides):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(overrides)
        result = bpy.ops.curve.tree_add(**settings, do_update=True)
        if result != {"FINISHED"}:
            raise AssertionError(result)
        return Scene.active_object()

    @staticmethod
    def add_with_leaves():
        """A quaking aspen with leaves in an empty scene."""
        Scene.reset()
        return Trees.add(showLeaves=True)

    @staticmethod
    def edit(root, **changes):
        """Edit Sapling Tree with some settings changed (stored settings + changes)."""
        stored = Addon.stored_settings(root)
        stored.update(changes)
        return bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)

    @staticmethod
    def root_of(ob):
        return Addon.module("build.tree_record").TreeRecord.root_of(ob)

    @staticmethod
    def generated_model(test, settings):
        """Generate a tree (the result must be FINISHED) and return the model the generator grew for it."""
        captured = Model.record_growth(test)
        test.assertEqual(Scene.generate(settings), {"FINISHED"})
        return captured[-1]

    @staticmethod
    def full_settings(rig=True):
        """Everything on, with the armature rig or with the node wind."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=rig, windAnim=True, leafFlutter=True, makeMesh=True, prune=True)
        return settings
