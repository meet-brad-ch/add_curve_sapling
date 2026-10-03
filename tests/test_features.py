# SPDX-License-Identifier: GPL-3.0-or-later

"""Generator features added for tree-gen's species: several trunks, ..."""

import itertools
import unittest

import bpy
import helpers


def armature():
    return next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")


def root_of(bone):
    while bone.parent is not None:
        bone = bone.parent
    return bone


class SeveralTrunks(unittest.TestCase):
    """Trunks above 1 grows a clump: further trunks stand on a disc around the first (bamboo)."""

    TRUNKS = 3

    @classmethod
    def setUpClass(cls):
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, trunks=cls.TRUNKS, useArm=True, armAnim=True)
        cls.settings = settings
        cls.result = helpers.generate(settings)

    def roots(self):
        return [b for b in armature().data.bones if b.parent is None]

    def test_trunks_stand_on_the_ground_apart(self):
        self.assertEqual(self.result, {"FINISHED"})
        splines = bpy.data.objects["tree"].data.splines
        bases = [s.bezier_points[0].co.copy() for s in splines if s.bezier_points[0].co.z == 0.0]
        self.assertEqual(len(bases), self.TRUNKS)
        s = self.settings
        gap = 2.5 * s["scale"] * s["length"][0] * s["ratio"] * s["scale0"]
        for a, b in itertools.combinations(bases, 2):
            self.assertGreaterEqual((a - b).length, gap * 0.999)

    def test_each_trunk_is_a_root_with_its_own_branches(self):
        roots = self.roots()
        self.assertEqual(len(roots), self.TRUNKS)
        branches_per_root = {root.name: 0 for root in roots}
        for bone in armature().data.bones:
            if bone.parent is not None and not bone.use_connect:  # the first bone of a branch
                branches_per_root[root_of(bone).name] += 1
        self.assertTrue(all(count >= 10 for count in branches_per_root.values()), branches_per_root)

    def test_every_trunk_base_stays_still(self):
        base = {b.name for root in self.roots() for b in (root, *root.children) if b.use_connect or b.parent is None}
        base = {name for name in base if name.endswith((".000", ".001"))}
        self.assertGreaterEqual(len(base), self.TRUNKS)
        for fc in helpers.fcurves_of(armature()):
            if any(f'"{name}"' in fc.data_path for name in base):
                for mod in fc.modifiers:
                    self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")


class TrunkPlacementFailure(unittest.TestCase):
    """Placing a trunk gives up after a bounded number of tries instead of searching forever (tree-gen hangs)."""

    def test_no_room_is_an_error(self):
        clump = helpers.module("model.branching").TrunkClump
        tries = clump.TRIES
        clump.TRIES = 0  # no try can succeed
        self.addCleanup(setattr, clump, "TRIES", tries)
        helpers.reset_scene()
        settings = helpers.resolve_preset("quaking_aspen.py")
        settings.update(levels=1, trunks=2)
        with self.assertRaisesRegex(RuntimeError, "No room for trunk 2 of 2 after 0 tries"):
            bpy.ops.curve.tree_add(**settings, do_update=True)
