# SPDX-License-Identifier: GPL-3.0-or-later

"""Make Mesh: the branches as a vertex skeleton with a Skin modifier, weighted to the armature."""

import bpy
from mathutils import Vector

from ..model.geometry import BezierSegment
from ..model.stem import BoneName


class SkinMeshBuilder:
    """Samples every spline into skin vertices and edges, with one vertex group per bone."""

    ROLE = "treemesh"

    def __init__(self, params, objects):
        self.params = params
        self.objects = objects

    def build(self, tree, grown, armature_ob, bone_level_end):
        p = self.params
        curve = tree.data
        res = p.res_u
        links = grown.bone_map
        verts: list[Vector] = []
        edges = []
        roots = []
        radii = []
        groups: dict[str, list[int]] = {}
        last_verts: list[int] = []

        for i, spline in enumerate(curve.splines):
            link = links[i]
            points = spline.bezier_points
            step = p.bone_step[grown.level_of(i)]
            vindex = len(verts)
            p1 = points[0]

            # A split starts with an extra vertex on its parent, just before the split point
            if link.is_split:
                parent_points = curve.splines[BoneName.spline(link.bone)].bezier_points
                segment = BezierSegment.between(parent_points[link.split_point], parent_points[link.split_point + 1])
                verts.append(segment.point(1 - 1 / (res + 1)))
                roots.append(False)
                radii.append((p1.radius * 0.75, p1.radius * 0.75))
                edges.append([vindex, vindex + 1])
                vindex += 1

            if link.is_end:
                # a branch continuing its parent's tip shares the parent's last vertex
                parent_vertex = last_verts[BoneName.spline(link.bone)]
                vindex -= 1
            else:
                verts.append(p1.co)
                roots.append(True)
                radii.append((p1.radius, p1.radius))

            # Above the armature levels, vertices join the group of the nearest bone below
            inherited = i >= bone_level_end
            if inherited:
                index = i
                group = links[index].bone
                while group not in groups:
                    index = BoneName.spline(links[index].bone)
                    group = links[index].bone

            for n, p2 in enumerate(points[1:]):
                if not inherited:
                    group = BoneName.rounded(BoneName.of(i, n), step)
                    groups.setdefault(group, [])

                # the first vertex of a split belongs to the parent branch's bone
                if link.is_split and n == 0:
                    groups[group if inherited else link.bone].append(vindex - 1)

                segment = BezierSegment.between(p1, p2)
                for f in range(1, res + 1):
                    pos = f / res
                    radius = p1.radius + (p2.radius - p1.radius) * pos
                    verts.append(segment.point(pos))
                    roots.append(False)
                    radii.append((radius, radius))
                    if link.is_end and (n == 0) and (f == 1):
                        edges.append([parent_vertex, n * res + f + vindex])
                    else:
                        edges.append([n * res + f + vindex - 1, n * res + f + vindex])
                        groups[group].append(n * res + f + vindex - 1)

                groups[group].append(n * res + res + vindex)
                p1 = p2

            last_verts.append(len(verts) - 1)

        mesh = bpy.data.meshes.new(self.ROLE)
        # Part of the tree: under the armature that deforms it, or under the tree curve
        ob = self.objects.new(self.ROLE, mesh, parent=armature_ob or tree)
        mesh.from_pydata(verts, edges, ())
        for name, indices in groups.items():
            ob.vertex_groups.new(name=name).add(indices, 1.0, "ADD")

        if armature_ob:
            modifier = ob.modifiers.new("windSway", "ARMATURE")
            if p.preview_armature:
                armature_ob.hide_viewport = True
                armature_ob.data.display_type = "STICK"
            modifier.object = armature_ob
            modifier.use_bone_envelopes = False
            modifier.use_vertex_groups = True

        skin = ob.modifiers.new("Skin", "SKIN")
        skin.use_smooth_shade = True
        if p.preview_armature:
            skin.show_viewport = False
        skin_data = mesh.skin_vertices[0].data
        skin_data.foreach_set("radius", [r for pair in radii for r in pair])
        skin_data.foreach_set("use_root", roots)
        return ob
