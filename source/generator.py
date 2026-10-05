# SPDX-License-Identifier: GPL-3.0-or-later

"""Generating a tree: grow the model, then build the Blender objects."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from math import copysign
from typing import Any

from bpy.types import Collection, Context, Object

from .build.armature import ArmatureBuilder, RigSize
from .build.bake import BarkBake
from .build.build_params import BuildParams
from .build.envelope import EnvelopeBuilder
from .build.joint_proxy import JointProxy
from .build.leaf_object import BlossomObjectBuilder, FoliagePart, LeafObjectBuilder
from .build.materials import MaterialLibrary
from .build.node_wind import NodeWind
from .build.objects import ObjectFactory
from .build.tree_record import TreeRecord
from .build.tree_root import CurveSource, TreeRootBuilder
from .build.wind import LeafFlutter
from .model.curve_data import CurveData
from .model.joints import Joints, TreeWind
from .model.leaves import LeafGenerator, LeafShape
from .model.params import TreeParams, WindParams
from .model.tree import GrownTree, TreeGrower
from .model.wind_model import WindModel
from .settings import TreeSettings


class TreeResult:
    """The objects of one generated tree, by role; `root` is the tree (the mesh that draws the bark), which the
    others hang from."""

    def __init__(self, objects: ObjectFactory) -> None:
        self.objects = objects
        self.roles = objects.roles

    @property
    def root(self) -> Object:
        """The tree: every other part hangs from it, the rig too (so a click on the branches selects the whole
        tree)."""
        return self.roles[TreeRootBuilder.ROLE]

    def role(self, name: str) -> Object | None:
        """The object with this role, or None when this tree has none (e.g. no leaves)."""
        return self.roles.get(name)


@dataclass(frozen=True, slots=True)
class GrownLeaves:
    """The generated leaves and blossoms, each with its object (None for a part the tree does not have: no
    blossoms, or no leaves left when every position is a blossom)."""

    leaves: FoliagePart | None
    blossoms: FoliagePart | None

    @property
    def parts(self) -> list[FoliagePart]:
        """The parts the tree has: the leaves, then the blossoms."""
        return [part for part in [self.leaves, self.blossoms] if part is not None]


@dataclass(frozen=True, slots=True)
class Movers:
    """What moves the bark: the rig (its armature and the joint proxy the bones deform) or the wind curves."""

    armature_ob: Object | None
    joints_ob: Object | None
    wind_ob: Object | None


class TreeGenerator:
    """Generates one tree from settings (anything with the operator's property names)."""

    def __init__(self, settings: Any, context: Context, collections: Sequence[Collection]) -> None:
        self.params = TreeParams(settings)
        self.wind_params = WindParams(settings, self.params)
        self.build_params = BuildParams(settings, self.params, self.wind_params)
        self.context = context
        self.collections = collections
        self.warnings: list[str] = []  # for the operator to report (the tree is still built)

    def generate(self, stored: TreeSettings) -> TreeResult:
        """Build the tree and store `stored` (the settings it was made with) on it; if anything fails, remove
        what was created and re-raise."""
        p = self.params
        if p.leaves and p.leaf_shape in LeafShape.INSTANCED:
            LeafObjectBuilder.instance_object(self.build_params)  # fail before anything is created
        objects = ObjectFactory(self.collections)
        try:
            self._build(objects)
            result = TreeResult(objects)
            TreeRecord.tag(result, stored)
        except BaseException:
            objects.discard()
            raise
        return result

    def _build(self, objects: ObjectFactory) -> None:
        p = self.params
        b = self.build_params
        # One random stream for the whole tree: the same seed gives the same tree
        rng = random.Random(p.seed)
        root_builder = TreeRootBuilder(b, objects)
        root = root_builder.build()
        scale = p.scale + rng.uniform(-p.scale_v, p.scale_v)
        scale += copysign(1e-6, scale)  # never exactly zero
        if p.prune:
            EnvelopeBuilder(p, objects).build(root, scale)

        # The model grows in memory (every write O(1)); the curves are then written to Blender in bulk
        grown_curve = CurveData()
        grown = TreeGrower(p, rng).grow(grown_curve, scale)
        joints = self._joints(grown_curve, grown)
        curves_ob = CurveSource(b, objects).build(grown_curve, root)
        leaves = self._leaves(rng, grown, root, objects)
        movers = self._movers(root, curves_ob, joints, rng, leaves, objects)
        preview = b.preview_armature and not b.use_armature
        root_builder.sweep(root, curves_ob, movers.wind_ob, preview, movers.joints_ob)

        MaterialLibrary.assign(TreeResult(objects), b)  # before a bake: the baked mesh keeps the sweep's material
        if b.make_mesh:
            BarkBake(b, self.context).bake(root, curves_ob, joints, movers.armature_ob, movers.wind_ob)
        if leaves is not None and leaves.leaves is not None:
            LeafObjectBuilder(b, objects).finish(leaves.leaves.ob, leaves.leaves.leaves)

    def _joints(self, curve: CurveData, grown: GrownTree) -> Joints | None:
        """The joints the rig or the node wind needs (none for a still tree without a rig); a big rig warns."""
        b = self.build_params
        if not (b.use_armature or b.armature_animation):
            return None
        joints = Joints(self.wind_params, curve, grown)
        if b.use_armature:
            warning = RigSize.check(RigSize.bones(joints))
            if warning:
                self.warnings.append(warning)
        return joints

    def _leaves(self, rng: random.Random, grown: GrownTree, root: Object, objects: ObjectFactory) -> GrownLeaves | None:
        """The leaves and blossoms with their objects (None without leaves); the leaves draw from the rng after the
        tree. The leaves object is left out only when every leaf position is a blossom."""
        if not self.params.leaves:
            return None
        foliage = LeafGenerator(self.params, rng).generate(grown.sprouts)
        leaves = None
        if foliage.leaves.count or foliage.blossoms is None:
            leaves = FoliagePart(
                foliage.leaves, LeafObjectBuilder(self.build_params, objects).build(foliage.leaves, root)
            )
        blossoms = None
        if foliage.blossoms is not None:
            ob = BlossomObjectBuilder(self.build_params, objects).build(foliage.blossoms, root)
            blossoms = FoliagePart(foliage.blossoms, ob)
        return GrownLeaves(leaves, blossoms)

    def _movers(
        self,
        root: Object,
        curves_ob: Object,
        joints: Joints | None,
        rng: random.Random,
        leaves: GrownLeaves | None,
        objects: ObjectFactory,
    ) -> Movers:
        """The rig (bones through the joint proxy) or the wind curves, with the leaves following them.

        The rng is drawn in the rig's order: the joints' phases (two per curve with joints), then two flutter
        offsets per leaf (the leaves', then the blossoms').
        """
        b = self.build_params
        if joints is None:
            return Movers(None, None, None)
        foliage = leaves.parts if leaves is not None else []
        if b.use_armature:
            wind = self._wind(joints, rng) if b.armature_animation else None
            joints_ob = JointProxy(objects).build(root, joints)
            builder = ArmatureBuilder(b, rng, objects, self.context)
            return Movers(builder.build(root, joints_ob, joints, wind, foliage), joints_ob, None)
        wind = self._wind(joints, rng)  # without the rig, the joints are there for the wind
        wind_ob = NodeWind(b, objects).build(root, curves_ob, joints, wind)
        for part in foliage:
            if b.leaf_animation:
                offsets = LeafFlutter.offsets(part.leaves, self.wind_params.flutter.randomness, rng)
                LeafFlutter.add(part.ob, part.leaves, offsets, wind.model)
            NodeWind.follow(part.ob, wind_ob, joints.leaf_joints(part.leaves))
        return Movers(None, None, wind_ob)

    def _wind(self, joints: Joints, rng: random.Random) -> TreeWind:
        """The wind's numbers and every joint's sway (drawing two phases per curve with joints)."""
        model = WindModel(self.wind_params, self._fps())
        return TreeWind(model, joints.sway(model, rng))

    def _fps(self) -> float:
        """The scene's frame rate, which the wind's timing is relative to."""
        scene = self.context.scene
        return scene.render.fps / scene.render.fps_base  # type: ignore[union-attr]  # an operator context has a scene
