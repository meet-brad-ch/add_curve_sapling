# SPDX-License-Identifier: GPL-3.0-or-later

"""The operator's tree properties. Their names are the operator API and the preset keys."""

from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    FloatVectorProperty,
    IntProperty,
    IntVectorProperty,
    StringProperty,
)
from bpy.types import Context

from ..model.branching import BranchingMode
from ..model.geometry import CrownShape
from ..model.leaves import LeafShape


class Choices:
    """Enum items of the tree properties."""

    SHAPES = [
        ("0", "Conical", ""),
        ("6", "Inverse Conical", ""),
        ("1", "Spherical", ""),
        ("2", "Hemispherical", ""),
        ("3", "Cylindrical", ""),
        ("4", "Tapered Cylindrical", ""),
        ("10", "Inverse Tapered Cylindrical", ""),
        ("5", "Flame", ""),
        ("7", "Tend Flame", ""),
        (str(CrownShape.CUSTOM), "Custom Shape", ""),
    ]
    SECONDARY_SHAPES = [item for item in SHAPES if item[0] != str(CrownShape.CUSTOM)]
    HANDLES = [("0", "Auto", "Smooth automatic handles"), ("1", "Vector", "Straight segments")]
    BRANCH_MODES = [
        (BranchingMode.ORIGINAL, "Original", "Rotate around each branch"),
        (BranchingMode.ROTATE, "Rotate", "Evenly distribute branches to point outward from the center of the tree"),
        (BranchingMode.RANDOM, "Random", "Choose a random point"),
    ]
    LEAF_SHAPES = [
        (LeafShape.HEX, "Hexagonal", "Hexagonal leaf mesh"),
        (LeafShape.RECT, "Rectangular", "Rectangular leaf mesh, for image textures"),
        (LeafShape.INSTANCE_FACES, "Instance Faces", "Instance the leaf object on one face per leaf"),
        (LeafShape.INSTANCE_POINTS, "Instance Points", "Instance the leaf object on one point per leaf"),
    ]
    PAGES = [
        ("0", "Geometry", "Tree shape, scale, curve settings and presets"),
        ("1", "Branch Radius", "Radius and taper of the branches"),
        ("2", "Branch Splitting", "Levels, splits and branch counts"),
        ("3", "Branch Growth", "Length, angles and curvature"),
        ("4", "Pruning", "Pruning envelope"),
        ("5", "Leaves", "Leaf shape and placement"),
        ("6", "Armature", "Armature and skin mesh"),
        ("7", "Animation", "Wind animation"),
    ]


class TreeProperties:
    """Mixin with the tree properties, for the Add Tree operator.

    Changing a generation property regenerates the tree; changing a page, preset name or other UI
    state does not (do_update is cleared and the operator passes through).
    """

    # Refers to an object in the scene: stored with a tree, never in presets.
    SCENE_BOUND = ("leafDupliObj",)
    # UI state: never part of presets or stored tree settings.
    UI_ONLY = frozenset({"do_update", "chooseSet", "presetName", "limitImport", "overwrite"})

    def update_tree(self, context: Context) -> None:
        """Update callback of a generation property: the next run regenerates the tree."""
        self.do_update = True

    def update_leaves(self, context: Context) -> None:
        """Update callback of a leaf property: regenerate only when the leaves are shown (otherwise nothing changes)."""
        self.do_update = self.showLeaves

    def no_update_tree(self, context: Context) -> None:
        """Update callback of UI state (page, preset name, ...): the next run keeps the tree as it is."""
        self.do_update = False

    do_update: BoolProperty(name="Do Update", default=True, options={"HIDDEN", "SKIP_SAVE"})
    chooseSet: EnumProperty(
        name="Settings", description="Choose the settings to modify", items=Choices.PAGES, default="0",
        update=no_update_tree,
    )  # fmt: skip

    # Geometry
    bevel: BoolProperty(name="Bevel", description="Give the branches thickness", default=False, update=update_tree)
    bevelRes: IntProperty(
        name="Bevel Resolution", description="The bevel resolution of the curves", min=0, max=32, default=0,
        update=update_tree,
    )  # fmt: skip
    resU: IntProperty(
        name="Curve Resolution", description="The resolution along the curves", min=1, default=4, update=update_tree
    )
    handleType: EnumProperty(
        name="Handle Type", description="The type of handles used in the spline", items=Choices.HANDLES,
        default="0", update=update_tree,
    )  # fmt: skip
    shape: EnumProperty(
        name="Shape", description="The overall shape of the tree (Shape)", items=Choices.SHAPES, default="7",
        update=update_tree,
    )  # fmt: skip
    shapeS: EnumProperty(
        name="Secondary Branches Shape", description="The shape of secondary splits", items=Choices.SECONDARY_SHAPES,
        default="4", update=update_tree,
    )  # fmt: skip
    customShape: FloatVectorProperty(
        name="Custom Shape", description="Custom shape branch length at (Base, Middle, Middle Position, Top)",
        size=4, min=0.01, max=1, default=[0.5, 1.0, 0.3, 0.5], update=update_tree,
    )  # fmt: skip
    branchDist: FloatProperty(
        name="Branch Distribution",
        description="Adjust branch spacing to put more branches at the top or bottom of the tree",
        min=0.1, soft_max=10, default=1.0, update=update_tree,
    )  # fmt: skip
    nrings: IntProperty(name="Branch Rings", description="Grow branches in rings", min=0, default=0, update=update_tree)
    seed: IntProperty(
        name="Random Seed", description="The seed of the random number generator", default=0, update=update_tree
    )
    scale: FloatProperty(name="Scale", description="The tree scale (Scale)", min=0.0, default=13.0, update=update_tree)
    scaleV: FloatProperty(
        name="Scale Variation", description="The variation in the tree scale (ScaleV)", default=3.0,
        update=update_tree,
    )  # fmt: skip

    # Branch radius
    ratio: FloatProperty(
        name="Ratio", description="Base radius size (Ratio)", min=0.0, default=0.015, update=update_tree
    )
    scale0: FloatProperty(
        name="Radius Scale", description="The scale of the trunk radius (0Scale)", min=0.0, default=1.0,
        update=update_tree,
    )  # fmt: skip
    scaleV0: FloatProperty(
        name="Radius Scale Variation", description="Variation in the radius scale (0ScaleV)", min=0.0, max=1.0,
        default=0.2, update=update_tree,
    )  # fmt: skip
    ratioPower: FloatProperty(
        name="Branch Radius Ratio",
        description="Power which defines the radius of a branch compared to the radius of the branch it grew from "
        "(RatioPower)",
        min=0.0, default=1.2, update=update_tree,
    )  # fmt: skip
    minRadius: FloatProperty(
        name="Minimum Radius", description="Minimum branch radius", min=0.0, default=0.0, update=update_tree
    )
    closeTip: BoolProperty(
        name="Close Tip", description="Set radius at branch tips to zero", default=False, update=update_tree
    )
    rootFlare: FloatProperty(
        name="Root Flare", description="Root radius factor", min=1.0, default=1.0, update=update_tree
    )
    autoTaper: BoolProperty(
        name="Auto Taper", description="Calculate taper automatically based on branch lengths", default=True,
        update=update_tree,
    )  # fmt: skip
    taper: FloatVectorProperty(
        name="Taper", description="The fraction of tapering on each branch (nTaper)", min=0.0, max=1.0,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip
    radiusTweak: FloatVectorProperty(
        name="Tweak Radius", description="Multiply the radius by this factor", min=0.0, max=1.0,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip

    # Branch splitting
    levels: IntProperty(
        name="Levels", description="Number of recursive branches (Levels)", min=1, max=6, soft_max=4, default=3,
        update=update_tree,
    )  # fmt: skip
    baseSplits: IntProperty(
        name="Base Splits", description="Number of trunk splits at its base (nBaseSplits)", min=0, default=0,
        update=update_tree,
    )  # fmt: skip
    baseSize: FloatProperty(
        name="Trunk Height", description="Fraction of tree height with no branches (Base Size)", min=0.0, max=1.0,
        default=0.4, update=update_tree,
    )  # fmt: skip
    baseSize_s: FloatProperty(
        name="Secondary Base Size", description="Factor to decrease base size for each level", min=0.0, max=1.0,
        default=0.25, update=update_tree,
    )  # fmt: skip
    splitHeight: FloatProperty(
        name="Split Height", description="Fraction of tree height with no splits", min=0.0, max=1.0, default=0.2,
        update=update_tree,
    )  # fmt: skip
    splitBias: FloatProperty(
        name="Split Bias", description="Put more splits at the top or bottom of the tree", soft_min=-2.0,
        soft_max=2.0, default=0.0, update=update_tree,
    )  # fmt: skip
    splitByLen: BoolProperty(
        name="Split Relative to Length", description="Split proportional to branch length", default=False,
        update=update_tree,
    )  # fmt: skip
    branches: IntVectorProperty(
        name="Branches", description="The number of branches grown at each level (nBranches)", min=0,
        default=[50, 30, 10, 10], size=4, update=update_tree,
    )  # fmt: skip
    segSplits: FloatVectorProperty(
        name="Segment Splits", description="Number of splits per segment (nSegSplits)", min=0, soft_max=3,
        default=[0, 0, 0, 0], size=4, update=update_tree,
    )  # fmt: skip
    splitAngle: FloatVectorProperty(
        name="Split Angle", description="Angle of branch splitting (nSplitAngle)", default=[0, 0, 0, 0], size=4,
        update=update_tree,
    )  # fmt: skip
    splitAngleV: FloatVectorProperty(
        name="Split Angle Variation", description="Variation in the split angle (nSplitAngleV)",
        default=[0, 0, 0, 0], size=4, update=update_tree,
    )  # fmt: skip
    rotate: FloatVectorProperty(
        name="Rotate Angle",
        description="The angle of a new branch around the one it grew from (negative values rotate opposite from "
        "the previous)",
        default=[137.5, 137.5, 137.5, 137.5], size=4, update=update_tree,
    )  # fmt: skip
    rotateV: FloatVectorProperty(
        name="Rotate Angle Variation", description="Variation in the rotate angle (nRotateV)", default=[0, 0, 0, 0],
        size=4, update=update_tree,
    )  # fmt: skip
    attractOut: FloatVectorProperty(
        name="Outward Attraction", description="Branch outward attraction", default=[0, 0, 0, 0], min=0.0, max=1.0,
        size=4, update=update_tree,
    )  # fmt: skip
    rMode: EnumProperty(
        name="Branching Mode", description="Branching and rotation mode", items=Choices.BRANCH_MODES,
        default=BranchingMode.ROTATE, update=update_tree,
    )  # fmt: skip
    curveRes: IntVectorProperty(
        name="Curve Resolution", description="The number of segments on each branch (nCurveRes)", min=1,
        default=[3, 5, 3, 1], size=4, update=update_tree,
    )  # fmt: skip

    # Branch growth
    taperCrown: FloatProperty(
        name="Taper Crown", description="Shorten trunk splits toward the outside of the tree", min=0.0, soft_max=1.0,
        default=0, update=update_tree,
    )  # fmt: skip
    length: FloatVectorProperty(
        name="Length", description="The relative lengths of each branch level (nLength)", min=0.000001,
        default=[1, 0.3, 0.6, 0.45], size=4, update=update_tree,
    )  # fmt: skip
    lengthV: FloatVectorProperty(
        name="Length Variation", description="The relative length variations of each level (nLengthV)", min=0.0,
        max=1.0, default=[0, 0, 0, 0], size=4, update=update_tree,
    )  # fmt: skip
    downAngle: FloatVectorProperty(
        name="Down Angle", description="The angle between a new branch and the one it grew from (nDownAngle)",
        default=[90, 60, 45, 45], size=4, update=update_tree,
    )  # fmt: skip
    downAngleV: FloatVectorProperty(
        name="Down Angle Variation",
        description="Angle to decrease Down Angle by towards end of parent branch (negative values add random "
        "variation)",
        default=[0, -50, 10, 10], size=4, update=update_tree,
    )  # fmt: skip
    curve: FloatVectorProperty(
        name="Curvature", description="The angle of the end of the branch (nCurve)", default=[0, -40, -40, 0],
        size=4, update=update_tree,
    )  # fmt: skip
    curveV: FloatVectorProperty(
        name="Curvature Variation", description="Variation of the curvature (nCurveV)", default=[20, 50, 75, 0],
        size=4, update=update_tree,
    )  # fmt: skip
    curveBack: FloatVectorProperty(
        name="Back Curvature", description="Curvature for the second half of a branch (nCurveBack)",
        default=[0, 0, 0, 0], size=4, update=update_tree,
    )  # fmt: skip
    attractUp: FloatVectorProperty(
        name="Vertical Attraction", description="Branch upward attraction", default=[0, 0, 0, 0], size=4,
        update=update_tree,
    )  # fmt: skip
    useOldDownAngle: BoolProperty(
        name="Use Old Down Angle Variation",
        description="Down Angle Variation as in older versions: negative values scale the angle along the parent",
        default=False, update=update_tree,
    )  # fmt: skip
    useParentAngle: BoolProperty(
        name="Use Parent Angle", description="(First level) Rotate branch to match parent branch", default=True,
        update=update_tree,
    )  # fmt: skip

    # Pruning
    prune: BoolProperty(name="Prune", description="Whether the tree is pruned", default=False, update=update_tree)
    pruneRatio: FloatProperty(
        name="Prune Ratio", description="Proportion of pruned length (PruneRatio)", min=0.0, max=1.0, default=1.0,
        update=update_tree,
    )  # fmt: skip
    pruneWidth: FloatProperty(
        name="Prune Width", description="The width of the envelope (PruneWidth)", min=0.0, default=0.4,
        update=update_tree,
    )  # fmt: skip
    pruneBase: FloatProperty(
        name="Prune Base Height", description="The height of the base of the envelope, bound by trunk height",
        min=0.0, max=1.0, default=0.3, update=update_tree,
    )  # fmt: skip
    pruneWidthPeak: FloatProperty(
        name="Prune Width Peak",
        description="Fraction of envelope height where the maximum width occurs (PruneWidthPeak)",
        min=0.0, default=0.6, update=update_tree,
    )  # fmt: skip
    prunePowerHigh: FloatProperty(
        name="Prune Power High",
        description="Power which determines the shape of the upper portion of the envelope (PrunePowerHigh)",
        default=0.5, update=update_tree,
    )  # fmt: skip
    prunePowerLow: FloatProperty(
        name="Prune Power Low",
        description="Power which determines the shape of the lower portion of the envelope (PrunePowerLow)",
        default=0.001, update=update_tree,
    )  # fmt: skip

    # Leaves
    showLeaves: BoolProperty(
        name="Show Leaves", description="Whether the leaves are shown", default=False, update=update_tree
    )
    leafShape: EnumProperty(
        name="Leaf Shape", description="The shape of the leaves", items=Choices.LEAF_SHAPES, default=LeafShape.HEX,
        update=update_leaves,
    )  # fmt: skip
    leafDupliObj: StringProperty(
        name="Leaf Object", description="Object instanced as the leaf (Instance Faces and Instance Points)",
        default="", update=update_leaves,
    )  # fmt: skip
    leaves: IntProperty(
        name="Leaves",
        description="Maximum number of leaves per branch (negative values grow leaves from branch tip (palmate "
        "compound leaves))",
        default=25, update=update_tree,
    )  # fmt: skip
    leafDist: EnumProperty(
        name="Leaf Distribution", description="The way leaves are distributed on branches",
        items=Choices.SECONDARY_SHAPES, default="6", update=update_tree,
    )  # fmt: skip
    leafDownAngle: FloatProperty(
        name="Leaf Down Angle", description="The angle between a new leaf and the branch it grew from", default=45,
        update=update_leaves,
    )  # fmt: skip
    leafDownAngleV: FloatProperty(
        name="Leaf Down Angle Variation",
        description="Angle to decrease Down Angle by towards end of parent branch (negative values add random "
        "variation)",
        default=10, update=update_leaves,
    )  # fmt: skip
    leafRotate: FloatProperty(
        name="Leaf Rotate Angle",
        description="The angle of a new leaf around the one it grew from (negative values rotate opposite from "
        "previous)",
        default=137.5, update=update_leaves,
    )  # fmt: skip
    leafRotateV: FloatProperty(
        name="Leaf Rotate Angle Variation", description="Variation in the rotate angle", default=0.0,
        update=update_leaves,
    )  # fmt: skip
    leafScale: FloatProperty(
        name="Leaf Scale", description="The scaling applied to the whole leaf (LeafScale)", min=0.0, default=0.17,
        update=update_leaves,
    )  # fmt: skip
    leafScaleX: FloatProperty(
        name="Leaf Scale X", description="The scaling applied to the x direction of the leaf (LeafScaleX)", min=0.0,
        default=1.0, update=update_leaves,
    )  # fmt: skip
    leafScaleT: FloatProperty(
        name="Leaf Scale Taper", description="Scale leaves toward the tip or base of the parent branch", min=-1.0,
        max=1.0, default=0.0, update=update_leaves,
    )  # fmt: skip
    leafScaleV: FloatProperty(
        name="Leaf Scale Variation", description="Randomize leaf scale", min=0.0, max=1.0, default=0.0,
        update=update_leaves,
    )  # fmt: skip
    bend: FloatProperty(
        name="Leaf Bend", description="The proportion of bending applied to the leaf (Bend)", min=0.0, max=1.0,
        default=0.0, update=update_leaves,
    )  # fmt: skip
    leafangle: FloatProperty(
        name="Leaf Angle", description="Leaf vertical attraction", default=0.0, update=update_leaves
    )
    leafMaterial: BoolProperty(
        name="Leaf Material",
        description="Give mesh leaves the Sapling Leaf material: Thin Wall shading, so light shines through the "
        "leaves like through real ones",
        default=True, update=update_leaves,
    )  # fmt: skip
    horzLeaves: BoolProperty(
        name="Horizontal Leaves", description="Leaves face upwards", default=True, update=update_leaves
    )

    # Armature
    useArm: BoolProperty(
        name="Use Armature", description="Whether the armature is generated", default=False, update=update_tree
    )
    makeMesh: BoolProperty(
        name="Make Mesh",
        description="Convert curves to mesh, uses skin modifier, enables armature simplification",
        default=False, update=update_tree,
    )  # fmt: skip
    armLevels: IntProperty(
        name="Armature Levels", description="Number of branching levels to make bones for, 0 is all levels", min=0,
        default=2, update=update_tree,
    )  # fmt: skip
    boneStep: IntVectorProperty(
        name="Bone Length", description="Number of stem segments per bone (with Make Mesh)", min=1,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip

    # Animation
    armAnim: BoolProperty(
        name="Armature Animation", description="Whether animation is added to the armature", default=False,
        update=update_tree,
    )  # fmt: skip
    leafAnim: BoolProperty(
        name="Leaf Animation", description="Whether animation is added to the leaves", default=False,
        update=update_tree,
    )  # fmt: skip
    previewArm: BoolProperty(
        name="Fast Preview",
        description="Disable the armature modifier, draw the tree as its bounds and the bones as wire, for fast "
        "playback",
        default=False, update=update_tree,
    )  # fmt: skip
    frameRate: FloatProperty(
        name="Animation Speed", description="Adjust speed of animation, relative to scene frame rate", min=0.001,
        default=1, update=update_tree,
    )  # fmt: skip
    loopFrames: IntProperty(
        name="Loop Frames", description="Number of frames to make the animation loop for, zero is disabled", min=0,
        default=0, update=update_tree,
    )  # fmt: skip
    wind: FloatProperty(
        name="Overall Wind Strength", description="The intensity of the wind to apply to the armature", default=1.0,
        update=update_tree,
    )  # fmt: skip
    gust: FloatProperty(
        name="Wind Gust Strength", description="The amount of directional movement (from the positive Y direction)",
        default=1.0, update=update_tree,
    )  # fmt: skip
    gustF: FloatProperty(
        name="Wind Gust Frequency", description="The frequency of directional movement", default=0.075,
        update=update_tree,
    )  # fmt: skip
    af1: FloatProperty(name="Amplitude", description="Multiplier for noise amplitude", default=1.0, update=update_tree)
    af2: FloatProperty(name="Frequency", description="Multiplier for noise frequency", default=1.0, update=update_tree)
    af3: FloatProperty(name="Randomness", description="Random offset in noise", default=4.0, update=update_tree)

    # Presets (UI state)
    presetName: StringProperty(
        name="Preset Name", description="The name of the preset to be saved", default="", subtype="FILE_NAME",
        update=no_update_tree,
    )  # fmt: skip
    limitImport: BoolProperty(
        name="Limit Import", description="Limit loaded presets to 2 levels and no leaves, for speed", default=False,
        update=no_update_tree,
    )  # fmt: skip
    overwrite: BoolProperty(
        name="Overwrite", description="When checked, overwrite existing preset files when saving", default=False,
        options={"SKIP_SAVE"}, update=no_update_tree,
    )  # fmt: skip

    @classmethod
    def generation_names(cls) -> list[str]:
        """Names of the properties that shape the tree (what presets and stored trees hold)."""
        names = TreeProperties.__annotations__  # the mixin's own; operators add only UI state
        return [n for n in names if n not in cls.UI_ONLY and n not in cls.SCENE_BOUND]

    @classmethod
    def stored_names(cls) -> list[str]:
        """What a generated tree stores for re-editing: the generation settings and the leaf object."""
        return [*cls.generation_names(), *cls.SCENE_BOUND]
