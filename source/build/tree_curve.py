# SPDX-License-Identifier: GPL-3.0-or-later

"""The tree curve object, the bulk writer that fills it, and the pruning envelope shown with it."""

import bpy
from bpy.types import Curve, Object
from mathutils import Vector

from ..model.curve_data import CurveData
from ..model.geometry import Bezier
from ..model.params import TreeParams
from .objects import ObjectFactory


class TreeCurveBuilder:
    """Creates the (still empty) curve that the branches grow into."""

    ROLE = "tree"

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self) -> Object:
        """The tree object: a 3D curve with the bevel and resolution of the params, no splines yet."""
        p = self.params
        curve = bpy.data.curves.new(self.ROLE, "CURVE")
        tree = self.objects.new(self.ROLE, curve)
        curve.dimensions = "3D"
        curve.fill_mode = "FULL"
        curve.bevel_depth = p.bevel_depth
        curve.bevel_resolution = p.bevel_res
        curve.resolution_u = p.res_u
        return tree


class CurveWriter:
    """Writes the grown curve into the empty tree curve: per spline one new(), one add() and one foreach_set per
    attribute. Writing point by point costs Blender time in proportion to the number of splines; this does not.

    foreach_set stores the values without recalculating handles, so the handles are the model's, exactly.
    """

    @staticmethod
    def write(source: CurveData, target: Curve) -> None:
        """Append every spline of `source` to `target`, in order, with the model's handles."""
        for spline in source.splines:
            spline.ensure_handles()
            points = target.splines.new(Bezier.SPLINE).bezier_points
            if len(spline.co) > 1:
                points.add(len(spline.co) - 1)
            points.foreach_set("handle_left_type", spline.h1)
            points.foreach_set("handle_right_type", spline.h2)
            points.foreach_set("co", [c for v in spline.co for c in v.to_tuple()])
            points.foreach_set("handle_left", [c for v in spline.left for c in v.to_tuple()])
            points.foreach_set("handle_right", [c for v in spline.right for c in v.to_tuple()])
            points.foreach_set("radius", spline.radius)


class EnvelopeBuilder:
    """Two profile curves (in the XZ and YZ planes) that show the pruning envelope.

    A guide, not part of the tree's look: hidden in viewports and renders after generation (Object Properties
    > Visibility shows it again).
    """

    ROLE = "envelope"
    POINTS = 128

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(self, tree: Object, scale: float) -> None:
        """The envelope object under the tree: two profiles from the tree top (at `scale`) down to the prune base."""
        p = self.params
        prune_base = p.prune_base_clamped
        curve = bpy.data.curves.new(self.ROLE, "CURVE")
        envelope = self.objects.new(self.ROLE, curve, parent=tree)
        envelope.hide_viewport = True
        envelope.hide_render = True
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
