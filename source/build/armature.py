# SPDX-License-Identifier: GPL-3.0-or-later

"""The armature: one bone per curve segment (or per Bone Step segments); the leaves follow the branch bones."""

import random
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

import bpy
from bpy.types import (
    Armature,
    ArmatureModifier,
    BezierSplinePoint,
    Context,
    Curve,
    EditBone,
    Object,
    SplineBezierPoints,
)

from ..model.curve_data import CurveData
from ..model.geometry import Angles
from ..model.leaves import LeafSet
from ..model.params import TreeParams
from ..model.stem import BoneLink, BoneName
from ..model.tree import GrownTree
from ..settings import SettingsError
from .node_wind import WindJoints
from .objects import ObjectFactory, VertexGroupWriter
from .wind import BranchSway, LeafFlutter, WindAnimator, WindModel


class BoneGeometry:
    """Heads, tails and radii of the branch bones in the order they are made, written in one pass each.

    Each write to an EditBone's head, tail, radius or envelope costs Blender time in proportion to the
    number of bones (measured at 32,000 bones: about 0.57 ms per write); foreach_set writes all bones at about
    0.1 µs each. The armature must hold only these bones, in this order.
    """

    def __init__(self) -> None:
        self.heads: list[float] = []
        self.tails: list[float] = []
        self.head_radii: list[float] = []
        self.tail_radii: list[float] = []

    def add(self, head: BezierSplinePoint, tail: BezierSplinePoint) -> None:
        """The next bone runs from curve point `head` to curve point `tail`."""
        self.heads.extend(head.co.to_tuple())
        self.tails.extend(tail.co.to_tuple())
        self.head_radii.append(head.radius)
        self.tail_radii.append(tail.radius)

    def write(self, armature: Armature, envelope: float) -> None:
        """Set every bone's head, tail, radii and envelope distance (after parenting and connecting them)."""
        bones = armature.edit_bones
        if len(bones) != len(self.head_radii):
            raise RuntimeError(f"{len(bones)} bones for the geometry of {len(self.head_radii)}")
        bones.foreach_set("head", self.heads)
        bones.foreach_set("tail", self.tails)
        bones.foreach_set("head_radius", self.head_radii)
        bones.foreach_set("tail_radius", self.tail_radii)
        bones.foreach_set("envelope_distance", [envelope] * len(self.head_radii))


class RigSize:
    """How many bones the rig would have, and whether that is reasonable.

    Creating a bone costs Blender time in proportion to the bones already made (edit_bones.new, measured), so a
    rig's build time grows with the square of its bone count: 79,648 bones took 415 s. Joint Levels and Joint
    Length with Make Mesh keep the count down; above WARN_BONES the operator warns, above MAX_BONES it refuses.
    """

    WARN_BONES = 10_000
    MAX_BONES = 40_000
    MEASURED = (79_648, 415.0)  # bones, seconds
    ADVICE = (
        "turn on Make Mesh and lower Joint Levels or raise Joint Length on the Armature page, "
        "or use Wind without the rig"
    )

    @staticmethod
    def bones(params: TreeParams, curve: CurveData, grown: GrownTree) -> int:
        """The bones the rig makes for this tree (the node wind's joints are the same)."""
        return int(WindJoints(params, curve, grown).count.sum())

    @classmethod
    def seconds(cls, bones: int) -> float:
        """About how long Blender takes to create that many bones, from the measured quadratic cost."""
        measured_bones, measured_seconds = cls.MEASURED
        return measured_seconds * (bones / measured_bones) ** 2

    @classmethod
    def check(cls, bones: int) -> str | None:
        """A warning above WARN_BONES; raises SettingsError above MAX_BONES."""
        if bones > cls.MAX_BONES:
            seconds = cls.seconds(bones)
            raise SettingsError(
                f"The armature rig would have {bones:,} bones (limit {cls.MAX_BONES:,}; "
                f"about {seconds:.0f} s to build): {cls.ADVICE}"
            )
        if bones > cls.WARN_BONES:
            seconds = cls.seconds(bones)
            return f"The armature rig has {bones:,} bones; building it takes about {seconds:.0f} s: {cls.ADVICE}"
        return None


class ArmatureBuilder:
    """Builds the armature that deforms the tree curve, the leaves and the skin mesh."""

    ROLE = "treeArm"
    DATA_NAME = "tree"
    MODIFIER = "windSway"
    # Every bone is in this bone collection, hidden unless Fast Preview shows the armature instead of the tree
    BONE_COLLECTION = "Sapling Bones"
    # Branch bones deform the curve through their envelopes, kept tight around the bone
    BRANCH_ENVELOPE = 0.001

    def __init__(self, params: TreeParams, rng: random.Random, objects: ObjectFactory, context: Context) -> None:
        self.params = params
        self.rng = rng
        self.objects = objects
        self.context = context

    def build(
        self, root: Object, curve_ob: Object, grown: GrownTree, leaves: LeafSet | None, leaves_ob: Object | None
    ) -> Object:
        """The armature object (the rig), a child of the root, with bones for the branches and wind.

        The bones deform the tree's curve source `curve_ob` (a legacy Curve, by bone envelopes on its points,
        as before) and the leaves (vertex groups). Switches the new armature into edit mode and back (see
        _editing). Draws from the rng only with Wind: two phase offsets per spline that gets bones, and two
        per leaf with Leaf Flutter. The bones are in a bone collection, hidden unless Fast Preview. The root
        stays the tree: a click on the branches selects it, and moving it moves the rig and all it deforms.
        """
        p = self.params
        armature = bpy.data.armatures.new(self.DATA_NAME)
        # Both are at the origin with no rotation while the tree is built, so no parent inverse is needed
        armature_ob = self.objects.new(self.ROLE, armature, parent=root)
        armature.display_type = "STICK"
        scene = self.context.scene
        fps = scene.render.fps / scene.render.fps_base  # type: ignore[union-attr]  # an operator context has a scene
        wind = WindAnimator(armature_ob, WindModel(p, fps)) if p.armature_animation else None

        # Curves have no vertex groups: the bone envelopes deform them
        modifier = self.deform(curve_ob, armature_ob, by_envelopes=True)
        modifier.use_apply_on_spline = True
        if p.preview_armature:
            modifier.show_viewport = False
            armature.display_type = "WIRE"
            # Drawn as its bounds, not hidden: a hidden root is deselected and left out of Move/Rotate/Scale
            root.display_type = "BOUNDS"
        if leaves_ob:
            self.deform(leaves_ob, armature_ob, by_envelopes=False)

        # Every bone goes into one bone collection, shown only when asked (Fast Preview). Hiding the bones, not
        # the armature object, keeps the armature an ordinary part of the tree; bones in no collection are shown.
        collection = armature.collections.new(self.BONE_COLLECTION)
        bones: dict[str, EditBone] = {}  # by name: Blender's own lookup by name costs more the more bones there are
        with self._editing(armature_ob):
            self._branch_bones(armature, bones, curve_ob.data, grown, wind)  # type: ignore[arg-type]  # the curve source of a rig is a legacy Curve
            for bone in bones.values():  # an EditBone is assigned at the same cost however many bones there are
                collection.assign(bone)
        collection.is_visible = p.preview_armature
        if leaves_ob:
            self._leaf_groups(set(bones), grown, leaves, leaves_ob, wind)  # type: ignore[arg-type]  # leaves_ob implies leaves
        if wind:
            wind.finish()

        for pose_bone in armature_ob.pose.bones:  # type: ignore[union-attr]  # an armature object has a pose
            pose_bone.rotation_mode = "XYZ"
        return armature_ob

    @classmethod
    def deform(cls, ob: Object, armature_ob: Object, by_envelopes: bool) -> ArmatureModifier:
        """An Armature modifier on ob: by bone envelopes, or by the vertex groups named after the bones."""
        modifier: ArmatureModifier = ob.modifiers.new(cls.MODIFIER, "ARMATURE")  # type: ignore[assignment]  # stub: new() returns the base class
        modifier.object = armature_ob
        modifier.use_bone_envelopes = by_envelopes
        modifier.use_vertex_groups = not by_envelopes
        return modifier

    @staticmethod
    def preview_with_skin_mesh(armature_ob: Object) -> None:
        """Fast Preview with Make Mesh: the skin mesh shows the tree, so the armature is hidden."""
        armature_ob.hide_viewport = True
        armature_ob.data.display_type = "STICK"  # type: ignore[union-attr]  # stub: Object.data is a union of all data types

    @contextmanager
    def _editing(self, armature_ob: Object) -> Iterator[None]:
        """Edit mode on the new armature alone; the selection and active object are restored after.

        mode_set works on the view layer's selection (a context override does not change that), so every
        other selected armature would enter edit mode too; the new armature is made the only selection.
        """
        objects = self.context.view_layer.objects  # type: ignore[union-attr]  # an operator context has a view layer
        previous_active = objects.active
        previous_selection = [ob for ob in objects if ob.select_get()]
        for ob in previous_selection:
            ob.select_set(False)
        armature_ob.select_set(True)
        objects.active = armature_ob
        try:
            self._switch_mode("EDIT")
            try:
                yield
            finally:
                self._switch_mode("OBJECT")
        finally:
            armature_ob.select_set(False)
            for ob in previous_selection:
                ob.select_set(True)
            objects.active = previous_active

    @staticmethod
    def _switch_mode(mode: Literal["EDIT", "OBJECT"]) -> None:
        if bpy.ops.object.mode_set(mode=mode) != {"FINISHED"}:
            raise RuntimeError(f"Could not switch the new armature to {mode} mode")

    def _branch_bones(
        self, armature: Armature, bones: dict[str, EditBone], curve: Curve, grown: GrownTree, wind: WindAnimator | None
    ) -> None:
        """Bones along each spline (Bone Step points per bone), chained, added to `bones`; with wind, each bone
        gets its sway."""
        p = self.params
        rng = self.rng
        geometry = BoneGeometry()
        for i, link, points in self._bone_splines(curve, grown):
            segments = len(points) - 1
            step = p.bone_step[grown.level_of(i)]

            if wind:
                spline_length = segments * ((points[0].co - points[1].co).length)
                offsets = (rng.uniform(0, Angles.TAU), rng.uniform(0, Angles.TAU))
                frequencies = wind.model.branch_frequencies(spline_length)

            bone: EditBone | None = None
            tail = 0
            for n in range(0, segments, step):
                previous = bone
                name = BoneName.of(i, n)
                bone = bones[name] = armature.edit_bones.new(name)
                tail = min(tail + step, segments)
                geometry.add(points[n], points[tail])
                if n == 0:
                    # the first bone hangs from the bone of the parent branch
                    if link.bone:
                        bone.parent = bones[link.bone]
                else:
                    bone.parent = previous
                    bone.use_connect = True

                if wind:
                    sway = wind.model.branch_amplitudes(points, n, tail, step, spline_length)
                    # the first two bones of every trunk hold the tree base still
                    if (link.bone == "") and (n <= step):
                        sway = (0, 0, 0, 0)
                    wind.add_branch_sway(name, BranchSway(sway, offsets, frequencies, wind.model.gust_frequency))
        geometry.write(armature, self.BRANCH_ENVELOPE)

    def _bone_splines(self, curve: Curve, grown: GrownTree) -> Iterator[tuple[int, BoneLink, SplineBezierPoints]]:
        """(spline index, bone link, points) of every spline that gets bones."""
        p = self.params
        # one walk over the splines: curve.splines[i] walks the spline list up to i
        for i, (link, spline) in enumerate(zip(grown.bone_map, curve.splines, strict=True)):
            # Joint Levels: deeper levels use their parent's bones
            if i >= grown.level_ends[p.bone_levels]:
                continue
            points = spline.bezier_points
            if len(points) > 1:  # a stem pruning removed has only its start point
                yield i, link, points

    def _leaf_groups(
        self, bones: set[str], grown: GrownTree, leaves: LeafSet, leaves_ob: Object, wind: WindAnimator | None
    ) -> None:
        """Each leaf follows the nearest existing branch bone through that bone's vertex group.

        With Leaf Animation and wind, the leaves also flutter (LeafFlutterNodes); each leaf draws its two
        noise offsets here, after all the branch bones' draws.
        """
        p = self.params
        bone_names = grown.bone_map.bones()
        size = leaves.verts_per_leaf
        randomness = p.leaf_wind[2]
        flutter = wind if p.leaf_animation else None
        groups: dict[str, list[int]] = {}
        for i, parent_bone in enumerate(leaves.parent_bones):
            parent = BoneName.rounded(parent_bone, p.leaf_bone_step)
            while parent not in bones:
                parent = bone_names[BoneName.spline(parent)]
            groups.setdefault(parent, []).extend(range(size * i, size * i + size))
        # two noise offsets per leaf, after all the branch bones' draws
        offsets = LeafFlutter.offsets(leaves, randomness, self.rng) if flutter else []

        VertexGroupWriter.assign(leaves_ob, groups)
        if flutter:
            LeafFlutter.add(leaves_ob, leaves, offsets, flutter.model)
