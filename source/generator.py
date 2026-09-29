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
from .model.leaves import LeafGenerator
from .model.params import TreeParams
from .model.tree import TreeGrower


class TreeResult:
    """The objects of one generated tree; `root` is the object the others hang from."""

    def __init__(self, tree, leaves, armature, skin_mesh, created):
        self.tree = tree
        self.leaves = leaves
        self.armature = armature
        self.skin_mesh = skin_mesh
        self.created = created

    @property
    def root(self):
        return self.armature or self.tree


class TreeGenerator:
    """Generates one tree from settings (anything with the operator's property names)."""

    def __init__(self, settings, context, collection=None):
        self.params = TreeParams(settings)
        self.context = context
        self.collection = collection or context.collection

    def generate(self):
        p = self.params
        # One random stream for the whole tree: the same seed gives the same tree
        rng = random.Random(p.seed)
        objects = ObjectFactory(self.collection)

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

        skin_ob = None
        if p.make_mesh:
            skin_ob = SkinMeshBuilder(p, objects).build(
                tree.data, grown, armature_ob, armatures.armature_level_end(grown)
            )

        if leaves_ob:
            leaf_builder.finish(leaves_ob, leaves)

        result = TreeResult(tree, leaves_ob, armature_ob, skin_ob, objects.created)
        MaterialLibrary().assign(result, p.leaf_material)
        return result
