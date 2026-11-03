# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of source/model: tree structure."""

import math
import random
import unittest
import unittest.mock
from types import SimpleNamespace

import numpy as np
from support.addon import Addon
from support.model import Model
from support.scene import Scene


class TreeStructure(unittest.TestCase):
    def test_one_bone_link_per_spline_and_monotone_levels(self):
        model = Model.grow_preset(levels=4)
        curve = model.curve
        grown = model.grown
        flat = curve.flatten()
        self.assertEqual(len(grown.bone_map), len(flat.sizes))
        self.assertEqual(grown.level_ends[-1], len(flat.sizes))
        self.assertEqual(grown.level_ends, sorted(grown.level_ends))
        self.assertTrue(np.isfinite(flat.co).all() and np.isfinite(flat.left).all() and np.isfinite(flat.right).all())

    def test_parents_come_before_their_children(self):
        model = Model.grow_preset(levels=3)
        grown = model.grown
        bone_name = Addon.module("model.stem").BoneName
        for index, link in enumerate(grown.bone_map):
            if link.bone:
                self.assertLess(bone_name.spline(link.bone), index, link.bone)
            else:
                self.assertLess(index, grown.level_ends[0], "only trunks hang from no bone")

    def test_spline_sizes(self):
        """A root has curveRes + 1 points; a split starts at its split point, so it has fewer."""
        model = Model.grow_preset(levels=3, segSplits=(0.5, 0.5, 0.5, 0.0), baseSplits=2)
        params = model.params
        curve = model.curve
        grown = model.grown
        sizes = curve.flatten().sizes
        for index, (link, size) in enumerate(zip(grown.bone_map, sizes, strict=True)):
            segments = params.curve_res[Model.level_index(grown, index)]
            if link.is_split:
                self.assertTrue(2 <= size <= segments, f"split {index}: {size} points")
                parent = Addon.module("model.stem").BoneName.spline(link.bone)
                self.assertEqual(size, sizes[parent] - (link.split_point + 1), "a split keeps its parent's segments")
            else:
                self.assertEqual(size, segments + 1)

    def test_trunk_count(self):
        for trunks in (1, 3):
            model = Model.grow_preset(levels=2, trunks=trunks)
            curve = model.curve
            grown = model.grown
            roots = [i for i, link in enumerate(grown.bone_map) if not link.bone and not link.is_split]
            self.assertEqual(len(roots), trunks)
            flat = curve.flatten()
            bases = flat.co[flat.start[:-1][roots]]
            self.assertTrue((bases[:, 2] == 0).all(), "trunks stand on the ground")

    def test_split_fraction_follows_seg_splits(self):
        """Without Split by Length, a level's stems split with probability segSplits (times the boost rule)."""
        model = Model.grow_preset(
            levels=2, branches=(0, 400, 0, 0), segSplits=(0.0, 0.3, 0.0, 0.0), splitByLen=False, curveRes=(8, 10, 3, 1)
        )
        grown = model.grown
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

    def test_sprouts_sit_on_their_parent_segment(self):
        """Every sprout point lies on the Bezier segment of the parent it names, within the sampling precision."""
        model = Model.grow_preset(levels=2, branches=(0, 60, 0, 0))
        curve = model.curve
        grown = model.grown
        flat = curve.flatten()
        sprouts = grown.sprouts
        bezier = Addon.module("model.rotations").BezierBatch
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
        model = Model.grow_preset(
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
        curve = model.curve
        radius = curve.flatten().radius
        self.assertTrue(np.isfinite(radius).all())
        self.assertGreater(radius.max(), 1e6, "the settings do blow the radii up")
        self.assertLessEqual(radius.max(), np.finfo(np.float32).max)


class FailFast(unittest.TestCase):
    def test_stem_rows_need_every_field(self):
        with self.assertRaisesRegex(TypeError, "missing"):
            Addon.module("model.level_grid").StemRows(key=np.zeros(1, np.uint64))

    def test_bone_map_starts_with_a_trunk(self):
        stem = Addon.module("model.stem")
        with self.assertRaisesRegex(ValueError, "trunk"):
            stem.BoneMap([stem.BoneLink("bone000.000")])
        with self.assertRaisesRegex(ValueError, "trunk"):
            stem.BoneMap([])
        self.assertEqual(len(stem.BoneMap([stem.BoneLink(""), stem.BoneLink("bone000.001")])), 2)

    def test_a_tree_needs_a_level(self):
        with self.assertRaisesRegex(ValueError, "at least one level"):
            Model.grow_preset(levels=0)

    def test_non_finite_sprouts_are_an_error(self):
        """Sprouts without a finite position stop the model instead of reaching Blender as NaN."""
        params = Model.grow_preset(levels=1).params
        module = Addon.module
        root_key = module("model.randomness").KeyedRandom.root(params.seed)
        grid = module("model.branching").LevelStarter(params, random.Random(1), root_key).trunks(params.scale)
        module("model.growth").LevelGrower(params, params.scale).grow(grid, False)
        grid.co[:, 1:] = np.nan
        with self.assertRaisesRegex(RuntimeError, "not finite"):
            module("model.sprouting").LevelSprouts(params, root_key).plan(grid, grid.flatten(), 0, 0.0, 1.0)

    def test_pruning_that_does_not_settle_is_an_error(self):
        pruning = Addon.module("model.pruning").LevelPruning
        passes = pruning.MAX_PASSES
        pruning.MAX_PASSES = 0
        self.addCleanup(setattr, pruning, "MAX_PASSES", passes)
        with self.assertRaisesRegex(RuntimeError, "did not settle"):
            Model.grow_preset(preset="callistemon", prune=True)

    def test_a_grown_level_cannot_be_subset(self):
        params = Model.grow_preset(levels=1, baseSplits=2).params  # Base Splits split the trunk at its first step
        module = Addon.module
        root_key = module("model.randomness").KeyedRandom.root(params.seed)
        grid = module("model.branching").LevelStarter(params, random.Random(1), root_key).trunks(params.scale)
        self.assertEqual(grid.subset(np.array([0])).rows, 1)
        module("model.growth").LevelGrower(params, params.scale).grow(grid, False)
        self.assertTrue(grid.stems.is_split.any())
        with self.assertRaisesRegex(RuntimeError, "before the level grows"):
            grid.subset(np.array([0]))

    def test_unknown_shapes(self):
        geometry = Addon.module("model.geometry")
        with self.assertRaisesRegex(ValueError, "crown shape"):
            geometry.CrownShape.ratios(99, np.array([0.5]))
        with self.assertRaisesRegex(ValueError, "crown shape"):
            geometry.CrownShape.ratio(99, 0.5)
        with self.assertRaisesRegex(ValueError, "leaf shape"):
            Addon.module("model.leaves").LeafShape.template("star")


class CrownShapes(unittest.TestCase):
    @staticmethod
    def reference(shape, r, custom):
        """The Weber-Penn shape ratios as the per-stem add-on computed them, one value at a time."""
        flame = 0.05 + 0.95 * r / 0.7 if r <= 0.7 else 0.05 + 0.95 * (1.0 - r) / 0.3
        tend_flame = 0.5 + 0.5 * r / 0.7 if r <= 0.7 else 0.5 + 0.5 * (1.0 - r) / 0.3
        shapes = {
            0: 0.05 + 0.95 * r,
            1: 0.2 + 0.8 * math.sin(math.pi * r),
            2: 0.2 + 0.8 * math.sin(0.5 * math.pi * r),
            3: 1.0,
            4: 0.5 + 0.5 * r,
            5: flame,
            6: 1.0 - 0.8 * r,
            7: tend_flame,
            10: 0.5 + 0.5 * (1 - r),
        }
        if shape != 8:
            return shapes[shape]
        rr = 1 - r
        if rr == 1:
            return custom[3]
        if rr >= custom[2]:
            pos = (rr - custom[2]) / (1 - custom[2])
            return pos * pos * (custom[3] - custom[1]) + custom[1]
        pos = 1 - (1 - rr / custom[2]) * (1 - rr / custom[2])
        return pos * (custom[1] - custom[0]) + custom[0]

    def test_ratios_equal_the_per_stem_formulas(self):
        geometry = Addon.module("model.geometry")
        ratios = np.linspace(0.0, 1.0, 41)
        custom = [0.3, 1.0, 0.4, 0.6]
        for shape in (0, 1, 2, 3, 4, 5, 6, 7, 8, 10):
            ours = geometry.CrownShape.ratios(shape, ratios, custom)
            for r, value in zip(ratios.tolist(), ours.tolist(), strict=True):
                self.assertAlmostEqual(value, self.reference(shape, r, custom), places=9, msg=f"shape {shape} at {r}")
                self.assertEqual(geometry.CrownShape.ratio(shape, r, custom), value)

    def test_angle_means(self):
        geometry = Addon.module("model.geometry")
        a1 = np.array([0.1, 3.0, -2.0])
        a2 = np.array([1.5, -3.0, 2.5])
        ours = geometry.Angles.means(a1, a2, 0.3)
        for x, y, value in zip(a1.tolist(), a2.tolist(), ours.tolist(), strict=True):
            # the per-stem add-on's mean of two angles through their unit vectors
            sx, sy = math.sin(x) + (math.sin(y) - math.sin(x)) * 0.3, math.cos(x) + (math.cos(y) - math.cos(x)) * 0.3
            self.assertAlmostEqual(value, math.atan2(sx, sy), places=9)


class TrunkHeightOne(unittest.TestCase):
    """Trunk Height 1 leaves the whole trunk bare: the first level's branches continue from its tip only."""

    def test_a_bare_trunk_grows_from_its_tip(self):
        model = Model.grow_preset(levels=2, baseSize=1.0)
        flat = model.curve.flatten()
        self.assertTrue(np.isfinite(flat.co).all())
        first_level = range(model.grown.level_ends[0], model.grown.level_ends[1])
        self.assertTrue(first_level)
        self.assertTrue(
            all(model.grown.bone_map[i].is_end for i in first_level if not model.grown.bone_map[i].is_split)
        )


class PlainParams(unittest.TestCase):
    """The parameters hold plain Python values: the operator's property arrays die with the operator, and numpy
    reading one later crashed Blender (EXCEPTION_ACCESS_VIOLATION, 2026-10-04)."""

    PLAIN = (int, float, bool, str)

    def assert_plain(self, params):
        for name, value in vars(params).items():
            with self.subTest(name=name):
                if isinstance(value, list):
                    not_numbers = [v for v in value if not isinstance(v, int | float)]
                    self.assertEqual(not_numbers, [], f"{name}: {value!r}")
                elif not isinstance(value, Addon.module("model.params").PlainParams):
                    self.assertTrue(isinstance(value, self.PLAIN) or hasattr(value, "__dataclass_fields__"), name)

    def test_params_after_the_operator_are_plain(self):
        generator = Addon.module("generator").TreeGenerator
        original = generator.__init__
        captured = []

        def recording(generator_self, *args):
            original(generator_self, *args)
            captured.append(generator_self)

        generator.__init__ = recording
        self.addCleanup(setattr, generator, "__init__", original)
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(useRig=True, windAnim=True, showLeaves=True)
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        made = captured[-1]
        for params in (made.params, made.wind_params, made.build_params):
            self.assert_plain(params)
        np.asarray(made.params.branches)  # what crashed when it was the operator's array

    def test_a_changed_source_leaves_the_params_unchanged(self):
        settings = Addon.resolve_preset("quaking_aspen.py")
        source = SimpleNamespace(**settings, leafDupliObj="")
        params = Addon.module("model.params").TreeParams(source)
        lengths = list(params.length)
        branches = list(params.branches)
        steps = list(params.bone_step)
        source.length[0] = 99.0
        source.branches.clear()
        source.jointStep[1] = 7
        self.assertEqual(params.length, lengths)
        self.assertEqual(params.branches, branches)
        self.assertEqual(params.bone_step, steps)


class JointParents(unittest.TestCase):
    """The rig's bones hang where the model's bone map says: a curve's first joint hangs from the joint named by
    its bone link."""

    def test_first_parents_are_the_bone_links(self):
        cases = [
            {"levels": 3, "branches": (0, 30, 10, 0)},
            {"levels": 3, "branches": (0, 30, 10, 0), "jointStep": (2, 3, 2, 1), "prune": True},
            {"levels": 4, "branches": (0, 12, 6, 4), "jointLevels": 0, "segSplits": (0.3, 0.3, 0.2, 0.0)},
        ]
        for case in cases:
            with self.subTest(case=case):
                settings = Addon.resolve_preset("quaking_aspen.py")
                settings.update(case)
                model = Model.grow(settings)
                joints = Model.joints(settings, model)
                names = joints.names()
                parents = joints.first_parent()
                linked = np.flatnonzero(joints.eligible & (joints.link_spline >= 0))
                self.assertGreater(len(linked), 10)
                for c in linked.tolist():
                    self.assertEqual(names[parents[c]], model.grown.bone_map[c].bone, f"curve {c}")
