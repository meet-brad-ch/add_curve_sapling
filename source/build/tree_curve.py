# SPDX-License-Identifier: GPL-3.0-or-later

"""The bulk writer of legacy curves (the rig's curve source), and the pruning envelope shown with the tree."""

import bpy
from bpy.types import Curve, Object
from mathutils import Vector

from ..model.curve_data import CurveData
from ..model.geometry import Bezier
from ..model.params import TreeParams
from .objects import ObjectFactory


class CurveWriter:
    """Writes the grown curve into the empty tree curve: per spline one new(), one add() and one foreach_set per
    attribute. Writing point by point costs Blender time in proportion to the number of splines; this does not.

    foreach_set stores the values without recalculating handles, so the handles are the model's, exactly.
    """

    @staticmethod
    def write(source: CurveData, target: Curve) -> None:
        """Append every spline of `source` to `target`, in order, with the model's handles."""
        flat = source.flatten()
        for a, b in zip(flat.start[:-1].tolist(), flat.start[1:].tolist(), strict=True):
            points = target.splines.new(Bezier.SPLINE).bezier_points
            if b - a > 1:
                points.add(b - a - 1)
            points.foreach_set("handle_left_type", flat.h1[a:b].tolist())
            points.foreach_set("handle_right_type", flat.h2[a:b].tolist())
            points.foreach_set("co", flat.co[a:b].ravel())
            points.foreach_set("handle_left", flat.left[a:b].ravel())
            points.foreach_set("handle_right", flat.right[a:b].ravel())
            points.foreach_set("radius", flat.radius[a:b])


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
