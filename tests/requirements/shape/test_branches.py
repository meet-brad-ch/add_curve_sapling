# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree shape: branches (the requirements each class or test names)."""

import math
import unittest
import unittest.mock
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import bpy
import numpy as np
from support.addon import Addon
from support.crown import Crown
from support.evaluated import Evaluated
from support.foliage import Foliage
from support.mesh_counts import MeshCounts
from support.model import Model
from support.node_trees import LegacyBevel, NodeTrees
from support.scene import Scene
from support.verifies import Verifies


@dataclass(frozen=True)
class HelixLevel:
    """A tree whose one level grows helixes: the model, its flat curve, the level's spline rows, and the points of
    that level's stems with three or more points."""

    model: Any
    flat: Any
    rows: range
    stems: list


@dataclass(frozen=True)
class Turns:
    """The turn angles between the segments of every level-1 stem (degrees), and the level's segment count."""

    angles: np.ndarray
    segments: int


class HelixStems(unittest.TestCase):
    """A helix level grows each segment as half a turn of a helix around the stem's start direction."""

    HELIX_ANGLE = 60.0

    def helix(self, level, **changes):
        """A tree whose `level` grows helixes, and that level's stems with three or more points."""
        helix = [False] * 4
        helix[level] = True
        curve_v = [20.0, 50.0, 75.0, 0.0]
        curve_v[level] = self.HELIX_ANGLE
        model = Model.grow_preset(helix=helix, curveV=curve_v, **changes)
        flat = model.curve.flatten()
        ends = [0, *model.grown.level_ends]
        rows = range(ends[level], ends[level + 1])
        points = [flat.co[flat.start[i] : flat.start[i + 1]].astype(np.float64) for i in rows]
        stems = [p for p in points if len(p) >= 3]
        return HelixLevel(model=model, flat=flat, rows=rows, stems=stems)

    def assert_helix(self, co):
        """Points on a helix: every second point one pitch further along the same axis, every chord as long, and
        the radius to pitch ratio of the helix angle within the random factors."""
        np.testing.assert_allclose(co[2:] - co[:-2], np.broadcast_to(co[2] - co[0], co[2:].shape), atol=1e-4)
        chords = np.linalg.norm(np.diff(co, axis=0), axis=1)
        np.testing.assert_allclose(chords, chords[0], rtol=1e-4)
        pitch = np.linalg.norm(co[2] - co[0])
        radius = math.sqrt(max(chords[0] ** 2 - pitch**2 / 4, 0.0)) / 2
        nominal = 3 / (16 * math.tan(math.radians(90 - self.HELIX_ANGLE)))
        self.assertTrue(0.8 * nominal - 1e-4 <= radius / pitch <= 1.2 * nominal + 1e-4, radius / pitch)

    @Verifies("SWR-0062")
    def test_points_lie_on_a_helix(self):
        stems = self.helix(0, levels=1, curveRes=(12, 5, 3, 1)).stems
        self.assertEqual(len(stems), 1)
        self.assert_helix(stems[0])

    @Verifies("SWR-0062")
    def test_helix_points_have_free_handles(self):
        level = self.helix(1, levels=2)
        flat = level.flat
        rows = level.rows
        free = Addon.module("model.curve_data").HandleType.FREE
        at = np.concatenate([np.arange(flat.start[i], flat.start[i + 1]) for i in rows])
        self.assertTrue((flat.h1[at] == free).all() and (flat.h2[at] == free).all())
        trunk = np.arange(flat.start[0] + 1, flat.start[1])
        self.assertFalse((flat.h1[trunk] == free).any())

    @Verifies("SWR-0062")
    def test_helix_off_draws_nothing(self):
        draw = Addon.module("model.randomness").Draw.HELIX_PITCH
        self.assertNotIn(draw, BendVariation().draws(levels=2))
        self.assertIn(draw, BendVariation().draws(levels=2, helix=(False, True, False, False)))

    @Verifies("SWR-0062")
    def test_helix_stems_do_not_split(self):
        level = self.helix(1, levels=2, segSplits=(0.0, 2.0, 0.0, 0.0))
        self.assertFalse(any(level.model.grown.bone_map[i].is_split for i in level.rows))
        for co in level.stems:
            self.assert_helix(co)

    @Verifies("SWR-0062")
    def test_a_pruned_helix_stays_a_helix(self):
        level = self.helix(1, preset="callistemon", prune=True)
        self.assertTrue(level.model.params.prune and level.stems)
        for co in level.stems:
            self.assert_helix(co)

    @Verifies("SWR-0063")
    def test_helix_angle_of_90_degrees_is_an_error(self):
        error = Addon.module("model.params").InvalidSettingError
        with self.assertRaisesRegex(error, "Helix on level 2: .* It is 90 degrees"):
            Model.grow_preset(levels=2, helix=(False, True, False, False), curveV=(20.0, 90.0, 0.0, 0.0))
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, helix=(False, True, False, False), curveV=(20.0, -95.0, 0.0, 0.0))
        with self.assertRaisesRegex(RuntimeError, "Helix on level 2: .* It is 95 degrees"):
            Scene.generate(settings)


@Verifies("SWR-0062")
class HelixWind(unittest.TestCase):
    """The node wind turns a helix's FREE handles with their joint: Set Position alone moves them by their point's
    offset without turning them, which bends the bark at every point."""

    @staticmethod
    def offsets(attributes, free):
        """Each FREE point's right handle minus the point."""
        count = len(attributes["position"].data)
        co, right = np.zeros(count * 3), np.zeros(count * 3)
        attributes["position"].data.foreach_get("vector", co)
        attributes["handle_right"].data.foreach_get("vector", right)
        return (right - co).reshape(-1, 3)[free]

    def test_free_handles_turn_with_their_joint(self):
        settings = NodeTrees.settings(
            windAnim=True, fastPreview=True, helix=(False, True, False, False), curveV=(20.0, 40.0, 75.0, 0.0)
        )
        self.assertEqual(Scene.generate(settings), {"FINISHED"})
        source = Evaluated.tree_curves().data
        types = np.zeros(len(source.attributes["position"].data), dtype=np.int8)
        source.attributes["handle_type_right"].data.foreach_get("value", types)
        free = types == Addon.module("model.curve_data").HandleType.FREE
        self.assertGreater(free.sum(), 10)
        rest = self.offsets(source.attributes, free)
        bpy.context.scene.frame_set(17)
        root = bpy.data.objects["tree"].evaluated_get(bpy.context.evaluated_depsgraph_get())
        geometry = root.evaluated_geometry()  # held: the curves are freed with it
        moved = self.offsets(geometry.curves.attributes, free)
        np.testing.assert_allclose(np.linalg.norm(moved, axis=1), np.linalg.norm(rest, axis=1), rtol=1e-4)
        cosine = (moved * rest).sum(axis=1) / (np.linalg.norm(moved, axis=1) * np.linalg.norm(rest, axis=1))
        self.assertLess(cosine.min(), np.cos(np.radians(0.1)), "the handles turned")


@Verifies("SWR-0071")
class BendVariation(unittest.TestCase):
    """Bend Variation turns each segment of a level sideways by a random part of the level's maximum."""

    STRAIGHT = {
        "levels": 2,
        "curve": (0.0, 0.0, 0.0, 0.0),
        "curveV": (0.0, 0.0, 0.0, 0.0),
        "curveBack": (0.0, 0.0, 0.0, 0.0),
        "attractUp": (0.0, 0.0, 0.0, 0.0),
        "segSplits": (0.0, 0.0, 0.0, 0.0),
    }

    def draws(self, **changes):
        """The draw ids the growth asks KeyedRandom.between for."""
        randomness = Addon.module("model.randomness").KeyedRandom
        original = randomness.between
        seen = set()

        def spy(keys, step, draw, low, high):
            seen.add(draw)
            return original(keys, step, draw, low, high)

        with unittest.mock.patch.object(randomness, "between", side_effect=spy):
            Model.grow_preset(**changes)
        return seen

    def turns(self, bend):
        """Every level-1 stem's turn angles between its segments, in degrees, and the level's segment count."""
        model = Model.grow_preset(**self.STRAIGHT, bendV=(0.0, bend, 0.0, 0.0))
        flat = model.curve.flatten()
        ends = model.grown.level_ends
        turns = []
        for spline in range(ends[0], ends[1]):
            co = flat.co[flat.start[spline] : flat.start[spline + 1]].astype(np.float64)
            d = np.diff(co, axis=0)
            d /= np.linalg.norm(d, axis=1, keepdims=True)
            turns.append(np.degrees(np.arccos(np.clip((d[:-1] * d[1:]).sum(axis=1), -1, 1))))
        return Turns(angles=np.concatenate(turns), segments=model.params.curve_res[1])

    def test_bend_off_draws_nothing(self):
        bend = Addon.module("model.randomness").Draw.BEND
        self.assertNotIn(bend, self.draws(levels=2, bendV=(0.0, 0.0, 0.0, 0.0)))
        self.assertIn(bend, self.draws(levels=2, bendV=(0.0, 30.0, 0.0, 0.0)))

    def test_bend_turns_level_stems_sideways(self):
        straight = self.turns(0.0).angles
        self.assertLess(straight.max(), 1e-3)
        bent = self.turns(60.0)
        self.assertGreater(bent.angles.max(), 1.0)
        self.assertLessEqual(bent.angles.max(), 60.0 / bent.segments + 1e-3)

    def test_split_step_does_not_bend(self):
        growth = Addon.module("model.growth")
        stems = SimpleNamespace(roll=np.array([0.2, 0.2]))
        split = growth.SplitAngles(np.full(2, 0.3), np.full(2, 0.1), np.full(2, 0.5))
        has_split = np.array([True, False])

        def rotations(bend):
            curve = growth.CurveAngles(np.full(2, 0.4), np.full(2, 0.05), bend)
            return growth.LevelGrower._local_rotations(stems, growth.StepAngles(curve, split), 1, has_split)

        unbent, bent = rotations(None), rotations(np.full(2, 0.25))
        np.testing.assert_array_equal(bent[0], unbent[0])
        self.assertGreater(np.abs(bent[1] - unbent[1]).max(), 0.1)


@Verifies("SWR-0072")
class PalmSettings(unittest.TestCase):
    """Count Above Base, Leaves Above Base and Fan Angles: tree-gen's palm, fan palm and bamboo need them."""

    PALM = {"levels": 2, "baseSize": 0.95, "branches": (0, 25, 0, 0), "showLeaves": False}

    @staticmethod
    def first_level(model):
        ends = model.grown.level_ends
        return [i for i in range(ends[0], ends[1]) if not model.grown.bone_map[i].is_split]

    def test_count_above_base_fills_the_crown(self):
        self.assertLessEqual(len(self.first_level(Model.grow_preset(**self.PALM))), 2)
        crown = Model.grow_preset(**self.PALM, countAboveBase=True)
        stems = self.first_level(crown)
        self.assertGreaterEqual(len(stems), 20)
        flat = crown.curve.flatten()
        trunk_top = flat.co[flat.start[0] : flat.start[1], 2].max()
        heights = np.array([flat.co[flat.start[i], 2] for i in stems]) / trunk_top
        self.assertGreater(heights.min(), 0.9)

    def test_count_above_base_leaves_the_leaf_count(self):
        plain = Foliage.grow(baseSize=0.4).leaves
        counted = Foliage.grow(baseSize=0.4, countAboveBase=True).leaves
        per_stem = plain.count / len(set(plain.parent_spline.tolist()))
        counted_per_stem = counted.count / len(set(counted.parent_spline.tolist()))
        self.assertAlmostEqual(counted_per_stem, per_stem, delta=0.15 * per_stem)


@Verifies("SWR-0074")
class RootSweep(unittest.TestCase):
    """The root is a mesh: the bark it sweeps has the old bevel's vertices and faces."""

    def test_root_is_a_mesh_that_draws_the_bark(self):
        self.assertEqual(Scene.generate(NodeTrees.settings()), {"FINISHED"})
        root = Scene.active_object()
        self.assertEqual((root.name, root.type), ("tree", "MESH"))
        self.assertEqual([(m.type, m.name) for m in root.modifiers], [("NODES", "Sapling Tree")])
        source = Evaluated.tree_curves()
        self.assertEqual((source.type, source.parent), ("CURVES", root))
        self.assertTrue(source.hide_viewport and source.hide_render)
        counts = NodeTrees.counts("tree")
        self.assertGreater(counts.polygons, 1000)
        self.assertGreater(counts.vertices, counts.polygons)

    def test_sweep_counts_equal_the_old_bevel(self):
        """Blender's own bevel of a legacy curve with the same points is the reference."""
        for changes in ({}, {"bevelRes": 3, "resU": 2}, {"bevel": False}, {"prune": True}):
            with self.subTest(changes=changes):
                settings = NodeTrees.settings(**changes)
                self.assertEqual(Scene.generate(settings), {"FINISHED"})
                self.assertEqual(NodeTrees.counts("tree"), LegacyBevel.counts(settings))

    def test_inputs_stay_live(self):
        self.assertEqual(Scene.generate(NodeTrees.settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        before = NodeTrees.counts("tree")
        NodeTrees.set_input(root, "Bevel Resolution", 4)
        after = NodeTrees.counts("tree")
        self.assertGreater(after.vertices, before.vertices)
        NodeTrees.set_input(root, "Fill Caps", True)
        self.assertGreater(NodeTrees.counts("tree").polygons, after.polygons)

    def test_apply_gives_the_mesh(self):
        self.assertEqual(Scene.generate(NodeTrees.settings()), {"FINISHED"})
        root = bpy.data.objects["tree"]
        counts = NodeTrees.counts("tree")
        with bpy.context.temp_override(object=root, active_object=root):
            self.assertEqual(bpy.ops.object.modifier_apply(modifier="Sapling Tree"), {"FINISHED"})
        mesh = root.data
        self.assertEqual(MeshCounts.of(mesh), counts)
        self.assertEqual([m.name for m in mesh.materials], ["Sapling Bark"])


@Verifies("SWR-0069")
class BranchBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        settings = Addon.resolve_preset("cambridge_oak.py")
        # no splits: every spline is one stem, starting where it sprouts (a split piece starts mid-stem)
        settings.update(levels=3, seed=5, prune=False, baseSplits=0, segSplits=[0.0, 0.0, 0.0, 0.0])
        cls.base = settings
        cls.plain = Crown.spray_starts(settings)

    def test_zero_changes_nothing(self):
        same = Crown.spray_starts(dict(self.base, branchBase=[0.0, 0.0, 0.0, 0.0]))
        np.testing.assert_array_equal(same, self.plain)

    def test_the_sprays_grow_on_the_limbs_outer_part(self):
        outer = Crown.spray_starts(dict(self.base, branchBase=[0.0, 0.6, 0.0, 0.0]))
        plain_reach = np.hypot(self.plain[:, 0], self.plain[:, 1])
        outer_reach = np.hypot(outer[:, 0], outer[:, 1])
        # the sprays start further out from the trunk: none on the limbs' bare inner 60 %
        self.assertGreater(np.percentile(outer_reach, 10), np.percentile(plain_reach, 10) * 1.5)
