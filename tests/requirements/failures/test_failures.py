# SPDX-License-Identifier: GPL-3.0-or-later

"""Failure behaviour: failures (the requirements each class or test names)."""

import random
import unittest

import bpy
from support.addon import Addon
from support.operator_stand_in import OperatorStandIn
from support.scene import Scene
from support.trees import Trees
from support.verifies import Verifies


@Verifies("SWR-0140")
class FailureSafety(unittest.TestCase):
    """A generation that fails part-way leaves nothing behind, and a failed edit keeps the old tree."""

    def fail_during_the_bake(self):
        """Make the bark bake raise a RuntimeError for this test only."""
        builder = Addon.module("build.bake").BarkBake
        original = builder.bake

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.bake = failing
        self.addCleanup(setattr, builder, "bake", original)

    def test_failed_add_leaves_nothing(self):
        Scene.reset()
        before = Scene.counts()
        self.fail_during_the_bake()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, makeMesh=True, prune=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
        self.assertEqual(Scene.counts(), before)


@Verifies("SWR-0140")
class FailureRollback(unittest.TestCase):
    """A generation that fails after its objects exist removes them, and puts the user's leaf object back."""

    def test_failed_tag_leaves_nothing(self):
        Scene.reset()
        before = Scene.counts()
        tree_record = Trees.record()
        original = tree_record.__dict__["tag"]

        def failing(*args):
            raise RuntimeError("injected failure")

        tree_record.tag = classmethod(failing)
        self.addCleanup(setattr, tree_record, "tag", original)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**Addon.resolve_preset("quaking_aspen.py"), do_update=True)
        self.assertEqual(Scene.counts(), before)

    def test_failed_add_restores_the_leaf_object(self):
        Scene.reset()
        holder = bpy.data.objects.new("holder", None)
        bpy.context.scene.collection.objects.link(holder)
        holder.location = (1, 2, 3)
        card = Scene.add_leaf_card()
        card.parent = holder
        bpy.context.view_layer.update()
        world = card.matrix_world.copy()
        builder = Addon.module("build.bake").BarkBake
        original = builder.bake

        def failing(*args, **kwargs):
            raise RuntimeError("injected failure")

        builder.bake = failing
        self.addCleanup(setattr, builder, "bake", original)
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(showLeaves=True, leafShape="dFace", makeMesh=True)
        with self.assertRaisesRegex(RuntimeError, "injected failure"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True)
        bpy.context.view_layer.update()
        self.assertIs(card.parent, holder)
        self.assertLess((card.matrix_world.to_translation() - world.to_translation()).length, 1e-6)


@Verifies("SWR-0140")
class RedoPanel(unittest.TestCase):
    """In the redo panel, a change of page or other UI state keeps the tree (execute passes through); a setting
    change regenerates it; a settings error cancels with its message. Blender sets is_repeat only for its own redo,
    so execute runs on a stand-in operator."""

    def execute(self, stand_in):
        """Run the add operator's execute on the stand-in operator and return its result."""
        return Addon.module("ui.operators").AddTreeOperator.execute(stand_in, bpy.context)

    def test_a_settings_error_cancels_with_its_message(self):
        error = Addon.module("settings").SettingsError("Leaf Object 'x' is not an object")

        def failing(context):
            raise error

        made = OperatorStandIn.make(do_update=True, make=failing)
        stand_in = made.operator
        reports = made.reports
        self.assertEqual(self.execute(stand_in), {"CANCELLED"})
        self.assertEqual(reports, [str(error)])


@Verifies("SWR-0141")
class ScriptCalls(unittest.TestCase):
    """UI-only keywords from a script used to make the operator pass through without a tree."""

    def test_ui_keywords_still_generate(self):
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        result = bpy.ops.curve.tree_add(**settings, chooseSet="3", overwrite=False)
        self.assertEqual(result, {"FINISHED"})
        self.assertIn("tree", bpy.data.objects)


@Verifies("SWR-0142")
class SharedRandom(unittest.TestCase):
    """The add-on reseeded Python's shared random module: a tree changed every other user's random numbers."""

    def test_the_shared_random_state_is_untouched(self):
        random.seed(1)
        state = random.getstate()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        self.assertEqual(random.getstate(), state)


@Verifies("SWR-0144")
class DataLifecycle(unittest.TestCase):
    """Removing a tree or generating it again leaves no data blocks behind, with the rig and with the node wind."""

    def test_remove_leaves_no_data(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                Scene.reset()
                empty = Scene.counts()
                self.assertEqual(bpy.ops.curve.tree_add(**Trees.full_settings(rig), do_update=True), {"FINISHED"})
                root = Addon.module("build.tree_record").TreeRecord.root_of(bpy.context.active_object)
                Addon.module("build.tree_record").TreeRecord.remove(root)
                self.assertEqual(Scene.counts(), empty)

    def test_regenerate_leaves_no_orphans(self):
        for rig in (True, False):
            with self.subTest(rig=rig):
                self.regenerate_three_times(Trees.full_settings(rig))

    def regenerate_three_times(self, settings):
        """Generate the tree, then edit it three times, and check that the data block counts stay the same."""
        Scene.reset()
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        kinds = [*Scene.DATA, "materials", "node_groups"]  # materials and node groups are shared, made once
        after_first = Scene.counts(kinds)
        root = Scene.active_object()
        stored = Addon.stored_settings(root)
        for _ in range(3):
            result = bpy.ops.curve.tree_add(replace=root.name, load_stored=False, **stored, do_update=True)
            self.assertEqual(result, {"FINISHED"})
            root = Scene.active_object()
        self.assertEqual(Scene.counts(kinds), after_first)


@Verifies("SWR-0145")
class ArmatureContext(unittest.TestCase):
    """Building a rig leaves another selected and active armature in Object Mode."""

    def test_other_selected_armature_is_not_edited(self):
        Scene.reset()
        other = bpy.data.objects.new("other_rig", bpy.data.armatures.new("other_rig"))
        bpy.context.scene.collection.objects.link(other)
        other.select_set(True)
        bpy.context.view_layer.objects.active = other
        modes = []
        builder = Addon.module("build.armature").ArmatureBuilder
        original = builder.__dict__["_branch_bones"]  # the staticmethod itself, put back as it was

        def recording(*args):
            modes.append(other.mode)
            return original.__func__(*args)

        builder._branch_bones = staticmethod(recording)
        self.addCleanup(setattr, builder, "_branch_bones", original)
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True)
        self.assertEqual(bpy.ops.curve.tree_add(**settings, do_update=True), {"FINISHED"})
        self.assertEqual(modes, ["OBJECT"], "the other armature stays in Object Mode while bones are made")
        self.assertEqual(len(other.data.bones), 0)
        self.assertEqual(bpy.context.mode, "OBJECT")
        self.assertEqual(bpy.context.active_object.location.to_tuple(), (0.0, 0.0, 0.0))
