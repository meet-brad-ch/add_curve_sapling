# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: trunk (the requirements each class or test names)."""

import itertools
import unittest
import unittest.mock

import bpy
import numpy as np
from mathutils import Vector
from support.addon import Addon
from support.evaluated import Evaluated
from support.model import Model
from support.scene import Scene
from support.verifies import Verifies


@Verifies("SWR-0060")
class DeepTrees(unittest.TestCase):
    """The last-level checks compared the level index clamped to 3 with levels - 1, so with 5 or 6
    levels Close Tip and the last level's base size reset never applied."""

    def tip_radii(self, close_tip):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=5, branches=(0, 8, 3, 2), closeTip=close_tip)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        return [points[-1][1] for points in Evaluated.spline_points()]

    def test_close_tip_on_five_levels(self):
        closed = self.tip_radii(True)
        self.assertGreater(closed.count(0.0), self.tip_radii(False).count(0.0))


@Verifies("SWR-0061")
class SeveralTrunks(unittest.TestCase):
    """Trunks above 1 grows a clump: further trunks stand on a disc around the first (bamboo)."""

    TRUNKS = 3

    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, trunks=cls.TRUNKS, useRig=True, windAnim=True)
        cls.settings = settings
        cls.result = Scene.generate(settings)

    def roots(self):
        return [b for b in Scene.armature().data.bones if b.parent is None]

    @staticmethod
    def root_of(bone):
        """The bone's farthest parent (a trunk's first bone). A chain of parents is at most as long as there are
        bones; Blender refuses a parent loop, so the bound only makes the loop's end visible."""
        bones = Scene.armature().data.bones
        for _ in range(len(bones)):
            if bone.parent is None:
                return bone
            bone = bone.parent
        raise AssertionError(f"{bone.name}: the chain of parents is longer than the bones")

    def base_bones(self):
        """The names of each trunk's first two bones: the root and its connected child."""
        names = set()
        for root in self.roots():
            for bone in (root, *root.children):
                if bone.use_connect or bone.parent is None:
                    names.add(bone.name)
        return {name for name in names if name.endswith((".000", ".001"))}

    def test_trunks_stand_on_the_ground_apart(self):
        self.assertEqual(self.result, {"FINISHED"})
        bases = [Vector(s[0][0]) for s in Evaluated.spline_points() if s[0][0][2] == 0.0]
        self.assertEqual(len(bases), self.TRUNKS)
        s = self.settings
        gap = 2.5 * s["scale"] * s["length"][0] * s["ratio"] * s["scale0"]
        for a, b in itertools.combinations(bases, 2):
            self.assertGreaterEqual((a - b).length, gap * 0.999)

    def test_each_trunk_is_a_root_with_its_own_branches(self):
        roots = self.roots()
        self.assertEqual(len(roots), self.TRUNKS)
        branches_per_root = {root.name: 0 for root in roots}
        for bone in Scene.armature().data.bones:
            if bone.parent is not None and not bone.use_connect:  # the first bone of a branch
                branches_per_root[self.root_of(bone).name] += 1
        self.assertTrue(all(count >= 10 for count in branches_per_root.values()), branches_per_root)

    def test_every_trunk_base_stays_still(self):
        base = self.base_bones()
        self.assertGreaterEqual(len(base), self.TRUNKS)
        quoted = [f'"{name}"' for name in base]
        for fc in Evaluated.fcurves_of(Scene.armature()):
            if not any(name in fc.data_path for name in quoted):
                continue
            for mod in fc.modifiers:
                self.assertEqual(mod.amplitude, 0.0, f"{fc.data_path}[{fc.array_index}]")


@Verifies("SWR-0070")
class TrunkPlacementFailure(unittest.TestCase):
    """Placing a trunk gives up after a bounded number of tries instead of searching forever (tree-gen hangs)."""

    def test_no_room_is_an_error(self):
        clump = Addon.module("model.branching").TrunkClump
        tries = clump.TRIES
        clump.TRIES = 0  # no try can succeed
        self.addCleanup(setattr, clump, "TRIES", tries)
        Scene.reset()
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=1, trunks=2)
        with self.assertRaisesRegex(RuntimeError, "No room for trunk 2 of 2 after 0 tries"):
            bpy.ops.curve.tree_add(**settings, do_update=True)


@Verifies("SWR-0073")
class TrunksFaceOut(unittest.TestCase):
    """Trunks Face Out turns each further trunk of a clump so that a positive Curvature bends it outward."""

    CLUMP = {
        "levels": 1,
        "trunks": 6,
        "curve": (60.0, 0.0, 0.0, 0.0),
        "curveV": (0.0, 0.0, 0.0, 0.0),
        "curveBack": (0.0, 0.0, 0.0, 0.0),
        "attractUp": (0.0, 0.0, 0.0, 0.0),
        "segSplits": (0.0, 0.0, 0.0, 0.0),
        "baseSplits": 0,
        "showLeaves": False,
    }

    def outward(self, **changes):
        """Per further trunk, the cosine between its base's direction from the centre and its tip's sideways shift."""
        model = Model.grow_preset(**self.CLUMP, **changes)
        flat = model.curve.flatten()
        cosines = []
        for trunk in range(1, model.grown.level_ends[0]):
            co = flat.co[flat.start[trunk] : flat.start[trunk + 1]].astype(np.float64)
            base, shift = co[0, :2], co[-1, :2] - co[0, :2]
            cosines.append(float(base @ shift / (np.linalg.norm(base) * np.linalg.norm(shift))))
        return np.array(cosines)

    def test_trunks_face_out_bend_away_from_the_centre(self):
        cosines = self.outward(trunksFaceOut=True)
        self.assertEqual(len(cosines), 5)
        self.assertGreater(cosines.min(), 0.99)

    def test_random_trunks_bend_any_way(self):
        self.assertLess(self.outward().min(), 0.5)


@Verifies("SWR-0075")
class SplitTrunkBranches(unittest.TestCase):
    """A split trunk shares one branch per height among its pieces, as Sapling's per-stem code did: the array
    rewrite grouped the trunk's sprouts by their offset, which each piece measures on its own length, so every
    piece kept its own branch at every height and a birch with two base splits grew 2.7 times the branches."""

    def branches(self, base_splits: int) -> int:
        settings = Addon.resolve_preset("white_birch.py")
        settings.update(levels=2, baseSplits=base_splits, segSplits=(0.0, 0.0, 0.0, 0.0), showLeaves=False)
        ends = Model.grow(settings).grown.level_ends
        return ends[1] - ends[0]

    def test_base_splits_do_not_multiply_the_first_level(self):
        whole, split = self.branches(0), self.branches(2)
        self.assertGreater(whole, 20)
        self.assertLess(split, 1.25 * whole, f"{split} branches on the split trunk, {whole} on the whole one")
