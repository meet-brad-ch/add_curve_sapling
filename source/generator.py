# SPDX-License-Identifier: GPL-3.0-or-later

"""Generating a tree: grow the model, then build the Blender objects."""

import random
from math import copysign

import bpy

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

    def __init__(self, objects):
        self.objects = objects
        self.roles = objects.roles

    @property
    def tree(self):
        return self.roles[TreeCurveBuilder.ROLE]

    @property
    def root(self):
        return self.roles.get(ArmatureBuilder.ROLE, self.tree)

    def role(self, name):
        """The object with this role, or None when this tree has none (e.g. no leaves)."""
        return self.roles.get(name)


class TreeGenerator:
    """Generates one tree from settings (anything with the operator's property names)."""

    def __init__(self, settings, context, collections):
        self.params = TreeParams(settings)
        self.context = context
        self.collections = collections

    def generate(self):
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
        MaterialLibrary().assign(result, p)
        return result

    def _build(self, objects):
        p = self.params
        # One random stream for the whole tree: the same seed gives the same tree
        rng = random.Random(p.seed)
        tree = TreeCurveBuilder(p, objects).build()
        scale = p.scale + rng.uniform(-p.scale_v, p.scale_v)
        scale += copysign(1e-6, scale)  # never exactly zero
        if p.prune:
            EnvelopeBuilder(p, objects).build(tree, scale)

        scratch = TreeCurveBuilder.scratch_like(tree.data) if p.prune else None
        try:
            grown = TreeGrower(p, rng).grow(tree.data, scratch, scale)
        finally:
            if scratch:
                bpy.data.curves.remove(scratch)

        leaves = leaves_ob = None
        leaf_builder = LeafObjectBuilder(p, objects)
        if p.leaves:
            leaves = LeafGenerator(p, rng).generate(grown.sprouts)
            leaves_ob = leaf_builder.build(leaves, tree)

        armature_ob = None
        armatures = ArmatureBuilder(p, rng, objects, self.context)
        if p.use_armature:
            armature_ob = armatures.build(tree, grown, leaves, leaves_ob)

        if p.make_mesh:
            SkinMeshBuilder(p, objects).build(tree, grown, armature_ob, armatures.armature_level_end(grown))
            if armature_ob and p.preview_armature:
                ArmatureBuilder.preview_with_skin_mesh(armature_ob)

        if leaves_ob:
            leaf_builder.finish(leaves_ob, leaves)
