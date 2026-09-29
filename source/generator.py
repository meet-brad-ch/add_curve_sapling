# SPDX-License-Identifier: GPL-3.0-or-later

"""Generating a tree: grow the model, then build the Blender objects."""

import random
from collections.abc import Sequence
from math import copysign
from typing import Any

from bpy.types import Collection, Context, Object

from .build.armature import ArmatureBuilder
from .build.leaf_object import LeafObjectBuilder
from .build.materials import MaterialLibrary
from .build.objects import ObjectFactory
from .build.skin_mesh import SkinMeshBuilder
from .build.tree_curve import EnvelopeBuilder, TreeCurveBuilder
from .model.leaves import LeafGenerator, LeafShape
from .model.params import TreeParams
from .model.tree import TreeGrower


class TreeResult:
    """The objects of one generated tree, by role; `root` is the object the others hang from."""

    def __init__(self, objects: ObjectFactory) -> None:
        self.objects = objects
        self.roles = objects.roles

    @property
    def tree(self) -> Object:
        """The tree curve object."""
        return self.roles[TreeCurveBuilder.ROLE]

    @property
    def root(self) -> Object:
        """The armature object when the tree has one, else the tree curve."""
        return self.roles.get(ArmatureBuilder.ROLE, self.tree)

    def role(self, name: str) -> Object | None:
        """The object with this role, or None when this tree has none (e.g. no leaves)."""
        return self.roles.get(name)


class TreeGenerator:
    """Generates one tree from settings (anything with the operator's property names)."""

    def __init__(self, settings: Any, context: Context, collections: Sequence[Collection]) -> None:
        self.params = TreeParams(settings)
        self.context = context
        self.collections = collections

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
        tree = TreeCurveBuilder(p, objects).build()
        scale = p.scale + rng.uniform(-p.scale_v, p.scale_v)
        scale += copysign(1e-6, scale)  # never exactly zero
        if p.prune:
            EnvelopeBuilder(p, objects).build(tree, scale)

        with TreeCurveBuilder.pruning_scratch(tree.data, p.prune) as scratch:  # type: ignore[arg-type]  # stub: Object.data is a union of all data types
            grown = TreeGrower(p, rng).grow(tree.data, scratch, scale)  # type: ignore[arg-type]  # stub: Object.data is a union of all data types

        leaf_set = leaves_ob = None
        leaf_builder = LeafObjectBuilder(p, objects)
        if p.leaves:
            leaf_set = LeafGenerator(p, rng).generate(grown.sprouts)
            leaves_ob = leaf_builder.build(leaf_set, tree)

        armature_ob = None
        if p.use_armature:
            armature_ob = ArmatureBuilder(p, rng, objects, self.context).build(tree, grown, leaf_set, leaves_ob)

        if p.make_mesh:
            SkinMeshBuilder(p, objects).build(tree, grown, armature_ob)
            if armature_ob and p.preview_armature:
                ArmatureBuilder.preview_with_skin_mesh(armature_ob)

        if leaves_ob:
            leaf_builder.finish(leaves_ob, leaf_set)  # type: ignore[arg-type]  # leaves_ob implies leaf_set
