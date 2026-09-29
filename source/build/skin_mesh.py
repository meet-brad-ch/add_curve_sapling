# SPDX-License-Identifier: GPL-3.0-or-later

"""Make Mesh: the branches as a vertex skeleton with a Skin modifier, weighted to the armature."""

import bpy
from mathutils import Vector

from ..model.geometry import BezierSegment
from ..model.stem import BoneName
from .armature import ArmatureBuilder


class SkinSkeleton:
    """Vertices, edges and bone vertex groups of the skin mesh, filled spline by spline."""

    def __init__(self):
        self.verts: list[Vector] = []
        self.edges: list[list[int]] = []
        self.roots: list[bool] = []
        self.radii: list[tuple[float, float]] = []
        self.groups: dict[str, list[int]] = {}
        self.last_verts: list[int] = []  # per spline, its last vertex

    def add_vertex(self, co, radius, root=False):
        self.verts.append(co)
        self.roots.append(root)
        self.radii.append((radius, radius))


class SkinMeshBuilder:
    """Samples every spline into skin vertices and edges, with one vertex group per bone."""

    ROLE = "treemesh"
    # A split's first vertex sits on its parent with this fraction of the split's radius
    SPLIT_JOINT_RADIUS = 0.75

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self, tree, grown, armature_ob):
        skeleton = SkinSkeleton()
        for i, spline in enumerate(tree.data.splines):
            self._add_spline(skeleton, tree.data, grown, i, spline)
        return self._object(skeleton, tree, armature_ob)

    def _add_spline(self, skeleton, curve, grown, i, spline):
        p = self.params
        res = p.res_u
        link = grown.bone_map[i]
        points = spline.bezier_points
        step = p.bone_step[grown.level_of(i)]
        vindex = len(skeleton.verts)
        p1 = points[0]

        # A split starts with an extra vertex on its parent, just before the split point
        if link.is_split:
            parent_points = curve.splines[BoneName.spline(link.bone)].bezier_points
            segment = BezierSegment.between(parent_points[link.split_point], parent_points[link.split_point + 1])
            skeleton.add_vertex(segment.point(1 - 1 / (res + 1)), p1.radius * self.SPLIT_JOINT_RADIUS)
            skeleton.edges.append([vindex, vindex + 1])
            vindex += 1

        if link.is_end:
            # a branch continuing its parent's tip shares the parent's last vertex
            parent_vertex = skeleton.last_verts[BoneName.spline(link.bone)]
            vindex -= 1
        else:
            skeleton.add_vertex(p1.co, p1.radius, root=True)

        # Above the armature levels, vertices join the group of the nearest bone below
        inherited = i >= grown.level_ends[p.bone_levels]
        if inherited:
            group = self._nearest_group(skeleton, grown.bone_map, i)

        for n, p2 in enumerate(points[1:]):
            if not inherited:
                group = BoneName.rounded(BoneName.of(i, n), step)
                skeleton.groups.setdefault(group, [])

            # the first vertex of a split belongs to the parent branch's bone
            if link.is_split and n == 0:
                skeleton.groups[group if inherited else link.bone].append(vindex - 1)

            segment = BezierSegment.between(p1, p2)
            for f in range(1, res + 1):
                pos = f / res
                skeleton.add_vertex(segment.point(pos), p1.radius + (p2.radius - p1.radius) * pos)
                if link.is_end and (n == 0) and (f == 1):
                    skeleton.edges.append([parent_vertex, n * res + f + vindex])
                else:
                    skeleton.edges.append([n * res + f + vindex - 1, n * res + f + vindex])
                    skeleton.groups[group].append(n * res + f + vindex - 1)

            skeleton.groups[group].append(n * res + res + vindex)
            p1 = p2

        skeleton.last_verts.append(len(skeleton.verts) - 1)

    @staticmethod
    def _nearest_group(skeleton, links, index):
        """The vertex group of the nearest spline down the tree that has its own bones."""
        group = links[index].bone
        while group not in skeleton.groups:
            index = BoneName.spline(links[index].bone)
            group = links[index].bone
        return group

    def _object(self, skeleton, tree, armature_ob):
        mesh = bpy.data.meshes.new(self.ROLE)
        # Part of the tree: under the armature that deforms it, or under the tree curve
        ob = self.objects.new(self.ROLE, mesh, parent=armature_ob or tree)
        mesh.from_pydata(skeleton.verts, skeleton.edges, (), shade_flat=False)  # edges only: nothing to shade
        for name, indices in skeleton.groups.items():
            ob.vertex_groups.new(name=name).add(indices, 1.0, "ADD")

        if armature_ob:
            ArmatureBuilder.deform(ob, armature_ob, by_envelopes=False)

        skin = ob.modifiers.new("Skin", "SKIN")
        skin.use_smooth_shade = True
        if self.params.preview_armature:
            skin.show_viewport = False
        skin_data = mesh.skin_vertices[0].data
        skin_data.foreach_set("radius", [r for pair in skeleton.radii for r in pair])
        skin_data.foreach_set("use_root", skeleton.roots)
        return ob
