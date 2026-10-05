# SPDX-License-Identifier: GPL-3.0-or-later

"""Make Mesh: the branches as a vertex skeleton with a Skin modifier, weighted to the rig or moved by the node wind."""

import bpy
import numpy as np
from bpy.types import Object, SkinModifier

from ..model.curve_data import CurveData
from ..model.params import TreeParams
from ..model.stem import BoneName
from ..model.tree import GrownTree
from .armature import ArmatureBuilder
from .node_wind import NodeWind, WindJoints
from .objects import ObjectFactory, VertexGroupWriter


class SkinSkeleton:
    """Vertices, edges, skin radii, roots and bone vertex groups of the skin mesh, for every spline at once.

    Per spline, in spline order (a stem pruning removed has no vertices): a joint vertex on the parent just before
    a split's point, the stem's first vertex (a stem continuing its parent's tip shares the parent's last vertex
    instead), then Resolution U vertices per segment. A vertex belongs to the bone of its segment, and the vertex
    before a segment's first sample to that segment's bone too; above the Joint Levels, to the nearest bone below.
    Bones are keyed as spline * POINT_SPAN + point, named by BoneName.
    """

    # A split's first vertex sits on its parent with this fraction of the split's radius
    SPLIT_JOINT_RADIUS = 0.75
    POINT_SPAN = 1 << 20  # more points than any spline has

    def __init__(self, params: TreeParams, curve: CurveData, grown: GrownTree) -> None:
        self.params = params
        self.flat = curve.flatten()
        self.res = params.res_u
        links = list(grown.bone_map)
        count = len(links)
        self.is_split = np.array([link.is_split for link in links], dtype=bool)
        self.is_end = np.array([link.is_end for link in links], dtype=bool)
        self.split_point = np.array([link.split_point for link in links], dtype=np.int64)
        self.parent = np.array([BoneName.spline(link.bone) if link.bone else -1 for link in links], dtype=np.int64)
        point = np.array([BoneName.point(link.bone) if link.bone else -1 for link in links], dtype=np.int64)
        self.bone_key = self.parent * self.POINT_SPAN + point  # the bone each spline hangs from
        level = np.minimum(np.searchsorted(np.array(grown.level_ends), np.arange(count), side="right"), 3)
        self.step = np.array(params.bone_step, dtype=np.int64)[level]
        self.inherited = np.arange(count) >= grown.level_ends[params.bone_levels]
        self.nearest_key = self._nearest_keys()
        # the vertex layout
        alive = self.flat.sizes >= 2
        self.segments = np.where(alive, self.flat.sizes - 1, 0)
        self.joint_extra = (alive & self.is_split).astype(np.int64)
        self.first_extra = (alive & ~self.is_end).astype(np.int64)
        vertices = self.joint_extra + self.first_extra + self.segments * self.res
        self.base = np.concatenate([[0], np.cumsum(vertices)[:-1]])
        self.first_index = self.base + self.joint_extra  # the first vertex (or the first sample when is_end)
        self.last_vertex = np.where(alive, self.base + vertices - 1, -1)
        self.verts = np.zeros((int(vertices.sum()), 3), dtype=np.float32)
        self.radii = np.zeros(len(self.verts), dtype=np.float32)
        self.roots = np.zeros(len(self.verts), dtype=bool)
        self.edges: list[np.ndarray] = []
        self.members: list[tuple[np.ndarray, np.ndarray]] = []  # (vertex indices, bone keys)
        self._first_vertices()
        self._samples()
        self._joint_vertices()

    def _nearest_keys(self) -> np.ndarray:
        """Per spline above the Joint Levels: the key of the bone it hangs from through its boneless ancestors, that
        is the bone of the nearest stem below with bones of its own (-1 for a spline with its own bones)."""
        keys = np.full(len(self.parent), -1, dtype=np.int64)
        splines = np.flatnonzero(self.inherited)
        attach = splines.copy()  # the stem on the way down whose parent has bones; roots always have bones
        climb = self.inherited[self.parent[attach]]
        while climb.any():
            attach[climb] = self.parent[attach[climb]]
            climb = self.inherited[self.parent[attach]]
        keys[splines] = self.bone_key[attach]
        return keys

    def _bezier(self, a: np.ndarray, t: np.ndarray) -> np.ndarray:
        """Points at parameters t of the segments starting at flat point indices a, in float32 as mathutils
        evaluates a cubic Bezier (coefficients rounded to float32, then four terms summed left to right)."""
        flat = self.flat
        u = 1.0 - t
        c = np.stack([u**3, 3.0 * t * u**2, 3.0 * t**2 * u, t**3], axis=1).astype(np.float32)[:, :, None]
        terms = c[:, 0] * flat.co[a] + c[:, 1] * flat.right[a]
        return (terms + c[:, 2] * flat.left[a + 1]) + c[:, 3] * flat.co[a + 1]

    def _first_vertices(self) -> None:
        """A skin root vertex at the start of every stem that does not continue its parent's tip."""
        splines = np.flatnonzero(self.first_extra > 0)
        at = self.first_index[splines]
        start = self.flat.start[splines]
        self.verts[at] = self.flat.co[start]
        self.radii[at] = self.flat.radius[start]
        self.roots[at] = True

    def _samples(self) -> None:
        """Resolution U vertices along every segment, their edges and their bones."""
        res = self.res
        segment_spline = np.repeat(np.arange(len(self.segments)), self.segments)
        segment = np.arange(len(segment_spline)) - np.repeat(np.cumsum(self.segments) - self.segments, self.segments)
        spline = np.repeat(segment_spline, res)
        n = np.repeat(segment, res)
        f = np.tile(np.arange(1, res + 1), len(segment_spline))
        index = self.first_index[spline] + self.first_extra[spline] + n * res + (f - 1)
        a = self.flat.start[spline] + n
        t = f / res
        self.verts[index] = self._bezier(a, t)
        radius = self.flat.radius.astype(np.float64)
        self.radii[index] = radius[a] + (radius[a + 1] - radius[a]) * t
        # each sample joins the vertex before it: for a continuation's first sample, the parent's last vertex
        continuation = self.is_end[spline] & (n == 0) & (f == 1)
        previous = np.where(continuation, self.last_vertex[self.parent[spline]], index - 1)
        self.edges.append(np.stack([previous, index], axis=1))
        own = segment_spline * self.POINT_SPAN + (segment // self.step[segment_spline]) * self.step[segment_spline]
        key = np.repeat(np.where(self.inherited[segment_spline], self.nearest_key[segment_spline], own), res)
        self.members.append((index, key))
        self.members.append((previous[~continuation], key[~continuation]))

    def _joint_vertices(self) -> None:
        """A split's extra vertex on its parent just before the split point, joined to the split's first vertex and
        in the parent's bone."""
        splines = np.flatnonzero(self.joint_extra > 0)
        at = self.base[splines]
        a = self.flat.start[self.parent[splines]] + self.split_point[splines]
        self.verts[at] = self._bezier(a, np.full(len(splines), 1 - 1 / (self.res + 1)))
        self.radii[at] = self.flat.radius[self.flat.start[splines]] * self.SPLIT_JOINT_RADIUS
        self.edges.append(np.stack([at, at + 1], axis=1))
        key = np.where(self.inherited[splines], self.nearest_key[splines], self.bone_key[splines])
        self.members.append((at, key))

    def all_edges(self) -> np.ndarray:
        """(E, 2) vertex indices, in the order of the vertex each edge leads to."""
        edges = np.concatenate(self.edges)
        return edges[np.argsort(edges[:, 1], kind="stable")]

    def groups(self) -> dict[str, list[int]]:
        """Vertex indices per bone name, bones in the order the segments first use them."""
        vertices = np.concatenate([v for v, _ in self.members])
        keys = np.concatenate([k for _, k in self.members])
        unique, first, inverse = np.unique(keys, return_index=True, return_inverse=True)
        by_first_use = np.argsort(first, kind="stable")
        rank = np.empty_like(by_first_use)
        rank[by_first_use] = np.arange(len(by_first_use))
        ids = rank[inverse]
        order = np.argsort(ids, kind="stable")
        counts = np.bincount(ids, minlength=len(unique))
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        names = [BoneName.of(int(k // self.POINT_SPAN), int(k % self.POINT_SPAN)) for k in unique[by_first_use]]
        sorted_vertices = vertices[order]
        return {name: sorted_vertices[starts[i] : starts[i] + counts[i]].tolist() for i, name in enumerate(names)}


class SkinMeshBuilder:
    """Samples every spline into skin vertices and edges, with one vertex group per bone."""

    ROLE = "treemesh"

    def __init__(self, params: TreeParams, objects: ObjectFactory) -> None:
        self.params = params
        self.objects = objects

    def build(
        self,
        root: Object,
        curve: CurveData,
        grown: GrownTree,
        armature_ob: Object | None,
        wind: tuple[Object, WindJoints] | None = None,
    ) -> Object:
        """The skin mesh object: under the rig (deformed by it), or under the root (moved by the node wind when
        `wind` gives the tree's curves and joints)."""
        skeleton = SkinSkeleton(self.params, curve, grown)
        return self._object(skeleton, root, armature_ob, wind)

    def _object(
        self, skeleton: SkinSkeleton, root: Object, armature_ob: Object | None, wind: tuple[Object, WindJoints] | None
    ) -> Object:
        """The mesh object from the skeleton, with vertex groups, the rig or the node wind, and the Skin modifier."""
        mesh = bpy.data.meshes.new(self.ROLE)
        # Part of the tree: under the rig that deforms it, or under the root
        ob = self.objects.new(self.ROLE, mesh, parent=armature_ob or root)
        edges = skeleton.all_edges()
        mesh.vertices.add(len(skeleton.verts))
        mesh.vertices.foreach_set("co", skeleton.verts.ravel())
        mesh.edges.add(len(edges))
        mesh.edges.foreach_set("vertices", edges.astype(np.int32).ravel())
        mesh.update()
        groups = skeleton.groups()
        VertexGroupWriter.assign(ob, groups)

        if armature_ob:
            ArmatureBuilder.deform(ob, armature_ob, by_envelopes=False)
        elif wind:
            curves_ob, joints = wind
            vertex_joints = np.zeros(len(skeleton.verts), dtype=np.int32)
            for name, indices in groups.items():  # a vertex in two groups follows the later one
                vertex_joints[indices] = joints.joint_of(name)
            NodeWind.follow(ob, curves_ob, vertex_joints)

        skin: SkinModifier = ob.modifiers.new("Skin", "SKIN")  # type: ignore[assignment]  # stub: new() returns the base class
        skin.use_smooth_shade = True
        if self.params.preview_armature:
            skin.show_viewport = False
        skin_data = mesh.skin_vertices[0].data
        skin_data.foreach_set("radius", np.repeat(skeleton.radii, 2))
        skin_data.foreach_set("use_root", skeleton.roots)
        return ob
