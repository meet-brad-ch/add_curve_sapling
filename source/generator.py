# SPDX-License-Identifier: GPL-3.0-or-later

"""Generating a tree: grow the model, then build the Blender objects."""

import random
from collections.abc import Sequence
from math import copysign
from typing import Any

from bpy.types import Collection, Context, Object

from .build.armature import ArmatureBuilder, RigSize
from .build.envelope import EnvelopeBuilder
from .build.joint_proxy import JointProxy
from .build.leaf_object import LeafObjectBuilder
from .build.materials import MaterialLibrary
from .build.node_wind import NodeWind, WindJoints
from .build.objects import ObjectFactory
from .build.skin_mesh import SkinMeshBuilder
from .build.tree_root import CurveSource, TreeRootBuilder
from .build.wind import LeafFlutter
from .model.curve_data import CurveData
from .model.leaves import LeafGenerator, LeafSet, LeafShape
from .model.params import TreeParams
from .model.tree import GrownTree, TreeGrower


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
        result = TreeResult(objects)
        MaterialLibrary.assign(result, p)
        return result

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

        armature_ob = joints_ob = None
        joints = None
        if rig:
            joints_ob = JointProxy(p, objects).build(root, grown_curve, rig_joints)
            armature_ob = ArmatureBuilder(p, rng, objects, self.context).build(
                root, joints_ob, grown_curve, grown, leaf_set, leaves_ob
            )
        elif p.armature_animation:
            joints = self._node_wind(curves_ob, grown_curve, grown, rng, leaf_set, leaves_ob)
        root_builder.sweep(
            root, curves_ob, wind=joints is not None, preview=p.preview_armature and not rig, joints_ob=joints_ob
        )

        if p.make_mesh:
            wind = (curves_ob, joints) if joints is not None else None
            SkinMeshBuilder(p, objects).build(root, grown_curve, grown, armature_ob, wind)
            if armature_ob and p.preview_armature:
                ArmatureBuilder.preview_with_skin_mesh(armature_ob)

        if leaves_ob:
            leaf_builder.finish(leaves_ob, leaf_set)  # type: ignore[arg-type]  # leaves_ob implies leaf_set

    def _node_wind(
        self,
        curves_ob: Object,
        curve: CurveData,
        grown: GrownTree,
        rng: random.Random,
        leaf_set: LeafSet | None,
        leaves_ob: Object | None,
    ) -> WindJoints:
        """Wind without the rig: on the curves, then the leaves' flutter and their following, drawing from the rng
        in the rig's order (joint phases, then two offsets per leaf)."""
        p = self.params
        scene = self.context.scene
        fps = scene.render.fps / scene.render.fps_base  # type: ignore[union-attr]  # an operator context has a scene
        node_wind = NodeWind(p, rng, fps)
        joints = node_wind.build(curves_ob, curve, grown)
        if leaves_ob is not None and leaf_set is not None:
            if p.leaf_animation:
                offsets = LeafFlutter.offsets(leaf_set, p.leaf_wind[2], rng)
                LeafFlutter.add(leaves_ob, leaf_set, offsets, node_wind.model)
            NodeWind.follow(leaves_ob, curves_ob, joints.leaf_joints(leaf_set))
        return joints
