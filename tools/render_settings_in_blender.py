# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/render_settings.py: the pictures of the help pages. Each picture is a strip: one
preset at three values of one setting, side by side at true scale, each value written under its tree, with the look
of the presets page (tools/render_presets_in_blender.py) and the 1.8 m figure at the left.

Argument after `--`: the out folder. Each strip is written as <strip name>.jpg and prints "WROTE <file>".
"""

import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import bpy
from mathutils import Euler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)
from render_listing_in_blender import ListingMedia, Media  # noqa: E402  (as above)
from render_presets_in_blender import Bounds, Silhouette  # noqa: E402  (as above)


@dataclass(frozen=True, slots=True)
class Variant:
    """One tree of a strip: the label written under it and the settings it changes."""

    label: str
    changes: dict[str, Any]


@dataclass(frozen=True, slots=True)
class Strip:
    """One picture: a preset with `base` changes, grown once per variant."""

    name: str  # the file name without .jpg
    preset: str
    variants: tuple[Variant, ...]
    base: dict[str, Any] = field(default_factory=dict)


class Strips:
    """The pictures of the help pages, by panel page. A per-level setting lists its four values, the trunk first."""

    ALL = (
        # Geometry
        Strip("shape", "acer", (
            Variant("Shape: Conical", {"shape": "0"}),
            Variant("Shape: Spherical", {"shape": "1"}),
            Variant("Shape: Inverse Conical", {"shape": "6"}),
        )),
        Strip("branch_distribution", "acer", (
            Variant("Branch Distribution 0.5", {"branchDist": 0.5}),
            Variant("Branch Distribution 1.0", {"branchDist": 1.0}),
            Variant("Branch Distribution 2.5", {"branchDist": 2.5}),
        )),
        Strip("branch_rings", "small_pine", (
            Variant("Branch Rings 0", {"nrings": 0}),
            Variant("Branch Rings 4", {"nrings": 4}),
            Variant("Branch Rings 8", {"nrings": 8}),
        )),
        # Branch Radius
        Strip("ratio", "acer", (
            Variant("Ratio 0.010", {"ratio": 0.01}),
            Variant("Ratio 0.020", {"ratio": 0.02}),
            Variant("Ratio 0.040", {"ratio": 0.04}),
        ), {"showLeaves": False}),
        # Branch Splitting
        Strip("levels", "acer", (
            Variant("Levels 1", {"levels": 1}),
            Variant("Levels 2", {"levels": 2}),
            Variant("Levels 3", {"levels": 3}),
        ), {"showLeaves": False}),
        Strip("trunks", "acer", (
            Variant("Trunks 1", {"trunks": 1}),
            Variant("Trunks 3", {"trunks": 3}),
            Variant("Trunks 5", {"trunks": 5}),
        )),
        Strip("base_splits", "acer", (
            Variant("Base Splits 0", {"baseSplits": 0}),
            Variant("Base Splits 2", {"baseSplits": 2}),
            Variant("Base Splits 4", {"baseSplits": 4}),
        ), {"showLeaves": False}),
        Strip("trunk_height", "acer", (
            Variant("Trunk Height 0.1", {"baseSize": 0.1}),
            Variant("Trunk Height 0.4", {"baseSize": 0.4}),
            Variant("Trunk Height 0.7", {"baseSize": 0.7}),
        )),
        Strip("segment_splits", "acer", (
            Variant("Segment Splits 0", {"segSplits": (0.0, 0.0, 0.0, 0.0)}),
            Variant("Segment Splits 0.3", {"segSplits": (0.3, 0.3, 0.0, 0.0)}),
            Variant("Segment Splits 0.8", {"segSplits": (0.8, 0.8, 0.0, 0.0)}),
        ), {"showLeaves": False}),
        # Branch Angles
        Strip("split_angle", "acer", (
            Variant("Split Angle 10", {"splitAngle": (10.0, 10.0, 0.0, 0.0)}),
            Variant("Split Angle 30", {"splitAngle": (30.0, 30.0, 0.0, 0.0)}),
            Variant("Split Angle 50", {"splitAngle": (50.0, 50.0, 0.0, 0.0)}),
        ), {"showLeaves": False, "segSplits": (0.5, 0.5, 0.0, 0.0)}),
        Strip("down_angle", "acer", (
            Variant("Down Angle 30", {"downAngle": (0.0, 30.0, 45.0, 45.0)}),
            Variant("Down Angle 60", {"downAngle": (0.0, 60.0, 45.0, 45.0)}),
            Variant("Down Angle 90", {"downAngle": (0.0, 90.0, 45.0, 45.0)}),
        ), {"showLeaves": False}),
        # Branch Growth
        Strip("length", "acer", (
            Variant("Length 0.3", {"length": (1.0, 0.3, 0.5, 0.1)}),
            Variant("Length 0.6", {"length": (1.0, 0.6, 0.5, 0.1)}),
            Variant("Length 0.9", {"length": (1.0, 0.9, 0.5, 0.1)}),
        ), {"showLeaves": False}),
        Strip("curvature", "acer", (
            Variant("Curvature -40", {"curve": (0.0, -40.0, 0.0, 0.0)}),
            Variant("Curvature 0", {"curve": (0.0, 0.0, 0.0, 0.0)}),
            Variant("Curvature 40", {"curve": (0.0, 40.0, 0.0, 0.0)}),
        ), {"showLeaves": False}),
        Strip("vertical_attraction", "acer", (
            Variant("Vertical Attraction -1", {"attractUp": (0.0, -1.0, 0.0, 0.0)}),
            Variant("Vertical Attraction 0", {"attractUp": (0.0, 0.0, 0.0, 0.0)}),
            Variant("Vertical Attraction 2", {"attractUp": (0.0, 2.0, 0.0, 0.0)}),
        ), {"showLeaves": False}),
        Strip("helix", "acer", (
            Variant("Helix off", {"helix": (False, False, False, False)}),
            Variant("Helix on level 2", {"helix": (False, True, False, False)}),
            Variant("Helix on level 3", {"helix": (False, False, True, False)}),
        ), {"showLeaves": False, "curveV": (20.0, 40.0, 40.0, 0.0)}),  # Curvature Variation sets the helix angle
        # Pruning and wind shape
        Strip("prune", "acer", (
            Variant("Prune off", {"prune": False}),
            Variant("Prune Width 0.5", {"prune": True, "pruneWidth": 0.5}),
            Variant("Prune Width 0.3", {"prune": True, "pruneWidth": 0.3}),
        ), {"pruneRatio": 1.0}),
        # Leaves
        Strip("leaves", "acer", (
            Variant("Leaves 8", {"leaves": 8}),
            Variant("Leaves 25", {"leaves": 25}),
            Variant("Leaves 60", {"leaves": 60}),
        )),
        Strip("leaf_scale", "acer", (
            Variant("Leaf Scale 0.1", {"leafScale": 0.1}),
            Variant("Leaf Scale 0.2", {"leafScale": 0.2}),
            Variant("Leaf Scale 0.4", {"leafScale": 0.4}),
        )),
        Strip("blossom_rate", "hill_cherry", (
            Variant("Blossom Rate 0", {"blossomRate": 0.0}),
            Variant("Blossom Rate 0.3", {"blossomRate": 0.3}),
            Variant("Blossom Rate 0.8", {"blossomRate": 0.8}),
        )),
    )  # fmt: skip


class SettingPictures:
    """Grows the variants of a strip side by side and renders the strip."""

    GAP = 2.0  # m between two trees of a strip
    LABEL_SIZE = 0.06  # of the tallest tree, the height of a label's letters
    LABEL_WIDTH = 0.018  # of the strip's width, the least height of a label's letters
    PICTURE = (1800, 700)  # pixels of a strip

    def __init__(self, out: Path) -> None:
        """Strips into `out`, with the scene, the camera and the look of the listing media."""
        self.out = out
        self.listing = ListingMedia(Media(wide=self.PICTURE), out)

    def settings(self, preset: str, changes: dict[str, Any]) -> dict[str, Any]:
        """The preset's full settings (completed with the operator's defaults, as the operator does) with `changes`."""
        properties = bpy.ops.curve.tree_add.get_rna_type().properties
        names = sys.modules[f"{MODULE}.ui.properties"].TreeProperties.generation_names()
        tree_settings = sys.modules[f"{MODULE}.settings"].TreeSettings
        defaults = tree_settings.defaults_from_rna(properties, names).values
        store = sys.modules[f"{MODULE}.presets"].PresetStore.for_addon()
        values = store.load(preset).complete(defaults).values
        plain = {key: tree_settings.plain(value) for key, value in values.items()}
        for key, value in changes.items():
            if key not in plain:
                raise SystemExit(f"FAILED: {preset} has no setting {key}")
            plain[key] = value
        return plain

    def add(self, settings: dict[str, Any], left: float) -> Bounds:
        """Grow a tree from `settings` with its lowest x at `left`; return its bounds after the move."""
        before = {ob.name for ob in bpy.data.objects}
        result = bpy.ops.curve.tree_add(**settings, do_update=True)
        if result != {"FINISHED"}:
            raise SystemExit(f"FAILED: tree_add returned {result}")
        made = [ob for ob in bpy.data.objects if ob.name not in before]
        bounds = self.listing.bounds_of(made)
        shift = left - float(bounds.low[0])
        for ob in made:
            if ob.parent is None:
                ob.location.x += shift
        low = bounds.low.copy()
        high = bounds.high.copy()
        low[0] += shift
        high[0] += shift
        return Bounds(low=low, high=high)

    def label(self, text: str, centre_x: float, front_y: float, size: float) -> None:
        """Black text standing on the floor at depth `front_y` (in front of the trees), centred under a tree, turned
        to the camera."""
        curve = bpy.data.curves.new("render_label", "FONT")
        curve.body = text
        curve.size = size
        curve.align_x = "CENTER"
        material = bpy.data.materials.new("render_label")
        nodes = material.node_tree.nodes
        for node in nodes:
            if node.type == "BSDF_PRINCIPLED":
                node.inputs["Base Color"].default_value = (0.0, 0.0, 0.0, 1.0)
                node.inputs["Roughness"].default_value = 1.0
        curve.materials.append(material)
        ob = bpy.data.objects.new("render_label", curve)
        ob.location = (centre_x, front_y, size * 0.4)  # above the floor: the descenders stay visible
        ob.visible_shadow = False
        ob.rotation_euler = Euler((math.radians(90.0 - self.listing.look.tilt), 0.0, 0.0))
        bpy.context.scene.collection.objects.link(ob)

    def render(self, strip: Strip) -> None:
        """Grow the variants side by side, label them, add the figure and render the strip."""
        self.listing.scene.reset()
        left = 0.0
        trees = []
        for variant in strip.variants:
            changes = {**strip.base, **variant.changes}
            bounds = self.add(self.settings(strip.preset, changes), left)
            trees.append(bounds)
            left = float(bounds.high[0]) + self.GAP
        tallest = max(float(b.high[2] - b.low[2]) for b in trees)
        width = float(trees[-1].high[0] - trees[0].low[0])
        size = max(tallest * self.LABEL_SIZE, width * self.LABEL_WIDTH)  # readable on tall and on wide strips
        all_trees = self.listing.picture.bounds()
        front_y = float(all_trees.low[1]) - size * 2.0
        for variant, bounds in zip(strip.variants, trees, strict=True):
            centre = float(bounds.low[0] + bounds.high[0]) / 2
            self.label(variant.label, centre, front_y, size)
        Silhouette.add(float(all_trees.low[0]) - self.listing.look.figure_gap, float(all_trees.low[1]))
        both = self.listing.picture.bounds()
        low = both.low.copy()
        low[1] = front_y - size  # the labels stand in front of the trees (text objects are not in the bounds)
        self.listing.wide_camera(Bounds(low=low, high=both.high))
        self.listing.shoot(strip.name)


def main() -> None:
    """Enable the add-on and render every strip into the out folder."""
    out = Path(sys.argv[sys.argv.index("--") + 1])
    bpy.ops.preferences.addon_enable(module=MODULE)
    pictures = SettingPictures(out)
    names = sys.argv[sys.argv.index("--") + 2 :]
    for strip in Strips.ALL:
        if names and strip.name not in names:
            continue
        pictures.render(strip)


main()
