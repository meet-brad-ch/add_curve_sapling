# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree curve object, and the pruning envelope shown with it."""

from contextlib import contextmanager

import bpy
from mathutils import Vector

from ..model.geometry import Bezier


class TreeCurveBuilder:
    """Creates the (still empty) curve that the branches grow into."""

    ROLE = "tree"

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self):
        p = self.params
        curve = bpy.data.curves.new(self.ROLE, "CURVE")
        tree = self.objects.new(self.ROLE, curve)
        curve.dimensions = "3D"
        curve.fill_mode = "FULL"
        curve.bevel_depth = p.bevel_depth
        curve.bevel_resolution = p.bevel_res
        curve.resolution_u = p.res_u
        return tree

    @staticmethod
    @contextmanager
    def pruning_scratch(curve, needed):
        """A curve for the pruning search (stems grown and thrown away), removed afterwards; None if not needed."""
        if not needed:
            yield None
            return
        scratch = bpy.data.curves.new("sapling_prune_scratch", "CURVE")
        scratch.dimensions = curve.dimensions
        try:
            yield scratch
        finally:
            bpy.data.curves.remove(scratch)


class EnvelopeBuilder:
    """Two profile curves (in the XZ and YZ planes) that show the pruning envelope."""

    ROLE = "envelope"
    POINTS = 128

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self, tree, scale):
        p = self.params
        prune_base = p.prune_base_clamped
        curve = bpy.data.curves.new(self.ROLE, "CURVE")
        self.objects.new(self.ROLE, curve, parent=tree)
        for axis in (0, 1):
            spline = curve.splines.new(Bezier.SPLINE)
            point = spline.bezier_points[-1]
            point.co = Vector((0, 0, scale))
            (point.handle_right_type, point.handle_left_type) = (Bezier.VECTOR, Bezier.VECTOR)
            for c in range(self.POINTS):
                spline.bezier_points.add(1)
                point = spline.bezier_points[-1]
                ratio = (c + 1) / self.POINTS
                z = scale - scale * (1 - prune_base) * ratio
                width = scale * p.prune_width * p.envelope(ratio)
                point.co = Vector((width, 0, z) if axis == 0 else (0, width, z))
                (point.handle_right_type, point.handle_left_type) = (Bezier.VECTOR, Bezier.VECTOR)
