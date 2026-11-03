# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves and blossoms: grown in the model alone, or read from the generated tree."""

import random

import bpy
import numpy as np
from mathutils import Vector

from support.addon import Addon
from support.evaluated import Evaluated
from support.model import Model
from support.scene import Scene


class Foliage:
    """Leaves and blossoms: grown in the model alone, or read from the generated tree."""

    @staticmethod
    def blossoms_module():
        return Addon.module("model.blossoms")

    @staticmethod
    def grow(**changes):
        """The leaves and blossoms of a quaking aspen with leaves, grown in the model alone."""
        settings = Addon.resolve_preset("quaking_aspen.py")
        settings.update(levels=2, showLeaves=True, **changes)
        params = Model.params(settings)
        curve = Addon.module("model.curve_data").CurveData()
        rng = random.Random(params.seed)
        grown = Addon.module("model.tree").TreeGrower(params, rng).grow(curve, params.scale)
        return Addon.module("model.leaves").LeafGenerator(params, rng).generate(grown.sprouts)

    @staticmethod
    def blocks(leaf_set):
        """Each leaf's vertices as one bytes value (for comparing sets of leaves)."""
        per_leaf = leaf_set.vertices.reshape(leaf_set.count, -1)
        return [row.tobytes() for row in per_leaf]

    @staticmethod
    def positions(frame, armature_on=True):
        """The leaves' evaluated vertex positions at a frame (optionally without the Armature modifier, which is
        shown again after)."""
        leaves = bpy.data.objects["leaves"]
        armatures = [modifier for modifier in leaves.modifiers if modifier.type == "ARMATURE"]
        shown = [modifier.show_viewport for modifier in armatures]
        for modifier in armatures:
            modifier.show_viewport = armature_on
        try:
            return [Vector(co) for co in Evaluated.vertices("leaves", frame).tolist()]
        finally:
            for modifier, was_shown in zip(armatures, shown, strict=True):
                modifier.show_viewport = was_shown

    @staticmethod
    def normals(settings: dict) -> np.ndarray:
        """The unit face normal of every leaf of the generated tree."""
        Scene.generate(settings)
        mesh = bpy.data.objects["leaves"].data
        normals = np.zeros(len(mesh.polygons) * 3)
        mesh.polygons.foreach_get("normal", normals)
        return normals.reshape(-1, 3)
