# SPDX-License-Identifier: GPL-3.0-or-later

"""The settings pages of the Add Tree operator panel."""

from ..settings import TreeSettings
from .properties import TreeProperties


class SettingsPages:
    """Draws the page chosen with the operator's `chooseSet` property."""

    @classmethod
    def draw(cls, props, layout):
        layout.prop(props, "chooseSet")
        page = {
            "0": cls.geometry,
            "1": cls.branch_radius,
            "2": cls.branch_splitting,
            "3": cls.branch_growth,
            "4": cls.pruning,
            "5": cls.leaves,
            "6": cls.armature,
            "7": cls.animation,
        }[props.chooseSet]
        page(props, layout.box())

    @staticmethod
    def geometry(props, box):
        box.prop(props, "bevel")
        row = box.row()
        row.prop(props, "bevelRes")
        row.prop(props, "resU")
        box.prop(props, "handleType")
        box.prop(props, "shape")
        if props.shape == "8":
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
        save = row.operator("sapling.preset_save", icon="FILE_TICK")
        save.name = props.presetName
        save.overwrite = props.overwrite
        save.settings = TreeSettings.from_properties(props, TreeProperties.generation_names()).to_json()
        row.prop(props, "overwrite")

    @staticmethod
    def branch_radius(props, box):
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
    def branch_splitting(props, box):
        box.prop(props, "levels")
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
    def branch_growth(props, box):
        box.prop(props, "taperCrown")
        split = box.split()
        col = split.column()
        col.prop(props, "length")
        col.prop(props, "downAngle")
        col.prop(props, "curve")
        col.prop(props, "curveBack")
        col = split.column()
        col.prop(props, "lengthV")
        col.prop(props, "downAngleV")
        col.prop(props, "curveV")
        col.prop(props, "attractUp")
        box.prop(props, "useOldDownAngle")
        box.prop(props, "useParentAngle")

    @staticmethod
    def pruning(props, box):
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
    def leaves(props, box):
        box.prop(props, "showLeaves")
        box.prop(props, "leafShape")
        if props.leafShape in {"dFace", "dVert"}:
            box.prop(props, "leafDupliObj")
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
        box.prop(props, "horzLeaves")
        box.prop(props, "leafangle")

    @staticmethod
    def armature(props, box):
        box.prop(props, "useArm")
        box.prop(props, "makeMesh")
        box.label(text="Armature Simplification:")
        box.prop(props, "armLevels")
        box.prop(props, "boneStep")

    @staticmethod
    def animation(props, box):
        box.label(text="Finalize All Other Settings First!")
        box.prop(props, "armAnim")
        box.prop(props, "leafAnim")
        box.prop(props, "previewArm")
        box.prop(props, "frameRate")
        box.prop(props, "loopFrames")
        box.label(text="Wind Settings:")
        box.prop(props, "wind")
        row = box.row()
        row.prop(props, "gust")
        row.prop(props, "gustF")
        box.label(text="Leaf Wind Settings:")
        box.prop(props, "af1")
        box.prop(props, "af2")
        box.prop(props, "af3")
