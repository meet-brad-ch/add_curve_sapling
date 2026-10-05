# SPDX-License-Identifier: GPL-3.0-or-later

"""Generating a tree: grow the model, then build the Blender objects."""

import random
from collections.abc import Sequence
from math import copysign
from typing import Any

from bpy.types import Collection, Context, Object

from .build.armature import ArmatureBuilder, RigSize
from .build.bake import BarkBake
from .build.envelope import EnvelopeBuilder
from .build.joint_proxy import JointProxy
from .build.leaf_object import LeafObjectBuilder
from .build.materials import MaterialLibrary
from .build.node_wind import NodeWind, WindJoints
from .build.objects import ObjectFactory
from .build.tree_root import CurveSource, TreeRootBuilder
from .build.wind import LeafFlutter
from .model.curve_data import CurveData
from .model.leaves import LeafGenerator, LeafSet, LeafShape
from .model.params import TreeParams
from .model.tree import TreeGrower


class TreeResult:
    """The objects of one generated tree, by role; `root` is the tree (the mesh that draws the bark), which the
    others hang from."""

    def __init__(self, objects: ObjectFactory) -> None:
        self.objects = objects
        self.roles = objects.roles

    @property
    def tree(self) -> Object:
        """The tree object (the root)."""
        return self.roles[TreeRootBuilder.ROLE]

    @property
    def root(self) -> Object:
        """The tree: every other part hangs from it, the rig too (so a click on the branches selects the whole
        tree)."""
        return self.tree

    def role(self, name: str) -> Object | None:
        """The object with this role, or None when this tree has none (e.g. no leaves)."""
        return self.roles.get(name)


class TreeGenerator:
    """Generates one tree from settings (anything with the operator's property names)."""

    def __init__(self, settings: Any, context: Context, collections: Sequence[Collection]) -> None:
        self.params = TreeParams(settings)
        self.context = context
        self.collections = collections
        self.warnings: list[str] = []  # for the operator to report (the tree is still built)

    def generate(self) -> TreeResult:
        """Build the tree; if anything fails, remove what was created and re-raise."""
        p = self.params
        if p.leaves and p.leaf_shape in LeafShape.INSTANCED:
            LeafObjectBuilder.instance_object(p)  # fail before anything is created
        objects = ObjectFactory(self.collections)
        try:
            self._build(objects)
        except BaseException:
            objects.discard()
            raise
        return TreeResult(objects)

    def _build(self, objects: ObjectFactory) -> None:
        p = self.params
        # One random stream for the whole tree: the same seed gives the same tree
        rng = random.Random(p.seed)
        root_builder = TreeRootBuilder(p, objects)
        root = root_builder.build()
        scale = p.scale + rng.uniform(-p.scale_v, p.scale_v)
        scale += copysign(1e-6, scale)  # never exactly zero
        if p.prune:
            EnvelopeBuilder(p, objects).build(root, scale)

        # The model grows in memory (every write O(1)); the curves are then written to Blender in bulk
        grown_curve = CurveData()
        grown = TreeGrower(p, rng).grow(grown_curve, scale)
        rig = p.use_armature
        rig_joints = None
        if rig:
            rig_joints = WindJoints(p, grown_curve, grown)
            warning = RigSize.check(RigSize.bones(rig_joints))
            if warning:
                self.warnings.append(warning)
        curves_ob = CurveSource(p, objects).build(grown_curve, root)

        leaf_set = leaves_ob = None
        leaf_builder = LeafObjectBuilder(p, objects)
        if p.leaves:
            leaf_set = LeafGenerator(p, rng).generate(grown.sprouts)
            leaves_ob = leaf_builder.build(leaf_set, root)

        armature_ob = joints_ob = wind_ob = None
        joints = None
        if rig_joints is not None:
            joints_ob = JointProxy(p, objects).build(root, grown_curve, rig_joints)
            armature_ob = ArmatureBuilder(p, rng, objects, self.context).build(
                root, joints_ob, grown_curve, grown, leaf_set, leaves_ob
            )
        elif p.armature_animation:
            joints = WindJoints(p, grown_curve, grown)
            wind_ob = self._node_wind(root, curves_ob, joints, objects, rng, leaf_set, leaves_ob)
        root_builder.sweep(root, curves_ob, wind_ob, preview=p.preview_armature and not rig, joints_ob=joints_ob)

        MaterialLibrary.assign(TreeResult(objects), p)  # before a bake: the baked mesh keeps the sweep's material
        if p.make_mesh:
            bake_joints = rig_joints or joints or WindJoints(p, grown_curve, grown)
            BarkBake(p, self.context).bake(root, curves_ob, bake_joints, armature_ob, wind_ob)

        if leaves_ob:
            leaf_builder.finish(leaves_ob, leaf_set)  # type: ignore[arg-type]  # leaves_ob implies leaf_set

    def _node_wind(
        self,
        root: Object,
        curves_ob: Object,
        joints: WindJoints,
        objects: ObjectFactory,
        rng: random.Random,
        leaf_set: LeafSet | None,
        leaves_ob: Object | None,
    ) -> Object:
        """Wind without the rig: the wind curves under the root, then the leaves' flutter and their following,
        drawing from the rng in the rig's order (joint phases, then two offsets per leaf); returns the wind curves."""
        p = self.params
        scene = self.context.scene
        fps = scene.render.fps / scene.render.fps_base  # type: ignore[union-attr]  # an operator context has a scene
        node_wind = NodeWind(p, rng, fps, objects)
        wind_ob = node_wind.build(root, curves_ob, joints)
        if leaves_ob is not None and leaf_set is not None:
            if p.leaf_animation:
                offsets = LeafFlutter.offsets(leaf_set, p.leaf_wind[2], rng)
                LeafFlutter.add(leaves_ob, leaf_set, offsets, node_wind.model)
            NodeWind.follow(leaves_ob, wind_ob, joints.leaf_joints(leaf_set))
        return wind_ob
