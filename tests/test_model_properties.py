# SPDX-License-Identifier: GPL-3.0-or-later

"""What every grown tree must satisfy, whatever its random numbers (the array model's structure)."""

import math
import random
import unittest
from types import SimpleNamespace

import helpers
import numpy as np


def grow(**changes):
    """Grow a tree in the model alone (no Blender objects): (params, curve, grown)."""
    settings = helpers.resolve_preset(changes.pop("preset", "quaking_aspen") + ".py")
    settings.update(changes)
    params = helpers.module("model.params").TreeParams(SimpleNamespace(**settings, leafDupliObj=""))
    curve = helpers.module("model.curve_data").CurveData()
    grower = helpers.module("model.tree").TreeGrower(params, random.Random(params.seed))
    grown = grower.grow(curve, params.scale)
    return params, curve, grown


class TreeStructure(unittest.TestCase):
    def test_one_bone_link_per_spline_and_monotone_levels(self):
        params, curve, grown = grow(levels=4)
        flat = curve.flatten()
        self.assertEqual(len(grown.bone_map), len(flat.sizes))
        self.assertEqual(grown.level_ends[-1], len(flat.sizes))
        self.assertEqual(grown.level_ends, sorted(grown.level_ends))
        self.assertTrue(np.isfinite(flat.co).all() and np.isfinite(flat.left).all() and np.isfinite(flat.right).all())

    def test_parents_come_before_their_children(self):
        _, curve, grown = grow(levels=3)
        bone_name = helpers.module("model.stem").BoneName
        for index, link in enumerate(grown.bone_map):
            if link.bone:
                self.assertLess(bone_name.spline(link.bone), index, link.bone)
            else:
                self.assertLess(index, grown.level_ends[0], "only trunks hang from no bone")

    def test_spline_sizes(self):
        """A root has curveRes + 1 points; a split starts at its split point, so it has fewer."""
        params, curve, grown = grow(levels=3, segSplits=(0.5, 0.5, 0.5, 0.0), baseSplits=2)
        sizes = curve.flatten().sizes
        for index, (link, size) in enumerate(zip(grown.bone_map, sizes, strict=True)):
            segments = params.curve_res[grown.level_of(index)]
            if link.is_split:
                self.assertTrue(2 <= size <= segments, f"split {index}: {size} points")
                parent = helpers.module("model.stem").BoneName.spline(link.bone)
                self.assertEqual(size, sizes[parent] - (link.split_point + 1), "a split keeps its parent's segments")
            else:
                self.assertEqual(size, segments + 1)

    def test_trunk_count(self):
        for trunks in (1, 3):
            _, curve, grown = grow(levels=2, trunks=trunks)
            roots = [i for i, link in enumerate(grown.bone_map) if not link.bone and not link.is_split]
            self.assertEqual(len(roots), trunks)
            flat = curve.flatten()
            bases = flat.co[flat.start[:-1][roots]]
            self.assertTrue((bases[:, 2] == 0).all(), "trunks stand on the ground")

    def test_split_fraction_follows_seg_splits(self):
        """Without Split by Length, a level's stems split with probability segSplits (times the boost rule)."""
        params, curve, grown = grow(
            levels=2, branches=(0, 400, 0, 0), segSplits=(0.0, 0.3, 0.0, 0.0), splitByLen=False, curveRes=(8, 10, 3, 1)
        )
        start, end = grown.level_ends[0], grown.level_ends[1]
        links = [grown.bone_map[i] for i in range(start, end)]
        roots = sum(1 for link in links if not link.is_split)
        splits = sum(1 for link in links if link.is_split)
        # a root stem draws at 9 of its 10 segments (none at the first); the expected count is between
        # 0.3 and 0.3 * 1.33 per draw, and the splits themselves draw again
        draws = roots * 9
        low, high = 0.3 * draws, 0.3 * 1.33 * (draws + splits * 5)
        self.assertGreater(splits, low - 4 * math.sqrt(low), f"{splits} splits of {roots} stems")
        self.assertLess(splits, high + 4 * math.sqrt(high), f"{splits} splits of {roots} stems")

    def test_no_children_sprout_only_tips(self):
        """A negative leaf count (palmate leaves) sprouts at the stem tips only."""
        _, curve, grown = grow(levels=2, leaves=-3, showLeaves=True)
        self.assertTrue(grown.sprouts.is_end.all())
        self.assertEqual(grown.sprouts.count, grown.level_ends[1] - grown.level_ends[0])

    def test_sprouts_sit_on_their_parent_segment(self):
        """Every sprout point lies on the Bezier segment of the parent it names, within the sampling precision."""
        _, curve, grown = grow(levels=2, branches=(0, 60, 0, 0))
        flat = curve.flatten()
        sprouts = grown.sprouts
        bezier = helpers.module("model.rotations").BezierBatch
        t = np.arange(65) / 64
        for i in range(0, sprouts.count, max(1, sprouts.count // 200)):
            spline, point = int(sprouts.parent_spline[i]), int(sprouts.parent_point[i])
            a, b = flat.start[spline] + point, flat.start[spline] + point + 1
            controls = (flat.co[a], flat.right[a], flat.left[b], flat.co[b])
            along = bezier.points(*(np.repeat(c[None], 65, axis=0) for c in controls), t)
            best = np.linalg.norm(along - sprouts.co[i], axis=1).min()
            self.assertLess(best, 0.02, f"sprout {i} is {best:.3f} from its segment")


class RadiusRange(unittest.TestCase):
    """Settings that multiply the radius level by level (ratio power above 1 on branches longer than their parent)
    grew radii past float32: an infinite radius gave the swept bark NaN vertices (fuzz case 56)."""

    def test_radii_stay_within_float32(self):
        _, curve, _ = grow(
            levels=4,
            trunks=3,
            scale=13.2,
            ratio=1.616,
            ratioPower=2.424,
            minRadius=1.11,
            branches=(39, 13, 8, 3),
            length=(1.084, 1.589, 0.9, 0.8),
            lengthV=(0.583, 0.372, 0.339, 0.308),
            curveRes=(6, 1, 4, 2),
        )
        radius = curve.flatten().radius
        self.assertTrue(np.isfinite(radius).all())
        self.assertGreater(radius.max(), 1e6, "the settings do blow the radii up")
        self.assertLessEqual(radius.max(), np.finfo(np.float32).max)


class FailFast(unittest.TestCase):
    def test_stem_rows_need_every_field(self):
        with self.assertRaisesRegex(ValueError, "stem rows need"):
            helpers.module("model.level_grid").StemRows({"key": np.zeros(1, np.uint64)})

    def test_bone_map_from_links_starts_with_a_trunk(self):
        stem = helpers.module("model.stem")
        with self.assertRaisesRegex(ValueError, "trunk"):
            stem.BoneMap.from_links([stem.BoneLink("bone000.000")])
        with self.assertRaisesRegex(ValueError, "trunk"):
            stem.BoneMap.from_links([])
        self.assertEqual(len(stem.BoneMap.from_links([stem.BoneLink(""), stem.BoneLink("bone000.001")])), 2)

    def test_a_tree_needs_a_level(self):
        with self.assertRaisesRegex(ValueError, "at least one level"):
            grow(levels=0)

    def test_non_finite_sprouts_are_an_error(self):
        """Sprouts without a finite position stop the model instead of reaching Blender as NaN."""
        params, curve, grown = grow(levels=1)
        model = helpers.module
        root_key = model("model.randomness").KeyedRandom.root(params.seed)
        grid = model("model.branching").LevelStarter(params, random.Random(1), root_key).trunks(params.scale)
        model("model.growth").LevelGrower(params, params.scale).grow(grid, False)
        grid.co[:, 1:] = np.nan
        with self.assertRaisesRegex(RuntimeError, "not finite"):
            model("model.sprouting").LevelSprouts(params, root_key).plan(grid, grid.flatten(), 0, 0.0)

    def test_pruning_that_does_not_settle_is_an_error(self):
        pruning = helpers.module("model.pruning").LevelPruning
        passes = pruning.MAX_PASSES
        pruning.MAX_PASSES = 0
        self.addCleanup(setattr, pruning, "MAX_PASSES", passes)
        with self.assertRaisesRegex(RuntimeError, "did not settle"):
            grow(preset="callistemon", prune=True)

    def test_a_grown_level_cannot_be_subset(self):
        params, _, _ = grow(levels=1)
        model = helpers.module
        root_key = model("model.randomness").KeyedRandom.root(params.seed)
        grid = model("model.branching").LevelStarter(params, random.Random(1), root_key).trunks(params.scale)
        self.assertEqual(grid.subset(np.array([0])).rows, 1)
        model("model.growth").LevelGrower(params, params.scale).grow(grid, False)
        if grid.stems.is_split.any():
            with self.assertRaisesRegex(RuntimeError, "before the level grows"):
                grid.subset(np.array([0]))

    def test_unknown_shapes(self):
        geometry = helpers.module("model.geometry")
        with self.assertRaisesRegex(ValueError, "crown shape"):
            geometry.CrownShape.ratios(99, np.array([0.5]))
        with self.assertRaisesRegex(ValueError, "crown shape"):
            geometry.CrownShape.ratio(99, 0.5)
        with self.assertRaisesRegex(ValueError, "leaf shape"):
            helpers.module("model.leaves").LeafShape.template("star")


class CrownShapes(unittest.TestCase):
    def test_array_ratios_equal_scalar_ratios(self):
        geometry = helpers.module("model.geometry")
        ratios = np.linspace(0.0, 1.0, 41)
        custom = (0.3, 1.0, 0.4, 0.6)
        for shape in (0, 1, 2, 3, 4, 5, 6, 7, 8, 10):
            ours = geometry.CrownShape.ratios(shape, ratios, custom)
            for r, value in zip(ratios.tolist(), ours.tolist(), strict=True):
                self.assertAlmostEqual(
                    value, geometry.CrownShape.ratio(shape, r, custom), places=9, msg=f"shape {shape} at {r}"
                )

    def test_angle_means(self):
        geometry = helpers.module("model.geometry")
        a1 = np.array([0.1, 3.0, -2.0])
        a2 = np.array([1.5, -3.0, 2.5])
        ours = geometry.Angles.means(a1, a2, 0.3)
        for x, y, value in zip(a1.tolist(), a2.tolist(), ours.tolist(), strict=True):
            # the per-stem add-on's mean of two angles through their unit vectors
            sx, sy = math.sin(x) + (math.sin(y) - math.sin(x)) * 0.3, math.cos(x) + (math.cos(y) - math.cos(x)) * 0.3
            self.assertAlmostEqual(value, math.atan2(sx, sy), places=9)


class PrunedTrees(unittest.TestCase):
    """Pruning on the grid: the kept stems fit the envelope, the removed ones are stubs without sprouts."""

    def test_kept_stems_end_near_or_inside_the_envelope(self):
        """The search settles on an interval midpoint and the envelope is not monotone along a stem, so a few ends
        overshoot a little: measured 13-18 % outside, worst 1.13-1.31 x the limit, for this search and the per-stem
        search before it. Without pruning most ends are far outside."""
        for preset, changes in (("callistemon", {}), ("quaking_aspen", {"pruneWidth": 0.25})):
            with self.subTest(preset=preset):
                params, curve, grown = grow(preset=preset, prune=True, pruneRatio=1.0, **changes)
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
            level = grown.level_of(i)
            if sizes[i] < 2 or (level == 0 and end[2] < params.prune_base_clamped * scale):
                continue
            ratio = (scale - end[2]) / (scale * max(1 - params.prune_base_clamped, 1e-6))
            limit = params.prune_width * params.envelope(ratio)
            if limit > 0:
                over.append(np.hypot(end[0], end[1]) / scale / limit)
        return np.array(over)

    def test_removed_stems_are_stubs_without_sprouts(self):
        params, curve, grown = grow(preset="quaking_aspen", prune=True, pruneRatio=1.0, pruneWidth=0.25)
        flat = curve.flatten()
        removed = [i for i in range(1, len(flat.sizes)) if flat.sizes[i] == 1]
        self.assertGreater(len(removed), 10)
        bone_name = helpers.module("model.stem").BoneName
        parents = {bone_name.spline(link.bone) for link in grown.bone_map if link.bone}
        self.assertFalse(set(removed) & parents, "no stem hangs from a removed stem")
        self.assertFalse(set(removed) & set(grown.sprouts.parent_spline.tolist()), "no leaf sprouts on a removed stem")
        for i in removed:
            point = curve.splines[i].bezier_points[0]
            self.assertEqual((point.handle_left_type, point.handle_right_type), ("FREE", "FREE"))
            # the stub's handles are its start and its start direction: never uninitialized memory
            self.assertEqual(tuple(point.handle_left), (0.0, 0.0, 0.0))
            self.assertLess((point.handle_right - point.co).length, 1.001)
        self.assertEqual(len(grown.bone_map), len(flat.sizes))

    def test_two_growths_are_identical(self):
        """The same settings give the same arrays, bit for bit, every time."""
        _, first, _ = grow(preset="cambridge_oak")
        _, second, _ = grow(preset="cambridge_oak")
        a, b = first.flatten(), second.flatten()
        for name in ("co", "left", "right", "radius", "h1", "h2", "start"):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name), err_msg=name)

    def test_partial_ratio_keeps_every_stem(self):
        params, curve, grown = grow(preset="quaking_aspen", prune=True, pruneRatio=0.5, pruneWidth=0.25)
        self.assertTrue((curve.flatten().sizes >= 2).all())
