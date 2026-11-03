# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: pruning (the requirements each class or test names)."""

import unittest
import unittest.mock

import bpy
import numpy as np
from support.addon import Addon
from support.crown import Crown
from support.evaluated import Evaluated
from support.model import Model
from support.scene import Scene
from support.verifies import Verifies


class PrunedTrees(unittest.TestCase):
    """Pruning on the grid: the kept stems fit the envelope, the removed ones are stubs without sprouts."""

    @Verifies("SWR-0064")
    def test_kept_stems_end_near_or_inside_the_envelope(self):
        """The search settles on an interval midpoint and the envelope is not monotone along a stem, so a few ends
        overshoot a little: measured 13-18 % outside, worst 1.13-1.31 x the limit, for this search and the per-stem
        search before it. Without pruning most ends are far outside."""
        for preset, changes in (("callistemon", {}), ("quaking_aspen", {"pruneWidth": 0.25})):
            with self.subTest(preset=preset):
                model = Model.grow_preset(preset=preset, prune=True, pruneRatio=1.0, **changes)
                params = model.params
                curve = model.curve
                grown = model.grown
                over = self.overshoots(params, curve, grown)
                self.assertGreater(len(over), 100)
                self.assertLess(
                    (over > 1.0).mean(), 0.25, f"{100 * (over > 1.0).mean():.0f} % of the stem ends outside"
                )
                self.assertLess(over.max(), 1.35, f"worst end {over.max():.2f} x the envelope")

    @staticmethod
    def overshoots(params, curve, grown):
        """Per kept stem end, its distance from the axis over the envelope's limit there (1 = on the envelope)."""
        flat = curve.flatten()
        scale = params.scale
        ends = flat.co[flat.start[1:] - 1].astype(np.float64)
        sizes = flat.sizes
        over = []
        for i, end in enumerate(ends):
            level = Model.level_index(grown, i)
            if sizes[i] < 2 or (level == 0 and end[2] < params.prune_base_clamped * scale):
                continue
            ratio = (scale - end[2]) / (scale * max(1 - params.prune_base_clamped, 1e-6))
            limit = params.prune_width * params.envelope(ratio)
            if limit > 0:
                over.append(np.hypot(end[0], end[1]) / scale / limit)
        return np.array(over)

    @Verifies("SWR-0065")
    def test_removed_stems_are_stubs_without_sprouts(self):
        model = Model.grow_preset(preset="quaking_aspen", prune=True, pruneRatio=1.0, pruneWidth=0.25)
        curve = model.curve
        grown = model.grown
        flat = curve.flatten()
        removed = [i for i in range(1, len(flat.sizes)) if flat.sizes[i] == 1]
        self.assertGreater(len(removed), 10)
        bone_name = Addon.module("model.stem").BoneName
        parents = {bone_name.spline(link.bone) for link in grown.bone_map if link.bone}
        self.assertFalse(set(removed) & parents, "no stem hangs from a removed stem")
        self.assertFalse(set(removed) & set(grown.sprouts.parent_spline.tolist()), "no leaf sprouts on a removed stem")
        free = Addon.module("model.curve_data").HandleType.FREE
        for i in removed:
            point = int(flat.start[i])
            self.assertEqual(int(flat.h1[point]), free)
            self.assertEqual(int(flat.h2[point]), free)
            # the stub's handles are its start and its start direction: never uninitialized memory
            self.assertEqual(flat.left[point].tolist(), [0.0, 0.0, 0.0])
            self.assertLess(float(np.linalg.norm(flat.right[point] - flat.co[point])), 1.001)
        self.assertEqual(len(grown.bone_map), len(flat.sizes))

    @Verifies("SWR-0064")
    def test_partial_ratio_keeps_every_stem(self):
        model = Model.grow_preset(preset="quaking_aspen", prune=True, pruneRatio=0.5, pruneWidth=0.25)
        curve = model.curve
        self.assertTrue((curve.flatten().sizes >= 2).all())


@Verifies("SWR-0064")
class PruningInterpolation(unittest.TestCase):
    """interpStem: t rounding to the stem top gave index == numSegs -> IndexError (review, v0.3.6)."""

    def test_branch_distribution_near_max(self):
        settings = Addon.resolve_preset("callistemon.py")
        settings.update(prune=True, branchDist=9.6)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        # every spline is finite, and the branches crowd towards the top of the trunk (Branch Distribution > 1)
        splines = Evaluated.spline_points()
        not_finite = [i for i, points in enumerate(splines) if not all(np.isfinite(co).all() for co, _r in points)]
        self.assertEqual(not_finite[:5], [], "splines with NaN or inf points")
        trunk_top = max(co[2] for co, _radius in splines[0])
        starts = [points[0][0][2] for points in splines[1:] if len(points) > 1]
        self.assertGreater(float(np.median(starts)), 0.5 * trunk_top)


class PrunedAwayStems(unittest.TestCase):
    """Pruning shrank some stems to ~1 cm stubs: invisible, but their leaves floated next to the branches."""

    @Verifies("SWR-0065")
    def test_only_short_stems_at_full_ratio_are_removed(self):
        pruning = Addon.module("model.pruning").LevelPruning
        self.assertTrue(pruning.removes(0.1, 1.0))
        self.assertFalse(pruning.removes(0.2, 1.0))
        self.assertFalse(pruning.removes(0.1, 0.8))  # a partial ratio keeps part of the stem anyway

    @Verifies("SWR-0065")
    def test_removed_stems_keep_only_their_start_point(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(prune=True, pruneRatio=1.0, pruneWidth=0.25, useRig=True, windAnim=True, makeMesh=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        splines = Evaluated.spline_points()
        removed = [i for i, s in enumerate(splines) if i > 0 and len(s) == 1]
        self.assertGreater(len(removed), 10)
        bones = {b.name for b in bpy.data.objects["treeArm"].data.bones}
        kept = [name for name in bones for i in removed if name.startswith(f"bone{i:03d}.")]
        self.assertEqual(kept[:5], [], "bones of removed stems")

    @Verifies("SWR-0066")
    def test_envelope_is_hidden(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(prune=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        envelope = bpy.data.objects["envelope"]
        self.assertTrue(envelope.hide_viewport)
        self.assertTrue(envelope.hide_render)


@Verifies("SWR-0068")
class WindShape(unittest.TestCase):
    """A pruned tree grown still, sheared and bent."""

    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("black_oak.py")
        settings.update(levels=3, prune=True, pruneWidth=0.5, pruneRatio=1.0, seed=3)
        cls.base = settings
        cls.still = Crown.points(settings)

    def grown(self, **wind) -> np.ndarray:
        settings = dict(self.base)
        settings.update(wind)
        return Crown.points(settings)

    def test_a_direction_without_strength_changes_nothing(self):
        turned = self.grown(windDir=137.0)
        np.testing.assert_array_equal(turned, self.still)

    def test_the_shear_moves_the_crown_downwind(self):
        sheared = self.grown(windDir=0.0, windShear=0.6)
        # downwind is -Y: the crown reaches less far windward (+Y) and at least as far downwind (-Y); its reach, not
        # its mean, is what the envelope cuts (the inner points stay where they are)
        self.assertLess(sheared[:, 1].max(), 0.8 * self.still[:, 1].max())
        self.assertLessEqual(sheared[:, 1].min(), self.still[:, 1].min())

    def test_the_bend_turns_the_branches_downwind(self):
        bent = self.grown(windDir=90.0, windBend=[0.0, 0.6, 0.6, 0.0])
        spread = np.ptp(self.still[:, 0])
        # downwind is +X
        self.assertGreater(bent[:, 0].mean(), self.still[:, 0].mean() + 0.05 * spread)
