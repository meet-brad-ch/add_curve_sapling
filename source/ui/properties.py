# SPDX-License-Identifier: GPL-3.0-or-later

"""The operator's tree properties. Their names are the operator API and the preset keys."""

from dataclasses import dataclass

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

from ..model.geometry import CrownShape
from ..model.leaves import LeafShape
from ..model.params import BranchingMode
from ..settings import TreeSettings


@dataclass(frozen=True, slots=True)
class EnumItem:
    """One choice of an enum setting: the value stored, the name shown, and the tooltip."""

    identifier: str
    name: str
    description: str

    @property
    def item(self) -> tuple[str, str, str]:
        """The choice as Blender's EnumProperty takes it (Blender's API wants a tuple; nothing else uses it)."""
        return (self.identifier, self.name, self.description)

    @staticmethod
    def items(choices: list["EnumItem"]) -> list[tuple[str, str, str]]:
        """The choices as Blender's EnumProperty takes them."""
        return [choice.item for choice in choices]


class Choices:
    """Enum items of the tree properties."""

    SHAPES = [
        EnumItem("0", "Conical", ""),
        EnumItem("6", "Inverse Conical", ""),
        EnumItem("1", "Spherical", ""),
        EnumItem("2", "Hemispherical", ""),
        EnumItem("3", "Cylindrical", ""),
        EnumItem("4", "Tapered Cylindrical", ""),
        EnumItem("10", "Inverse Tapered Cylindrical", ""),
        EnumItem("5", "Flame", ""),
        EnumItem("7", "Tend Flame", ""),
        EnumItem(str(CrownShape.CUSTOM), "Custom Shape", ""),
    ]
    SECONDARY_SHAPES = [choice for choice in SHAPES if choice.identifier != str(CrownShape.CUSTOM)]
    HANDLES = [EnumItem("0", "Auto", "Smooth automatic handles"), EnumItem("1", "Vector", "Straight segments")]
    BRANCH_MODES = [
        EnumItem(BranchingMode.ORIGINAL, "Original", "Rotate around each branch"),
        EnumItem(
            BranchingMode.ROTATE, "Rotate", "Spread the branches evenly, pointing outward from the center of the tree"
        ),
        EnumItem(BranchingMode.RANDOM, "Random", "Choose a random point"),
    ]
    LEAF_SHAPES = [
        EnumItem(LeafShape.HEX, "Hexagonal", "Hexagonal leaf mesh"),
        EnumItem(LeafShape.RECT, "Rectangular", "Rectangular leaf mesh, for image textures"),
        EnumItem(LeafShape.INSTANCE_FACES, "Instance Faces", "Instance the leaf object on one face per leaf"),
        EnumItem(LeafShape.INSTANCE_POINTS, "Instance Points", "Instance the leaf object on one point per leaf"),
    ]
    PAGES = [
        EnumItem("0", "Geometry", "Tree shape, scale, curve settings and presets"),
        EnumItem("1", "Branch Radius", "Radius and taper of the branches"),
        EnumItem("2", "Branch Splitting", "Levels, splits and branch counts"),
        EnumItem("3", "Branch Growth", "Length, angles and curvature"),
        EnumItem("4", "Pruning", "Pruning envelope"),
        EnumItem("5", "Leaves", "Leaf shape and placement"),
        EnumItem("6", "Armature", "Armature rig and baked mesh"),
        EnumItem("7", "Animation", "Wind animation"),
    ]


class TreeProperties:
    """Mixin with the tree properties, for the Add Tree operator.

    Changing a generation property regenerates the tree; changing a page, preset name or other UI
    state does not (do_update is cleared and the operator passes through).
    """

    # Refers to an object in the scene: stored with a tree, never in presets.
    SCENE_BOUND = ["leafDupliObj"]
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
        name="Settings", description="Choose the settings to modify", items=EnumItem.items(Choices.PAGES), default="0",
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
        name="Handle Type", description="The type of handles used in the spline", items=EnumItem.items(Choices.HANDLES),
        default="0", update=update_tree,
    )  # fmt: skip
    shape: EnumProperty(
        name="Shape", description="The overall shape of the tree (Shape)", items=EnumItem.items(Choices.SHAPES),
        default="7", update=update_tree,
    )  # fmt: skip
    shapeS: EnumProperty(
        name="Secondary Branches Shape", description="The shape of secondary splits",
        items=EnumItem.items(Choices.SECONDARY_SHAPES), default="4", update=update_tree,
    )  # fmt: skip
    customShape: FloatVectorProperty(
        name="Custom Shape", description="Branch length of the custom shape at (Base, Middle, Middle Position, Top)",
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
        name="Ratio", description="The base radius (Ratio)", min=0.0, default=0.015, update=update_tree
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
        description="Power that gives the radius of a branch from the radius of the branch it grew from (RatioPower)",
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
        name="Auto Taper", description="Calculate the taper from the branch lengths", default=True,
        update=update_tree,
    )  # fmt: skip
    taper: FloatVectorProperty(
        name="Taper", description="The taper of the branches at each level (nTaper)", min=0.0, max=1.0,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip
    radiusTweak: FloatVectorProperty(
        name="Tweak Radius", description="Multiply the radius by this factor", min=0.0, max=1.0,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip

    # Branch splitting
    levels: IntProperty(
        name="Levels", description="Number of branch levels (Levels)", min=1, max=6, soft_max=4, default=3,
        update=update_tree,
    )  # fmt: skip
    trunks: IntProperty(
        name="Trunks", description="Number of trunks growing from one root, as a clump (bamboo)", min=1,
        soft_max=100, default=1, update=update_tree,
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
        name="Split Relative to Length", description="Split in proportion to the branch length", default=False,
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
        name="Branching Mode", description="Branching and rotation mode", items=EnumItem.items(Choices.BRANCH_MODES),
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
        description="Decrease of the Down Angle toward the end of the parent branch (negative values add random "
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
    bendV: FloatVectorProperty(
        name="Bend Variation",
        description="Maximum random sideways turn of a branch, in degrees. Each segment turns by a part of it. A "
        "segment that splits does not turn",
        default=[0, 0, 0, 0], size=4, min=0, max=360, update=update_tree,
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
        name="Use Parent Angle", description="Rotate the first-level branches to match the parent branch", default=True,
        update=update_tree,
    )  # fmt: skip

    # Pruning
    prune: BoolProperty(name="Prune", description="Prune the tree to the envelope", default=False, update=update_tree)
    pruneRatio: FloatProperty(
        name="Prune Ratio", description="Proportion of pruned length (PruneRatio)", min=0.0, max=1.0, default=1.0,
        update=update_tree,
    )  # fmt: skip
    pruneWidth: FloatProperty(
        name="Prune Width", description="The width of the envelope (PruneWidth)", min=0.0, default=0.4,
        update=update_tree,
    )  # fmt: skip
    pruneBase: FloatProperty(
        name="Prune Base Height", description="The height of the base of the envelope, limited by the Trunk Height",
        min=0.0, max=1.0, default=0.3, update=update_tree,
    )  # fmt: skip
    pruneWidthPeak: FloatProperty(
        name="Prune Width Peak",
        description="Fraction of envelope height where the maximum width occurs (PruneWidthPeak)",
        min=0.0, default=0.6, update=update_tree,
    )  # fmt: skip
    prunePowerHigh: FloatProperty(
        name="Prune Power High",
        description="Power that shapes the upper part of the envelope (PrunePowerHigh)",
        default=0.5, update=update_tree,
    )  # fmt: skip
    prunePowerLow: FloatProperty(
        name="Prune Power Low",
        description="Power that shapes the lower part of the envelope (PrunePowerLow)",
        default=0.001, update=update_tree,
    )  # fmt: skip

    # Leaves
    showLeaves: BoolProperty(name="Show Leaves", description="Show the leaves", default=False, update=update_tree)
    leafShape: EnumProperty(
        name="Leaf Shape", description="The shape of the leaves", items=EnumItem.items(Choices.LEAF_SHAPES),
        default=LeafShape.HEX, update=update_leaves,
    )  # fmt: skip
    leafDupliObj: StringProperty(
        name="Leaf Object", description="Object instanced as the leaf (Instance Faces and Instance Points)",
        default="", update=update_leaves,
    )  # fmt: skip
    leaves: IntProperty(
        name="Leaves",
        description="Maximum number of leaves per branch. Negative values grow a palmate fan of leaves from the "
        "branch tip",
        default=25, update=update_tree,
    )  # fmt: skip
    leafDist: EnumProperty(
        name="Leaf Distribution", description="How the leaves are spread along the branches",
        items=EnumItem.items(Choices.SECONDARY_SHAPES), default="6", update=update_tree,
    )  # fmt: skip
    leafDownAngle: FloatProperty(
        name="Leaf Down Angle", description="The angle between a new leaf and the branch it grew from", default=45,
        update=update_leaves,
    )  # fmt: skip
    leafDownAngleV: FloatProperty(
        name="Leaf Down Angle Variation",
        description="Decrease of the Leaf Down Angle toward the end of the parent branch (negative values add random "
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
        name="Leaf Scale", description="The scale of the whole leaf (LeafScale)", min=0.0, default=0.17,
        update=update_leaves,
    )  # fmt: skip
    leafScaleX: FloatProperty(
        name="Leaf Scale X", description="The scale of the leaf in its X direction (LeafScaleX)", min=0.0,
        default=1.0, update=update_leaves,
    )  # fmt: skip
    leafScaleT: FloatProperty(
        name="Leaf Scale Taper", description="Scale leaves toward the tip or base of the parent branch", min=-1.0,
        max=1.0, default=0.0, update=update_leaves,
    )  # fmt: skip
    leafScaleV: FloatProperty(
        name="Leaf Scale Variation", description="Random variation of the leaf scale", min=0.0, max=1.0, default=0.0,
        update=update_leaves,
    )  # fmt: skip
    bend: FloatProperty(
        name="Leaf Bend", description="How much the leaf bends (Bend)", min=0.0, max=1.0,
        default=0.0, update=update_leaves,
    )  # fmt: skip
    leafangle: FloatProperty(
        name="Leaf Angle", description="Leaf vertical attraction", default=0.0, update=update_leaves
    )
    leafMaterial: BoolProperty(
        name="Leaf Material",
        description="Give mesh leaves the Sapling Leaf material. Its Thin Wall shading lets light through the leaves, "
        "as through real ones",
        default=True, update=update_leaves,
    )  # fmt: skip
    horzLeaves: BoolProperty(
        name="Horizontal Leaves", description="Leaves face upwards", default=True, update=update_leaves
    )

    # Rig and baked mesh
    useRig: BoolProperty(
        name="Armature Rig",
        description="Generate an armature whose bones move the branches, one bone per Joint Length stem segments "
        "within the Joint Levels. With Wind, the wind animates the bones",
        default=False, update=update_tree,
    )  # fmt: skip
    makeMesh: BoolProperty(
        name="Make Mesh",
        description="Bake the branches into a plain mesh, weighted to the rig's bones, for export. The Bevel inputs "
        "are then fixed, Fast Preview shows the bounds, and playback is heavier (every vertex is deformed)",
        default=False, update=update_tree,
    )  # fmt: skip
    jointLevels: IntProperty(
        name="Joint Levels", description="Number of branch levels that get bones (joints) of their own. Deeper "
        "levels follow the nearest bone below them. 1 rigs the trunk, 2 adds its branches (0 is all levels)", min=0,
        default=2, update=update_tree,
    )  # fmt: skip
    jointStep: IntVectorProperty(
        name="Joint Length", description="Number of stem segments per bone (joint), per level", min=1,
        default=[1, 1, 1, 1], size=4, update=update_tree,
    )  # fmt: skip

    # Wind
    windAnim: BoolProperty(
        name="Wind",
        description="The branches sway in the wind, in Geometry Nodes or, with Armature Rig, on its bones",
        default=False, update=update_tree,
    )  # fmt: skip
    leafFlutter: BoolProperty(
        name="Leaf Flutter", description="Leaves flutter in the wind (with Wind), in Geometry Nodes", default=False,
        update=update_tree,
    )  # fmt: skip
    fastPreview: BoolProperty(
        name="Fast Preview",
        description="Fast playback. The branches are drawn as their curves, or with the rig the tree as its bounds "
        "and the bones as wire",
        default=False, update=update_tree,
    )  # fmt: skip
    animationSpeed: FloatProperty(
        name="Animation Speed", description="The speed of the animation, relative to the scene frame rate", min=0.001,
        default=1, update=update_tree,
    )  # fmt: skip
    loopFrames: IntProperty(
        name="Loop Frames", description="Number of frames after which the animation repeats (0: no loop)", min=0,
        default=0, update=update_tree,
    )  # fmt: skip
    windStrength: FloatProperty(
        name="Wind Strength", description="The intensity of the wind", default=1.0, update=update_tree,
    )  # fmt: skip
    gustStrength: FloatProperty(
        name="Gust Strength", description="The amount of directional movement (from the positive Y direction)",
        default=1.0, update=update_tree,
    )  # fmt: skip
    gustFrequency: FloatProperty(
        name="Gust Frequency", description="The frequency of directional movement", default=0.075,
        update=update_tree,
    )  # fmt: skip
    flutterStrength: FloatProperty(
        name="Flutter Strength", description="Multiplier for the leaves' noise amplitude", default=1.0,
        update=update_tree,
    )  # fmt: skip
    flutterSpeed: FloatProperty(
        name="Flutter Speed", description="Multiplier for the leaves' noise frequency", default=1.0, update=update_tree,
    )  # fmt: skip
    flutterRandomness: FloatProperty(
        name="Flutter Randomness", description="Random offset in the leaves' noise", default=4.0, update=update_tree,
    )  # fmt: skip

    # Presets (UI state)
    presetName: StringProperty(
        name="Preset Name", description="The name of the preset to save", default="", subtype="FILE_NAME",
        update=no_update_tree,
    )  # fmt: skip
    limitImport: BoolProperty(
        name="Limit Import", description="Limit loaded presets to 2 levels and no leaves, for speed", default=False,
        update=no_update_tree,
    )  # fmt: skip
    overwrite: BoolProperty(
        name="Overwrite", description="Overwrite an existing preset file with the same name", default=False,
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


class OldSettingNames:
    """The setting ids from before the rename (TreeSettings.RENAMED), so scripts calling the operator with them
    keep working. They are hidden and not saved; a value given under an old id moves to its new id."""

    HIDDEN = {"HIDDEN", "SKIP_SAVE"}

    useArm: BoolProperty(name="useArm", options=HIDDEN)
    armAnim: BoolProperty(name="armAnim", options=HIDDEN)
    previewArm: BoolProperty(name="previewArm", options=HIDDEN)
    armLevels: IntProperty(name="armLevels", options=HIDDEN)
    boneStep: IntVectorProperty(name="boneStep", size=4, options=HIDDEN)
    leafAnim: BoolProperty(name="leafAnim", options=HIDDEN)
    wind: FloatProperty(name="wind", options=HIDDEN)
    gust: FloatProperty(name="gust", options=HIDDEN)
    gustF: FloatProperty(name="gustF", options=HIDDEN)
    frameRate: FloatProperty(name="frameRate", options=HIDDEN)
    af1: FloatProperty(name="af1", options=HIDDEN)
    af2: FloatProperty(name="af2", options=HIDDEN)
    af3: FloatProperty(name="af3", options=HIDDEN)

    def forward_old_names(self) -> None:
        """Move values a script gave under old ids to the new ids; SettingsError when both disagree."""
        props = self.properties  # type: ignore[attr-defined]  # mixed into an Operator
        old = [name for name in TreeSettings.RENAMED if props.is_property_set(name)]
        if not old:
            return
        names = [*TreeSettings.RENAMED, *TreeSettings.RENAMED.values()]
        given = TreeSettings({n: TreeSettings.plain(getattr(self, n)) for n in names if props.is_property_set(n)})
        given.rename_keys()  # the same rules as for presets and stored trees
        for name in old:
            props.property_unset(name)  # the redo panel then works on the new id only
        for name, value in given.values.items():
            setattr(self, name, value)
