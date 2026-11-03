# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/build: guards."""

import unittest
from types import SimpleNamespace

import bpy
import numpy as np
from support.addon import Addon
from support.model import Model
from support.scene import Scene


class FailFast(unittest.TestCase):
    def test_bone_geometry_must_match_the_bones(self):
        Scene.reset()
        armature = bpy.data.armatures.new("probe")
        ob = bpy.data.objects.new("probe", armature)
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        self.addCleanup(bpy.ops.object.mode_set, mode="OBJECT")
        armature.edit_bones.new("extra")  # a bone the geometry does not know
        none = np.zeros((0, 3), np.float32)
        with self.assertRaisesRegex(RuntimeError, "1 bones for the geometry of 0"):
            Addon.module("build.armature").BoneGeometry(none, none).write(armature)

    def test_a_math_node_refuses_more_values_than_inputs(self):
        group = bpy.data.node_groups.new("probe", "GeometryNodeTree")
        self.addCleanup(bpy.data.node_groups.remove, group)
        maths = Addon.module("build.node_math").NodeMath(group)
        maths.math("ADD", 1.0, 2.0)  # two inputs, two values
        with self.assertRaisesRegex(ValueError, "the SQRT node has 1 inputs, 2 values were given"):
            maths.math("SQRT", 1.0, 2.0)

    def test_foreign_node_group_with_the_instancer_name(self):
        Scene.reset()
        nodes = Addon.module("build.leaf_object").LeafInstancerNodes
        bpy.data.node_groups.new(nodes.GROUP, "ShaderNodeTree")
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, leafShape="dVert")
        card = Scene.add_leaf_card()
        with self.assertRaisesRegex(RuntimeError, "is not a Geometry Nodes group"):
            bpy.ops.curve.tree_add(**settings, leafDupliObj=card.name, do_update=True)
        self.assertEqual([ob.name for ob in bpy.data.objects], [card.name])


class ReadOnlyParams(unittest.TestCase):
    """Generation stages share one TreeParams; none of them may change it for the others."""

    def test_params_are_read_only(self):
        settings = Addon.operator_defaults()
        params = Model.params(settings)
        self.assertEqual(params.levels, settings["levels"])
        with self.assertRaisesRegex(AttributeError, "read-only; cannot set levels"):
            params.levels = 1


class Guards(unittest.TestCase):
    """The internal checks fail with a message naming the cause, instead of a wrong tree or a bare KeyError."""

    def test_unknown_node_group_input(self):
        Scene.reset()
        self.assertEqual(Scene.generate(Addon.resolve_preset("quaking_aspen.py")), {"FINISHED"})
        modifier = bpy.data.objects["tree"].modifiers["Sapling Tree"]
        with self.assertRaisesRegex(RuntimeError, "has no input called 'Bogus'"):
            Addon.module("build.node_groups").SharedNodeGroup.set_input(modifier, "Bogus", 1)

    def test_following_twice_is_an_error(self):
        Scene.reset()
        mesh = bpy.data.meshes.new("probe")
        mesh.vertices.add(1)
        ob = bpy.data.objects.new("probe", mesh)
        mesh.attributes.new("sapling_joint", "INT", "POINT")
        with self.assertRaisesRegex(RuntimeError, "already has a 'sapling_joint' attribute"):
            Addon.module("build.node_wind").NodeWind.follow(ob, ob, np.zeros(1, np.int32))

    def test_sway_for_other_bones(self):
        sway = SimpleNamespace(wind1=np.zeros(2))
        animator = Addon.module("build.wind").WindAnimator(None)
        with self.assertRaisesRegex(RuntimeError, "1 bones for the sway of 2 joints"):
            animator.add_joints(["bone000.000"], sway)

    def test_unknown_leaf_shape(self):
        with self.assertRaisesRegex(ValueError, "unknown leaf shape star"):
            Addon.module("model.leaves").LeafShape.verts_per_leaf("star")

    def test_original_branching_does_not_pick(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(rMode="original")
        pick = Addon.module("model.branching").TrunkPick(Model.params(settings), np.zeros(1, np.uint64))
        one = np.zeros(1, np.int64)
        sprouts = SimpleNamespace(is_end=np.zeros(1, bool), family=one, position=one)
        with self.assertRaisesRegex(ValueError, "does not choose"):
            pick.choose(sprouts, 0.0, np.zeros((1, 3)))

    def test_curve_attribute_of_another_kind(self):
        data = bpy.data.hair_curves.new("probe")
        self.addCleanup(bpy.data.hair_curves.remove, data)
        data.attributes.new("probe", "FLOAT", "POINT")
        with self.assertRaisesRegex(RuntimeError, "attribute probe is FLOAT on POINT, not INT on POINT"):
            Addon.module("build.tree_root").CurveSource._attribute(data, "probe", "INT", "POINT")

    def test_object_factory_rules(self):
        factory = Addon.module("build.objects").ObjectFactory
        with self.assertRaisesRegex(ValueError, "at least one collection"):
            factory([])
        Scene.reset()
        objects = factory([bpy.context.scene.collection])
        self.addCleanup(objects.discard)
        objects.new("probe", None)
        with self.assertRaisesRegex(ValueError, "already has a 'probe' object"):
            objects.new("probe", None)

    def test_baked_joint_numbers_out_of_range(self):
        mesh = bpy.data.meshes.new("probe")
        self.addCleanup(bpy.data.meshes.remove, mesh)
        mesh.vertices.add(2)
        attribute = mesh.attributes.new("sapling_ordinal", "FLOAT", "POINT")
        attribute.data.foreach_set("value", [0.0, 5.0])
        with self.assertRaisesRegex(RuntimeError, "Baked joint numbers 0..5 are outside the 2 joints"):
            Addon.module("build.bake").BarkBake._vertex_ordinals(mesh, 2)
