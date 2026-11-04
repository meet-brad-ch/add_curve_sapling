# SPDX-License-Identifier: GPL-3.0-or-later

"""The settings pages of the Add Tree operator panel."""

from typing import Any

import bpy
from bpy.types import UILayout

from ..service.page_rules import PageRules
from ..settings import TreeSettings
from .preset_save import SavePresetOperator
from .properties import TreeProperties


class SettingsPages:
    """Draws the page chosen with the operator's `chooseSet` property."""

    # One method per entry of Choices.PAGES, in the same order
    ORDER = (
        "geometry", "branch_radius", "branch_splitting", "branch_angles", "branch_growth", "pruning", "leaves",
        "armature", "animation",
    )  # fmt: skip

    @classmethod
    def draw(cls, props: Any, layout: UILayout) -> None:
        """Draw the page selector and the chosen page in a box; props is the Add Tree operator."""
        layout.prop(props, "chooseSet")
        page = getattr(cls, cls.ORDER[int(props.chooseSet)])
        page(props, layout.box())

    LEVELS = 4  # every per-level setting holds one value per level, the trunk first

    @classmethod
    def level_heading(cls, box: UILayout) -> None:
        """The column heading of the per-level rows: one label per level."""
        row = box.row(align=True)
        for level in range(cls.LEVELS):
            row.label(text=f"Level {level + 1}")

    @classmethod
    def per_level(cls, props: Any, box: UILayout, name: str, label: str) -> None:
        """A per-level setting: its label on one line, then its values side by side, the levels above Levels drawn
        inactive (they have no effect)."""
        box.label(text=f"{label}:")
        row = box.row(align=True)
        for level in range(cls.LEVELS):
            cell = row.row(align=True)
            cell.active = level < props.levels
            cell.prop(props, name, index=level, text="")

    @staticmethod
    def geometry(props: Any, box: UILayout) -> None:
        """Tree shape, scale and curve resolution, plus loading and saving presets."""
        box.prop(props, "bevel")
        box.prop(props, "bevelRes")
        box.prop(props, "resU")
        box.label(text="Handle Type:")
        box.prop(props, "handleType", text="")
        box.label(text="Shape:")
        box.prop(props, "shape", text="")
        if PageRules.custom_shape(props):
            box.column().prop(props, "customShape")
        box.label(text="Secondary Branches Shape:")
        box.prop(props, "shapeS", text="")
        box.prop(props, "branchDist")
        box.prop(props, "nrings")
        box.prop(props, "seed")
        box.label(text="Tree Scale:")
        box.prop(props, "scale")
        box.prop(props, "scaleV")

        box.label(text="Presets:")
        box.prop(props, "preset", text="")
        box.prop(props, "presetName", text="")
        row = box.row()
        save = row.operator(SavePresetOperator.bl_idname, icon="FILE_TICK")
        save.name = props.presetName
        save.overwrite = props.overwrite
        save.settings = TreeSettings.from_properties(props, TreeProperties.generation_names()).to_json()
        row.prop(props, "overwrite")

    @classmethod
    def branch_radius(cls, props: Any, box: UILayout) -> None:
        """Radius ratio and scale, taper and root flare (the bevel is on the Geometry page)."""
        box.prop(props, "ratio")
        box.prop(props, "scale0")
        box.prop(props, "scaleV0")
        box.prop(props, "ratioPower")
        box.prop(props, "minRadius")
        box.prop(props, "closeTip")
        box.prop(props, "rootFlare")
        box.prop(props, "autoTaper")
        cls.level_heading(box)
        cls.per_level(props, box, "taper", "Taper")
        cls.per_level(props, box, "radiusTweak", "Tweak Radius")

    @classmethod
    def branch_splitting(cls, props: Any, box: UILayout) -> None:
        """Levels, base and segment splits, branch counts, angles and branching mode."""
        box.prop(props, "levels")
        box.prop(props, "trunks")
        box.prop(props, "trunksFaceOut")
        box.prop(props, "baseSplits")
        box.prop(props, "baseSize")
        box.prop(props, "baseSize_s")
        box.prop(props, "splitHeight")
        box.prop(props, "splitBias")
        box.prop(props, "splitByLen")
        box.prop(props, "countAboveBase")
        cls.level_heading(box)
        cls.per_level(props, box, "branches", "Branches")
        cls.per_level(props, box, "branchBase", "Branch Base")
        cls.per_level(props, box, "segSplits", "Segment Splits")
        cls.per_level(props, box, "curveRes", "Segments")

    @classmethod
    def branch_angles(cls, props: Any, box: UILayout) -> None:
        """The branching mode and the split, rotate and down angles with their variations and rules."""
        box.label(text="Branching Mode:")
        box.prop(props, "rMode", text="")
        cls.level_heading(box)
        cls.per_level(props, box, "splitAngle", "Split Angle")
        cls.per_level(props, box, "splitAngleV", "Split Angle Variation")
        cls.per_level(props, box, "rotate", "Rotate Angle")
        cls.per_level(props, box, "rotateV", "Rotate Angle Variation")
        cls.per_level(props, box, "downAngle", "Down Angle")
        cls.per_level(props, box, "downAngleV", "Down Angle Variation")
        box.prop(props, "useOldDownAngle")
        box.prop(props, "useParentAngle")

    @classmethod
    def branch_growth(cls, props: Any, box: UILayout) -> None:
        """Branch lengths, curvature, attraction, bend and helix."""
        box.prop(props, "taperCrown")
        cls.level_heading(box)
        cls.per_level(props, box, "length", "Length")
        cls.per_level(props, box, "lengthV", "Length Variation")
        cls.per_level(props, box, "curve", "Curvature")
        cls.per_level(props, box, "curveV", "Curvature Variation")
        cls.per_level(props, box, "curveBack", "Back Curvature")
        cls.per_level(props, box, "attractUp", "Vertical Attraction")
        cls.per_level(props, box, "attractOut", "Outward Attraction")
        cls.per_level(props, box, "bendV", "Bend Variation")
        cls.per_level(props, box, "helix", "Helix")

    @classmethod
    def pruning(cls, props: Any, box: UILayout) -> None:
        """The pruning envelope and the wind shape (direction, shear and bend)."""
        box.prop(props, "prune")
        box.prop(props, "pruneRatio")
        box.prop(props, "pruneWidth")
        box.prop(props, "pruneBase")
        box.prop(props, "pruneWidthPeak")
        box.prop(props, "prunePowerHigh")
        box.prop(props, "prunePowerLow")
        box.label(text="Wind Shape:")
        box.prop(props, "windDir")
        box.prop(props, "windShear")
        cls.level_heading(box)
        cls.per_level(props, box, "windBend", "Wind Bend")

    @classmethod
    def leaves(cls, props: Any, box: UILayout) -> None:
        """Leaf shape, count, angles and scale; the blossoms; the leaf options (PageRules: where each has effect)."""
        cls.leaf_shape(props, box)
        cls.leaf_angles(props, box)
        cls.blossoms(props, box)
        cls.leaf_options(props, box)

    @staticmethod
    def leaf_shape(props: Any, box: UILayout) -> None:
        """Show Leaves, the shape, the leaf object of instanced shapes, the count and the distribution."""
        box.prop(props, "showLeaves")
        box.label(text="Leaf Shape:")
        box.prop(props, "leafShape", text="")
        if PageRules.leaf_object(props):
            box.prop_search(props, "leafDupliObj", bpy.data, "objects")
        box.prop(props, "leaves")
        box.label(text="Leaf Distribution:")
        box.prop(props, "leafDist", text="")

    @staticmethod
    def leaf_angles(props: Any, box: UILayout) -> None:
        """The down and rotate angles and the scales, each with its variation."""
        box.prop(props, "leafDownAngle")
        box.prop(props, "leafDownAngleV")
        box.prop(props, "leafRotate")
        box.prop(props, "leafRotateV")
        box.prop(props, "leafScale")
        box.prop(props, "leafScaleX")
        box.prop(props, "leafScaleT")
        box.prop(props, "leafScaleV")

    @staticmethod
    def blossoms(props: Any, box: UILayout) -> None:
        """The blossom rate; its shape and scale when there are blossoms."""
        box.prop(props, "blossomRate")
        if PageRules.blossom_options(props):
            box.label(text="Blossom Shape:")
            box.prop(props, "blossomShape", text="")
            box.prop(props, "blossomScale")

    @staticmethod
    def leaf_options(props: Any, box: UILayout) -> None:
        """The material (for meshes) and the leaf turns: horizontal, face up, fans, above base, angle."""
        if PageRules.leaf_material(props):
            box.prop(props, "leafMaterial")
        box.prop(props, "horzLeaves")
        box.prop(props, "leafUp")
        box.prop(props, "leafUpV")
        box.prop(props, "fanAngles")
        box.prop(props, "leavesAboveBase")
        box.prop(props, "leafangle")

    @classmethod
    def armature(cls, props: Any, box: UILayout) -> None:
        """Armature rig, baked mesh and armature simplification."""
        box.prop(props, "useRig")
        box.prop(props, "makeMesh")
        box.label(text="Armature Simplification:")
        box.prop(props, "jointLevels")
        cls.level_heading(box)
        cls.per_level(props, box, "jointStep", "Joint Length")

    @staticmethod
    def animation(props: Any, box: UILayout) -> None:
        """Armature and leaf wind animation."""
        box.label(text="Set the tree first, then the wind.")
        box.prop(props, "windAnim")
        box.prop(props, "leafFlutter")
        box.prop(props, "fastPreview")
        box.prop(props, "animationSpeed")
        box.prop(props, "loopFrames")
        box.label(text="Wind Settings:")
        box.prop(props, "windStrength")
        box.prop(props, "gustStrength")
        box.prop(props, "gustFrequency")
        box.label(text="Leaf Wind Settings:")
        box.prop(props, "flutterStrength")
        box.prop(props, "flutterSpeed")
        box.prop(props, "flutterRandomness")
