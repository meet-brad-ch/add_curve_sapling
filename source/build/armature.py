# SPDX-License-Identifier: GPL-3.0-or-later

"""The armature: one bone per joint (Joints: every Joint Length curve segments of the stems within the Joint
Levels). The bark follows through the joint proxy (JointProxy, deformed by vertex groups), the leaves through
their own vertex groups."""

import random
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import bpy
import numpy as np
from bpy.types import Armature, ArmatureModifier, Context, EditBone, Object

from ..model.joints import Joints, TreeWind
from ..model.leaves import LeafSet
from ..settings import SettingsError
from .build_params import BuildParams
from .leaf_object import FoliagePart
from .objects import ObjectFactory, VertexGroup, VertexGroupWriter
from .wind import LeafFlutter, WindAnimator


class BoneGeometry:
    """Heads and tails of the branch bones in the order they are made, written in one pass each.

    Each write to an EditBone's head or tail costs Blender time in proportion to the number of bones (measured
    at 32,000 bones: about 0.57 ms per write); foreach_set writes all bones at about 0.1 µs each. The armature
    must hold only these bones, in this order.
    """

    def __init__(self, heads: np.ndarray, tails: np.ndarray) -> None:
        self.heads = np.asarray(heads, dtype=np.float32)
        self.tails = np.asarray(tails, dtype=np.float32)

    def write(self, armature: Armature) -> None:
        """Set every bone's head and tail (after parenting and connecting them)."""
        bones = armature.edit_bones
        if len(bones) != len(self.heads):
            raise RuntimeError(f"{len(bones)} bones for the geometry of {len(self.heads)}")
        bones.foreach_set("head", self.heads.ravel())
        bones.foreach_set("tail", self.tails.ravel())


@dataclass(frozen=True, slots=True)
class Measurement:
    """A measured rig build: how many bones took how many seconds."""

    bones: int
    seconds: float


class RigSize:
    """How many bones the rig would have, and whether that is reasonable.

    Creating a bone costs Blender time in proportion to the bones already made (edit_bones.new, measured), so a
    rig's build time grows with the square of its bone count: 79,648 bones took 415 s. Joint Levels and Joint
    Length keep the count down; above WARN_BONES the operator warns, above MAX_BONES it refuses.
    """

    WARN_BONES = 10_000
    MAX_BONES = 40_000
    MEASURED = Measurement(79_648, 415.0)
    ADVICE = "Lower Joint Levels or raise Joint Length on the Armature page, or use Wind without the rig."

    @staticmethod
    def bones(joints: Joints) -> int:
        """The bones the rig makes for these joints (one per joint)."""
        return int(joints.count.sum())

    @classmethod
    def seconds(cls, bones: int) -> float:
        """About how long Blender takes to create that many bones, from the measured quadratic cost."""
        return cls.MEASURED.seconds * (bones / cls.MEASURED.bones) ** 2

    @classmethod
    def check(cls, bones: int) -> str | None:
        """A warning above WARN_BONES; raises SettingsError above MAX_BONES."""
        if bones > cls.MAX_BONES:
            seconds = cls.seconds(bones)
            raise SettingsError(
                f"The armature rig would have {bones:,} bones, above the limit of {cls.MAX_BONES:,} "
                f"(about {seconds:.0f} s to build). {cls.ADVICE}"
            )
        if bones > cls.WARN_BONES:
            seconds = cls.seconds(bones)
            return f"The armature rig has {bones:,} bones and takes about {seconds:.0f} s to build. {cls.ADVICE}"
        return None


class ArmatureBuilder:
    """Builds the armature that deforms the joint proxy (and so the bark), the leaves and a baked bark mesh."""

    ROLE = "treeArm"
    DATA_NAME = "tree"
    MODIFIER = "windSway"
    # Every bone is in this bone collection, hidden unless Fast Preview shows the armature instead of the tree
    BONE_COLLECTION = "Sapling Bones"

    def __init__(self, params: BuildParams, rng: random.Random, objects: ObjectFactory, context: Context) -> None:
        self.params = params
        self.rng = rng
        self.objects = objects
        self.context = context

    def build(
        self,
        root: Object,
        joints_ob: Object,
        joints: Joints,
        wind: TreeWind | None,
        foliage: list[FoliagePart],
    ) -> Object:
        """The armature object (the rig), a child of the root, with one bone per joint and, with `wind`, the sway
        F-curves of every bone.

        The bones deform the joint proxy `joints_ob` (vertex groups named after them; the root's sweep reads the
        posed curve from it) and the leaves and blossoms in `foliage` (vertex groups). Switches the new armature into
        edit mode and back (see _editing). Draws from the rng only with Leaf Flutter: two offsets per leaf (the
        leaves', then the blossoms'). The bones are in a bone
        collection, hidden unless Fast Preview. The root stays the tree: a click on the branches selects it, and
        moving it moves the rig and all it deforms.
        """
        p = self.params
        armature = bpy.data.armatures.new(self.DATA_NAME)
        # Both are at the origin with no rotation while the tree is built, so no parent inverse is needed
        armature_ob = self.objects.new(self.ROLE, armature, parent=root)
        armature.display_type = "STICK"
        animator = WindAnimator(armature_ob) if wind is not None else None

        modifier = self.deform(joints_ob, armature_ob)
        if p.preview_armature:
            modifier.show_viewport = False
            armature.display_type = "WIRE"
            # Drawn as its bounds, not hidden: a hidden root is deselected and left out of Move/Rotate/Scale
            root.display_type = "BOUNDS"
        for part in foliage:
            self.deform(part.ob, armature_ob)

        # Every bone goes into one bone collection, shown only when asked (Fast Preview). Hiding the bones, not
        # the armature object, keeps the armature an ordinary part of the tree; bones in no collection are shown.
        collection = armature.collections.new(self.BONE_COLLECTION)
        with self._editing(armature_ob):
            for bone in self._branch_bones(
                armature, joints
            ):  # an EditBone is assigned at the same cost however many bones there are
                collection.assign(bone)
        collection.is_visible = p.preview_armature
        if animator is not None and wind is not None:
            animator.add_joints(joints.names(), wind.sway)
        for part in foliage:
            self._leaf_groups(joints, part.leaves, part.ob, wind)
        if animator is not None:
            animator.finish()

        for pose_bone in armature_ob.pose.bones:  # type: ignore[union-attr]  # an armature object has a pose
            pose_bone.rotation_mode = "XYZ"
        return armature_ob

    @classmethod
    def deform(cls, ob: Object, armature_ob: Object) -> ArmatureModifier:
        """An Armature modifier on ob, deforming by the vertex groups named after the bones."""
        modifier: ArmatureModifier = ob.modifiers.new(cls.MODIFIER, "ARMATURE")  # type: ignore[assignment]  # stub: new() returns the base class
        modifier.object = armature_ob
        modifier.use_bone_envelopes = False
        modifier.use_vertex_groups = True
        return modifier

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

    @staticmethod
    def _branch_bones(armature: Armature, joints: Joints) -> list[EditBone]:
        """One bone per joint, in joint order, parented to the joint before it on its curve (connected) or to the
        joint its curve hangs from; the geometry written in one pass."""
        names = joints.names()
        parents = joints.bone_parents().tolist()
        connected = joints.connected().tolist()
        bones: list[EditBone] = []
        for name, parent, connect in zip(names, parents, connected, strict=True):
            bone = armature.edit_bones.new(name)
            if parent >= 0:
                bone.parent = bones[parent]
                bone.use_connect = connect
            bones.append(bone)
        BoneGeometry(joints.heads(), joints.tails()).write(armature)
        return bones

    def _leaf_groups(self, joints: Joints, leaves: LeafSet, leaves_ob: Object, wind: TreeWind | None) -> None:
        """Each leaf follows the joint it hangs from through that bone's vertex group.

        With Leaf Flutter and wind, the leaves also flutter (LeafFlutterNodes); each leaf draws its two noise
        offsets here, after all the joints' draws.
        """
        p = self.params
        flutter = wind if p.leaf_animation else None
        groups = self._grouped(joints.leaf_joint(leaves), joints.names(), leaves.verts_per_leaf)
        # two noise offsets per leaf, after all the joints' draws
        offsets = LeafFlutter.offsets(leaves, p.wind.flutter.randomness, self.rng) if flutter else []
        VertexGroupWriter.assign(leaves_ob, groups)
        if flutter is not None:
            LeafFlutter.add(leaves_ob, leaves, offsets, flutter.model)

    @staticmethod
    def _grouped(per_leaf: np.ndarray, names: list[str], size: int) -> list[VertexGroup]:
        """The leaves' vertex groups, one per joint that has leaves, in the order the joints first appear among
        the leaves; a leaf's `size` vertices are consecutive."""
        _, first = np.unique(per_leaf, return_index=True)
        per_vertex = np.repeat(per_leaf, size)
        groups = []
        for leaf in np.sort(first).tolist():
            joint = int(per_leaf[leaf])
            groups.append(VertexGroup(names[joint], np.flatnonzero(per_vertex == joint)))
        return groups
