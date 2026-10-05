# SPDX-License-Identifier: GPL-3.0-or-later

"""What every grown tree must satisfy, whatever its random numbers (the array model's structure)."""

import math
import random
import unittest
from types import SimpleNamespace

import helpers
import numpy as np
from mathutils import Vector


def grow(**changes):
    """Grow a tree in the model alone (no Blender objects): (params, curve, grown)."""
    settings = helpers.resolve_preset(changes.pop("preset", "quaking_aspen") + ".py")
    settings.update(changes)
    params = helpers.module("model.params").TreeParams(SimpleNamespace(**settings, leafDupliObj=""))
    curve = helpers.module("model.curve_data").CurveData()
    grower = helpers.module("model.tree").TreeGrower(params, random.Random(params.seed))
    grown = grower.grow(curve, curve.__class__() if params.prune else None, params.scale)
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
        bezier = helpers.module("model.geometry").BezierSegment
        for i in range(0, sprouts.count, max(1, sprouts.count // 200)):
            spline, point = int(sprouts.parent_spline[i]), int(sprouts.parent_point[i])
            a, b = flat.start[spline] + point, flat.start[spline] + point + 1
            segment = bezier(*(Vector(c.tolist()) for c in (flat.co[a], flat.right[a], flat.left[b], flat.co[b])))
            target = Vector(sprouts.co[i].tolist())
            best = min((segment.point(t / 64) - target).length for t in range(65))
            self.assertLess(best, 0.02, f"sprout {i} is {best:.3f} from its segment")


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

    def test_unknown_shapes(self):
        geometry = helpers.module("model.geometry")
        with self.assertRaisesRegex(ValueError, "crown shape"):
            geometry.CrownShape.ratios(99, np.array([0.5]))
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
            self.assertAlmostEqual(value, geometry.Angles.mean(x, y, 0.3), places=9)


class PrunedPathStillGrows(unittest.TestCase):
    def test_pruned_tree_gives_the_same_structures(self):
        """With pruning, the per-stem path still produces the same kinds of results."""
        _, curve, grown = grow(preset="callistemon", prune=True)
        self.assertEqual(len(grown.bone_map), len(curve.splines))
        self.assertGreater(grown.sprouts.count, 10)
        self.assertEqual(len(grown.sprouts.parent_bones()), grown.sprouts.count)
