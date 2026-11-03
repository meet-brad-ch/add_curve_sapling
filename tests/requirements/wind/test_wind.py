# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind: wind (the requirements each class or test names)."""

import re
import unittest
import unittest.mock
from collections import defaultdict

import bpy
import numpy as np
from support.addon import Addon
from support.evaluated import Evaluated
from support.foliage import Foliage
from support.node_trees import NodeTrees
from support.scene import Scene
from support.verifies import Verifies


class NodeWind(unittest.TestCase):
    """Wind without the rig: the joints' transforms, composed in Geometry Nodes on the wind curves (one point per
    joint), move the bark."""

    @classmethod
    def setUpClass(cls):
        cls.settings = NodeTrees.settings(windAnim=True, loopFrames=48)
        cls.result = Scene.generate(cls.settings)
        cls.rest = Evaluated.vertices("tree", 1)

    @Verifies("SWR-0120")
    def test_no_armature(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertFalse([ob for ob in bpy.data.objects if ob.type == "ARMATURE"])
        self.assertEqual([m.name for m in Evaluated.tree_curves().modifiers], [])
        inputs = Evaluated.modifier_inputs(bpy.data.objects["tree"])["Sapling Tree"]["inputs"]
        self.assertEqual((inputs["Wind"], inputs["Wind Joints"], inputs["Rig"]), (True, "tree_wind", False))

    @Verifies("SWR-0120")
    def test_wind_curves_hold_one_point_per_joint(self):
        joints = NodeTrees.model_joints(windAnim=True, loopFrames=48).joints
        wind = bpy.data.objects["tree_wind"]
        root = bpy.data.objects["tree"]
        self.assertEqual((wind.type, wind.parent, wind.hide_viewport, wind.hide_render), ("CURVES", root, True, True))
        self.assertEqual([m.name for m in wind.modifiers], ["Sapling Wind"])
        self.assertEqual(len(wind.data.position_data), len(joints.joint_point))
        self.assertEqual([len(c.points) for c in wind.data.curves], joints.count[joints.eligible].tolist())
        self.assertLess(len(joints.joint_point), len(Evaluated.tree_curves().data.position_data))
        numbers = np.empty(len(Evaluated.tree_curves().data.position_data), np.int32)
        Evaluated.tree_curves().data.attributes["sapling_joint"].data.foreach_get("value", numbers)
        np.testing.assert_array_equal(numbers, joints.ordinals(joints.point_joints()))

    @Verifies("SWR-0120")
    def test_bark_moves(self):
        moved = np.linalg.norm(Evaluated.vertices("tree", 17) - self.rest, axis=1)
        self.assertGreater(moved.max(), 1e-3)
        self.assertGreater((moved > 1e-5).mean(), 0.5)

    @Verifies("SWR-0123")
    def test_loop_returns_to_the_first_frame(self):
        self.assertLess(np.abs(Evaluated.vertices("tree", 49) - self.rest).max(), 1e-4)

    @Verifies("SWR-0120")
    def test_trunk_base_stays_still(self):
        """The first two joints of the trunk hold still: the centres of the bark rings at the trunk's first three
        points (a ring may still turn: the moving points above change the curve's direction there)."""
        s = self.settings
        profile = 4 + 2 * s["bevelRes"]
        for frame in (9, 17, 33):
            now = Evaluated.vertices("tree", frame)
            for point in range(3):
                ring = slice(point * s["resU"] * profile, (point * s["resU"] + 1) * profile)
                with self.subTest(frame=frame, point=point):
                    centre = now[ring].mean(axis=0) - self.rest[ring].mean(axis=0)
                    self.assertLess(np.abs(centre).max(), 1e-6)

    @Verifies("SWR-0120")
    def test_bark_stretches_no_more_than_the_rig(self):
        """Rotations keep lengths: the bark's edges hardly change (the rig's envelopes stretch up to about 3 %)."""
        edges = self.evaluated_edges()
        rest = np.linalg.norm(self.rest[edges[:, 0]] - self.rest[edges[:, 1]], axis=1)
        now = Evaluated.vertices("tree", 17)
        lengths = np.linalg.norm(now[edges[:, 0]] - now[edges[:, 1]], axis=1)
        long = rest > 1e-4
        stretch = np.abs(lengths[long] / rest[long] - 1.0)
        self.assertLess(np.percentile(stretch, 99), 0.035)

    @staticmethod
    def evaluated_edges():
        ob = bpy.data.objects["tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = ob.to_mesh()
        edges = np.empty(len(mesh.edges) * 2, np.int32)
        mesh.edges.foreach_get("vertices", edges)
        ob.to_mesh_clear()
        return edges.reshape(-1, 2)


@Verifies("SWR-0120")
class NodeWindLeaves(unittest.TestCase):
    """Leaves follow the joint they hang from: rigid, and at the same distance from it on every frame."""

    @classmethod
    def setUpClass(cls):
        settings = NodeTrees.settings(showLeaves=True, windAnim=True)
        cls.result = Scene.generate(settings)
        cls.leaves = bpy.data.objects["leaves"]
        cls.size = 6 if settings["leafShape"] == "hex" else 4

    def joint_positions(self, frame):
        """Where each leaf vertex's joint head is at a frame."""
        joints = np.empty(len(self.leaves.data.vertices), np.int32)
        self.leaves.data.attributes["sapling_joint"].data.foreach_get("value", joints)
        return NodeTrees.wind_joint_positions(frame, joints)

    def test_modifiers(self):
        self.assertEqual(self.result, {"FINISHED"})
        self.assertEqual([m.name for m in self.leaves.modifiers], ["Sapling Follow Wind"])

    def test_leaves_move_rigidly_with_their_joint(self):
        rest = Evaluated.vertices("leaves", 1)
        rest_distance = np.linalg.norm(rest - self.joint_positions(1), axis=1)
        moved = 0
        for frame in (9, 17):
            now = Evaluated.vertices("leaves", frame)
            distance = np.linalg.norm(now - self.joint_positions(frame), axis=1)
            np.testing.assert_allclose(distance, rest_distance, atol=1e-4)
            leaves_now = now.reshape(-1, self.size, 3)
            leaves_rest = rest.reshape(-1, self.size, 3)
            span_now = np.linalg.norm(leaves_now - leaves_now[:, :1], axis=2)
            span_rest = np.linalg.norm(leaves_rest - leaves_rest[:, :1], axis=2)
            np.testing.assert_allclose(span_now, span_rest, atol=1e-4)
            moved += int((np.linalg.norm(now - rest, axis=1) > 1e-4).sum())
        self.assertGreater(moved, len(rest) // 2)


@Verifies("SWR-0120")
class BoneStep(unittest.TestCase):
    """With Bone Step > 1 a bone spans several points: its tail came from the point after its head instead of
    the point Joint Length segments on, and only one of the two trunk base bones was held still."""

    result: set[str]

    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, jointStep=(2, 2, 1, 1))
        cls.result = Scene.generate(settings)

    def test_trunk_base_bones_do_not_sway(self):
        base = sorted(b.name for b in Scene.armature().data.bones if b.name.startswith("bone000."))[:2]
        self.assertEqual(len(base), 2)
        matched = 0
        for fc in Evaluated.fcurves_of(Scene.armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                matched += 1
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")
        self.assertEqual(matched, 4, "X and Z sway curves of both base bones")


@Verifies("SWR-0120", "SWR-0122")
class BlossomObjects(unittest.TestCase):
    """The blossoms object of a generated tree."""

    def generate(self, **changes):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update({"levels": 2, "showLeaves": True, "blossomRate": 0.5, **changes})
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return bpy.data.objects["blossoms"]

    def test_node_wind_and_flutter_move_the_blossoms(self):
        blossoms = self.generate(windAnim=True, leafFlutter=True)
        self.assertEqual([m.name for m in blossoms.modifiers], ["Leaf Flutter", "Sapling Follow Wind"])
        rest = Evaluated.vertices("blossoms")
        bpy.context.scene.frame_set(17)
        self.assertGreater(np.abs(Evaluated.vertices("blossoms") - rest).max(), 1e-4)


@Verifies("SWR-0121")
class NodeWindMatchesTheRig(unittest.TestCase):
    """The node wind moves the bark as the armature's wind does, from the same random draws."""

    FRAMES = range(5, 97, 8)

    def displacements(self, rig, strength):
        settings = NodeTrees.settings(levels=3, branches=(0, 30, 10, 0), windAnim=True, useRig=rig)
        settings.update(windStrength=strength, gustStrength=strength)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return np.stack([Evaluated.vertices("tree", frame) for frame in self.FRAMES])

    def relative_rms(self, strength):
        rest = self.still()
        rig = self.displacements(True, strength) - rest
        node = self.displacements(False, strength) - rest
        return float(np.sqrt(np.mean((node - rig) ** 2)) / np.sqrt(np.mean(rig**2)))

    def still(self):
        settings = NodeTrees.settings(levels=3, branches=(0, 30, 10, 0))
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return Evaluated.vertices("tree", 1)

    def test_wind_1(self):
        self.assertLess(self.relative_rms(1.0), 0.08)

    def test_wind_3(self):
        self.assertLess(self.relative_rms(3.0), 0.02)


@Verifies("SWR-0121")
class WindAnimation(unittest.TestCase):
    """Blender 5.0 removed Action.fcurves; wind animation crashed on every 5.x release."""

    result: set[str]

    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        cls.result = Scene.generate(settings)

    def test_generates(self):
        self.assertEqual(self.result, {"FINISHED"})
        # fcurve_ensure_for_datablock assigns the action slot itself; a big rig's actions sit in NLA strips
        animation = Scene.armature().animation_data
        strips = [strip for track in animation.nla_tracks for strip in track.strips]
        slots = [animation.action_slot] if animation.action else [strip.action_slot for strip in strips]
        self.assertTrue(slots)
        self.assertTrue(all(slot is not None for slot in slots))

    def test_branch_bones_move(self):
        arm = Scene.armature()
        scene = bpy.context.scene
        poses = {}
        for frame in (1, 17):
            scene.frame_set(frame)
            poses[frame] = {p.name: tuple(p.rotation_euler) for p in arm.pose.bones}
        moved = {name for name in poses[1] if poses[1][name] != poses[17][name]}
        self.assertTrue(any(n.startswith("bone") for n in moved), "no branch bone moves")

    def test_each_bone_owns_its_x_and_z_sway(self):
        channels = defaultdict(set)
        for fc in Evaluated.fcurves_of(Scene.armature()):
            match = re.match(r'pose\.bones\["(.+)"\]\.rotation_euler', fc.data_path)
            self.assertIsNotNone(match, fc.data_path)
            assert match is not None
            bone = match.group(1)
            channels[bone].add(fc.array_index)
            # ungrouped: a grouped F-curve costs Blender about 4 times as much to create on big trees
            self.assertIsNone(fc.group, fc.data_path)
        names = [b.name for b in Scene.armature().data.bones]
        self.assertTrue(names)
        for name in names:
            self.assertEqual(channels[name], {0, 2}, name)


@Verifies("SWR-0121")
class LargeRigWind(unittest.TestCase):
    """Above WindAnimator.CHUNK bones the wind's F-curves sit in one action per chunk, played by NLA strips. The
    strips spanned frames 1 to 2 (the range of an action whose curves are all F-modifiers) and held their end value
    from then on: the bones did not follow their F-curves (measured at 4,133 bones: 8,246 of 8,266 channels off)."""

    @classmethod
    def setUpClass(cls):
        animator = Addon.module("build.wind").WindAnimator
        cls.addClassCleanup(setattr, animator, "CHUNK", animator.CHUNK)  # runs even if this method fails
        animator.CHUNK = 50  # the test tree's 308 bones take the large-rig path
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True)
        cls.result = Scene.generate(settings)

    def test_strips_span_the_timeline(self):
        self.assertEqual(self.result, {"FINISHED"})
        strips = [strip for track in Scene.armature().animation_data.nla_tracks for strip in track.strips]
        self.assertGreater(len(strips), 1)
        for strip in strips:
            self.assertEqual((strip.frame_start, strip.action_frame_start), (0.0, 0.0), strip.name)
            self.assertGreaterEqual(strip.frame_end, 100_000, strip.name)
            self.assertEqual(strip.action_frame_end, strip.frame_end, strip.name)

    def test_bones_follow_their_f_curves(self):
        arm = Scene.armature()
        curves = {(c.data_path, c.array_index): c for c in Evaluated.fcurves_of(arm)}
        self.assertEqual(len(curves), 2 * len(arm.data.bones))
        self.assertGreater(len(arm.data.bones), 50, "the rig takes the large-rig path")
        for frame in (17, 60):
            bpy.context.scene.frame_set(frame)
            for bone in arm.pose.bones:
                for index in (0, 2):
                    curve = curves[(f'pose.bones["{bone.name}"].rotation_euler', index)]
                    self.assertAlmostEqual(bone.rotation_euler[index], curve.evaluate(frame), places=5, msg=bone.name)


@Verifies("SWR-0123")
class LeafFlutterOptions(unittest.TestCase):
    def generate(self, **overrides):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, useRig=True, windAnim=True, leafFlutter=True)
        settings.update(overrides)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})

    def test_a_loop_starts_and_ends_at_rest(self):
        self.generate(loopFrames=48)
        rest = [v.co.copy() for v in bpy.data.objects["leaves"].data.vertices]

        def largest_move(frame):  # turning by zero about the sprout can still round in the last bit
            return max((a - b).length for a, b in zip(Foliage.positions(frame, armature_on=False), rest, strict=True))

        self.assertLess(largest_move(0), 1e-6)
        self.assertLess(largest_move(48), 1e-6)
        self.assertGreater(largest_move(24), 1e-3)
