# SPDX-License-Identifier: GPL-3.0-or-later

"""The pruning envelope shown with the tree."""

import bpy
from bpy.types import Object
from mathutils import Vector

from ..model.geometry import Bezier
from ..model.params import TreeParams
from .objects import ObjectFactory


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
