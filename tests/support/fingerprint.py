# SPDX-License-Identifier: GPL-3.0-or-later

"""The golden trees' fingerprint of the scene."""

import hashlib
from typing import Any

import bpy

from support.evaluated import Evaluated


class Fingerprint:
    """A compact, order-sensitive summary of every object in the scene and its data (the golden trees)."""

    HANDLE_TYPE_NAMES = ["FREE", "AUTO", "VECTOR", "ALIGNED"]
    MODIFIER_PARAMS = {
        "FNGENERATOR": ("amplitude", "phase_offset", "phase_multiplier", "value_offset", "use_additive"),
        "NOISE": ("scale", "strength", "offset", "phase", "use_restricted_range", "frame_end", "blend_in", "blend_out"),
    }

    @classmethod
    def scene(cls) -> dict:
        """The fingerprint of every object of the scene, by name."""
        out = {}
        for ob in sorted(bpy.data.objects, key=lambda o: o.name):
            out[ob.name] = cls.object_entry(ob)
        return out

    @classmethod
    def object_entry(cls, ob: Any) -> dict:
        """One object's fingerprint: its kind, parent, modifiers, groups, data and node results."""
        entry: dict[str, Any] = {
            "type": ob.type,
            "parent": ob.parent.name if ob.parent else None,
            "modifiers": [m.type for m in ob.modifiers],
            "vertex_groups": cls.vertex_groups(ob),
            "instance_type": ob.instance_type,
        }
        data = cls.data_entry(ob)
        if data is not None:
            entry["data"] = data
        if ob.type == "ARMATURE":
            entry["animation"] = cls.animation(ob)
        if any(m.type == "NODES" for m in ob.modifiers):
            entry["node_inputs"] = Evaluated.modifier_inputs(ob)
            if ob.type == "MESH" and not ob.hide_viewport:
                entry["evaluated"] = cls.evaluated(ob)
        return entry

    @classmethod
    def data_entry(cls, ob: Any) -> dict | None:
        """The fingerprint of the object's data by its kind; None for a kind without data."""
        if ob.type == "CURVE":
            return cls.curve(ob.data)
        if ob.type == "CURVES":
            return cls.curves(ob.data)
        if ob.type == "MESH":
            return cls.mesh(ob.data)
        if ob.type == "ARMATURE":
            return cls.armature(ob.data)
        return None

    @staticmethod
    def hash(data: bytes) -> str:
        """A short digest of bytes."""
        return hashlib.sha1(data).hexdigest()[:16]

    @classmethod
    def text(cls, items: Any) -> str:
        """A short digest of lines of text."""
        return cls.hash("\n".join(items).encode())

    @classmethod
    def spline_digest(cls, spline: Any) -> str:
        """A legacy spline's points, handles, radii and handle types."""
        points = spline.bezier_points
        parts = [
            Evaluated.floats(points, "co", 3),
            Evaluated.floats(points, "handle_left", 3),
            Evaluated.floats(points, "handle_right", 3),
            Evaluated.floats(points, "radius", 1),
        ]
        types = [f"{p.handle_left_type}/{p.handle_right_type}" for p in points]
        return cls.hash(b"".join(a.tobytes() for a in parts) + "|".join(types).encode())

    @classmethod
    def curve(cls, curve: Any) -> dict:
        """A legacy curve: counts, bevel and each spline's digest."""
        return {
            "splines": len(curve.splines),
            "points": sum(len(s.bezier_points) for s in curve.splines),
            "bevel_depth": curve.bevel_depth,
            "resolution_u": curve.resolution_u,
            "spline_digests": [cls.spline_digest(s) for s in curve.splines],
        }

    @classmethod
    def curves(cls, curves: Any) -> dict:
        """A Curves object hashed exactly as curve() hashes a legacy curve: the digests match for the same points."""
        sizes = [len(c.points) for c in curves.curves]
        co = Evaluated.floats(curves.position_data, "vector", 3).reshape(-1, 3)
        attrs = curves.attributes
        if "handle_left" not in attrs:  # the wind's joint curves: poly curves, one point per joint
            return {"splines": len(sizes), "points": sum(sizes), "co": cls.hash(co.tobytes())}
        left = Evaluated.floats(attrs["handle_left"].data, "vector", 3).reshape(-1, 3)
        right = Evaluated.floats(attrs["handle_right"].data, "vector", 3).reshape(-1, 3)
        radius = Evaluated.floats(attrs["radius"].data, "value", 1)
        h1 = Evaluated.ints(attrs["handle_type_left"].data, "value")
        h2 = Evaluated.ints(attrs["handle_type_right"].data, "value")
        names = cls.HANDLE_TYPE_NAMES
        digests = []
        start = 0
        for size in sizes:
            span = slice(start, start + size)
            parts = [co[span].ravel(), left[span].ravel(), right[span].ravel(), radius[span]]
            types = [f"{names[a]}/{names[b]}" for a, b in zip(h1[span], h2[span], strict=True)]
            digests.append(cls.hash(b"".join(a.tobytes() for a in parts) + "|".join(types).encode()))
            start += size
        return {"splines": len(sizes), "points": sum(sizes), "spline_digests": digests}

    @classmethod
    def evaluated(cls, ob: Any) -> dict:
        """What a node modifier makes of an object at the current frame: element counts and positions."""
        evaluated = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        geometry = evaluated.evaluated_geometry()
        mesh = geometry.mesh
        if mesh is None:
            return {"mesh": None}
        return {
            "verts": len(mesh.vertices),
            "edges": len(mesh.edges),
            "faces": len(mesh.polygons),
            "co": cls.hash(Evaluated.floats(mesh.vertices, "co", 3).tobytes()),
        }

    @classmethod
    def mesh(cls, mesh: Any) -> dict:
        """A mesh: counts, positions, topology and its first UV layer."""
        out = {
            "verts": len(mesh.vertices),
            "edges": len(mesh.edges),
            "faces": len(mesh.polygons),
            "co": cls.hash(Evaluated.floats(mesh.vertices, "co", 3).tobytes()),
            "topology": cls.hash(Evaluated.ints(mesh.loops, "vertex_index").tobytes()),
            "uv_layers": [layer.name for layer in mesh.uv_layers],
        }
        if mesh.uv_layers:
            out["uv"] = cls.hash(Evaluated.floats(mesh.uv_layers[0].data, "uv", 2).tobytes())
        return out

    @classmethod
    def armature(cls, armature: Any) -> dict:
        """An armature: bone names, parents, connections and geometry."""
        bones = armature.bones
        return {
            "bones": len(bones),
            "names": cls.text([b.name for b in bones]),
            "parents": cls.text([b.parent.name if b.parent else "" for b in bones]),
            "connect": cls.text([str(b.use_connect) for b in bones]),
            "geometry": cls.hash(
                Evaluated.floats(bones, "head_local", 3).tobytes()
                + Evaluated.floats(bones, "tail_local", 3).tobytes()
                + Evaluated.floats(bones, "head_radius", 1).tobytes()
                + Evaluated.floats(bones, "tail_radius", 1).tobytes()
            ),
        }

    @classmethod
    def animation(cls, ob: Any) -> dict:
        """An object's F-curves: paths, groups and modifier values."""
        curves = Evaluated.fcurves_of(ob)
        params = []
        for fc in curves:
            for mod in fc.modifiers:
                values = [getattr(mod, name) for name in cls.MODIFIER_PARAMS.get(mod.type, ())]
                params.append(f"{mod.type}:" + ",".join(repr(v) for v in values))
        return {
            "fcurves": len(curves),
            "paths": cls.text([f"{c.data_path}[{c.array_index}]" for c in curves]),
            "groups": cls.text([c.group.name if c.group else "" for c in curves]),
            "modifiers": cls.text(params),
        }

    @classmethod
    def vertex_groups(cls, ob: Any) -> str:
        """A mesh's vertex groups and every vertex's weights."""
        if not ob.vertex_groups or ob.type != "MESH":
            return ""
        members = []
        for v in ob.data.vertices:
            members.append(",".join(f"{g.group}:{g.weight!r}" for g in v.groups))
        return cls.text([g.name for g in ob.vertex_groups] + members)


class FingerprintDiff:
    """The first difference between two fingerprints, as a readable path."""

    @classmethod
    def first(cls, expected, actual, path="") -> str:
        """Human-readable location of the first difference between two fingerprints."""
        if isinstance(expected, dict) and isinstance(actual, dict):
            return cls.in_dict(expected, actual, path)
        if isinstance(expected, list) and isinstance(actual, list):
            return cls.in_list(expected, actual, path)
        return "" if expected == actual else f"{path}: {expected!r} -> {actual!r}"

    @classmethod
    def in_dict(cls, expected, actual, path) -> str:
        for key in sorted(set(expected) | set(actual)):
            if key not in actual:
                return f"{path}/{key}: missing"
            if key not in expected:
                return f"{path}/{key}: unexpected"
            found = cls.first(expected[key], actual[key], f"{path}/{key}")
            if found:
                return found
        return ""

    @classmethod
    def in_list(cls, expected, actual, path) -> str:
        if len(expected) != len(actual):
            return f"{path}: length {len(expected)} -> {len(actual)}"
        for i, (e, a) in enumerate(zip(expected, actual, strict=True)):
            found = cls.first(e, a, f"{path}[{i}]")
            if found:
                return found
        return ""
