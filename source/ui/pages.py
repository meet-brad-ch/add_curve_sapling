# SPDX-License-Identifier: GPL-3.0-or-later

"""The settings pages of the Add Tree operator panel."""

from typing import Any

import bpy
from bpy.types import UILayout

from ..model.geometry import CrownShape
from ..model.leaves import LeafShape
from ..settings import TreeSettings
from .preset_save import SavePresetOperator
from .properties import TreeProperties


class SettingsPages:
    """Draws the page chosen with the operator's `chooseSet` property."""

    # One method per entry of Choices.PAGES, in the same order
    ORDER = [
        "geometry", "branch_radius", "branch_splitting", "branch_growth", "pruning", "leaves", "armature", "animation",
    ]  # fmt: skip

    @classmethod
    def draw(cls, props: Any, layout: UILayout) -> None:
        """Draw the page selector and the chosen page in a box; props is the Add Tree operator."""
        layout.prop(props, "chooseSet")
        page = getattr(cls, cls.ORDER[int(props.chooseSet)])
        page(props, layout.box())

    @staticmethod
    def geometry(props: Any, box: UILayout) -> None:
        """Tree shape, scale and curve resolution, plus loading and saving presets."""
        box.prop(props, "bevel")
        row = box.row()
        row.prop(props, "bevelRes")
        row.prop(props, "resU")
        box.prop(props, "handleType")
        box.prop(props, "shape")
        if props.shape == str(CrownShape.CUSTOM):
            box.column().prop(props, "customShape")
        box.prop(props, "shapeS")
        box.prop(props, "branchDist")
        box.prop(props, "nrings")
        box.prop(props, "seed")
        box.label(text="Tree Scale:")
        row = box.row()
        row.prop(props, "scale")
        row.prop(props, "scaleV")

        box.label(text="Presets:")
        row = box.row()
        row.prop(props, "preset", text="")
        row.prop(props, "limitImport")
        row = box.row()
        row.prop(props, "presetName", text="")
        save = row.operator(SavePresetOperator.bl_idname, icon="FILE_TICK")
        save.name = props.presetName
        save.overwrite = props.overwrite
        save.settings = TreeSettings.from_properties(props, TreeProperties.generation_names()).to_json()
        row.prop(props, "overwrite")

    @staticmethod
    def branch_radius(props: Any, box: UILayout) -> None:
        """Bevel, radius ratio and scale, taper and root flare."""
        row = box.row()
        row.prop(props, "bevel")
        row.prop(props, "bevelRes")
        box.prop(props, "ratio")
        row = box.row()
        row.prop(props, "scale0")
        row.prop(props, "scaleV0")
        box.prop(props, "ratioPower")
        box.prop(props, "minRadius")
        box.prop(props, "closeTip")
        box.prop(props, "rootFlare")
        box.prop(props, "autoTaper")
        split = box.split()
        split.column().prop(props, "taper")
        split.column().prop(props, "radiusTweak")

    @staticmethod
    def branch_splitting(props: Any, box: UILayout) -> None:
        """Levels, base and segment splits, branch counts, angles and branching mode."""
        box.prop(props, "levels")
        box.prop(props, "trunks")
        box.prop(props, "baseSplits")
        row = box.row()
        row.prop(props, "baseSize")
        row.prop(props, "baseSize_s")
        box.prop(props, "splitHeight")
        box.prop(props, "splitBias")
        box.prop(props, "splitByLen")
        split = box.split()
        col = split.column()
        col.prop(props, "branches")
        col.prop(props, "splitAngle")
        col.prop(props, "rotate")
        col.prop(props, "attractOut")
        col = split.column()
        col.prop(props, "segSplits")
        col.prop(props, "splitAngleV")
        col.prop(props, "rotateV")
        col.prop(props, "rMode")
        box.column().prop(props, "curveRes")

    @staticmethod
    def branch_growth(props: Any, box: UILayout) -> None:
        """Branch lengths, down angles, curvature and attraction."""
        box.prop(props, "taperCrown")
        split = box.split()
        col = split.column()
        col.prop(props, "length")
        col.prop(props, "downAngle")
        col.prop(props, "curve")
        col.prop(props, "curveBack")
        col.prop(props, "bendV")
        col = split.column()
        col.prop(props, "lengthV")
        col.prop(props, "downAngleV")
        col.prop(props, "curveV")
        col.prop(props, "attractUp")
        box.prop(props, "helix")
        box.prop(props, "useOldDownAngle")
        box.prop(props, "useParentAngle")

    @staticmethod
    def pruning(props: Any, box: UILayout) -> None:
        """The pruning envelope."""
        box.prop(props, "prune")
        box.prop(props, "pruneRatio")
        row = box.row()
        row.prop(props, "pruneWidth")
        row.prop(props, "pruneBase")
        box.prop(props, "pruneWidthPeak")
        row = box.row()
        row.prop(props, "prunePowerHigh")
        row.prop(props, "prunePowerLow")

    @staticmethod
    def leaves(props: Any, box: UILayout) -> None:
        """Leaf shape, count, angles and scale; the leaf object for instanced shapes, the material for meshes."""
        box.prop(props, "showLeaves")
        box.prop(props, "leafShape")
        if props.leafShape in LeafShape.INSTANCED:
            box.prop_search(props, "leafDupliObj", bpy.data, "objects")
        box.prop(props, "leaves")
        box.prop(props, "leafDist")
        row = box.row()
        row.prop(props, "leafDownAngle")
        row.prop(props, "leafDownAngleV")
        row = box.row()
        row.prop(props, "leafRotate")
        row.prop(props, "leafRotateV")
        row = box.row()
        row.prop(props, "leafScale")
        row.prop(props, "leafScaleX")
        row = box.row()
        row.prop(props, "leafScaleT")
        row.prop(props, "leafScaleV")
        if props.leafShape in LeafShape.MESH:
            box.prop(props, "leafMaterial")
        box.prop(props, "horzLeaves")
        box.prop(props, "leafangle")

    @staticmethod
    def armature(props: Any, box: UILayout) -> None:
        """Armature rig, baked mesh and armature simplification."""
        box.prop(props, "useRig")
        box.prop(props, "makeMesh")
        box.label(text="Armature Simplification:")
        box.prop(props, "jointLevels")
        box.prop(props, "jointStep")

    @staticmethod
    def animation(props: Any, box: UILayout) -> None:
        """Armature and leaf wind animation."""
        box.label(text="Finalize All Other Settings First!")
        box.prop(props, "windAnim")
        box.prop(props, "leafFlutter")
        box.prop(props, "fastPreview")
        box.prop(props, "animationSpeed")
        box.prop(props, "loopFrames")
        box.label(text="Wind Settings:")
        box.prop(props, "windStrength")
        row = box.row()
        row.prop(props, "gustStrength")
        row.prop(props, "gustFrequency")
        box.label(text="Leaf Wind Settings:")
        box.prop(props, "flutterStrength")
        box.prop(props, "flutterSpeed")
        box.prop(props, "flutterRandomness")
