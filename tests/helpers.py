# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared test helpers: scene reset, tree generation through the public operator, fingerprints."""

import hashlib
import sys
from typing import Any

import bpy
import numpy as np
from bpy_extras import anim_utils

MODULE = "bl_ext.user_default.sapling_tree_gen"
OPERATOR = "curve.tree_add"
RECORD_GOLDEN = False

# Properties that are UI state, not generation input.
UI_ONLY = {
    "chooseSet",
    "presetName",
    "limitImport",
    "overwrite",
    "do_update",
    "leafDupliObj",
    "preset",
    "replace",
    "load_stored",
}


def addon():
    return sys.modules[MODULE]


def reset_scene() -> None:
    """Remove everything a tree generation creates, so data names never get .001 suffixes."""
    collections: tuple[Any, ...] = (
        bpy.data.objects,
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.actions,
        bpy.data.materials,
        bpy.data.node_groups,
    )
    for collection in collections:
        for block in list(collection):
            collection.remove(block)
    scene = bpy.context.scene
    scene.render.fps = 24  # wind animation speed depends on the scene frame rate
    scene.render.fps_base = 1.0
    scene.frame_set(1)


def module(name: str) -> Any:
    """A module of the installed add-on, e.g. module("build.tree_record")."""
    return sys.modules[f"{MODULE}.{name}"]


def generation_names() -> list[str]:
    """The add-on's own list of properties that shape a tree."""
    return module("ui.properties").TreeProperties.generation_names()


def operator_property_names() -> list[str]:
    rna = bpy.ops.curve.tree_add.get_rna_type()
    return [p.identifier for p in rna.properties if p.identifier != "rna_type"]


def operator_defaults() -> dict:
    rna = bpy.ops.curve.tree_add.get_rna_type()
    out = {}
    for prop in rna.properties:
        name = prop.identifier
        if name == "rna_type" or name in UI_ONLY:
            continue
        if getattr(prop, "is_array", False):
            out[name] = list(prop.default_array)
        else:
            out[name] = prop.default
    return out


def plain(value):
    """Convert bpy/mathutils values to JSON-friendly Python values."""
    if isinstance(value, str | bool | int | float) or value is None:
        return value
    return [plain(v) for v in value]


def resolve_preset(filename: str) -> dict:
    """Full operator settings produced by loading a built-in preset (operator defaults + preset)."""
    settings = operator_defaults()
    store = module("presets").PresetStore.for_addon()
    preset = store.load(filename.removesuffix(".py")).values
    names = set(operator_property_names())
    settings.update({k: v for k, v in preset.items() if k in names and k not in UI_ONLY})
    return {k: plain(v) for k, v in settings.items()}


def generate(settings: dict) -> set:
    """Run the operator with explicit settings on an empty scene; return the result set."""
    reset_scene()
    # Blender applies operator keywords in property-definition order and runs their update callbacks;
    # the legacy callbacks of UI-only properties (limitImport, chooseSet, ...) clear do_update, so only
    # generation settings are passed.
    return bpy.ops.curve.tree_add(**settings, do_update=True)


def _hash(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()[:16]


def _floats(collection, attr: str, width: int) -> np.ndarray:
    """Exact stored values (Blender keeps float32), so any drift at all changes the hash."""
    buf = np.empty(len(collection) * width, dtype=np.float32)
    collection.foreach_get(attr, buf)
    return buf


def _ints(collection, attr: str, width: int = 1) -> np.ndarray:
    buf = np.empty(len(collection) * width, dtype=np.int32)
    collection.foreach_get(attr, buf)
    return buf


def _text(items) -> str:
    return _hash("\n".join(items).encode())


def _spline_digest(spline) -> str:
    points = spline.bezier_points
    parts = [
        _floats(points, "co", 3),
        _floats(points, "handle_left", 3),
        _floats(points, "handle_right", 3),
        _floats(points, "radius", 1),
    ]
    types = [f"{p.handle_left_type}/{p.handle_right_type}" for p in points]
    return _hash(b"".join(a.tobytes() for a in parts) + "|".join(types).encode())


def _curve_fp(curve) -> dict:
    return {
        "splines": len(curve.splines),
        "points": sum(len(s.bezier_points) for s in curve.splines),
        "bevel_depth": curve.bevel_depth,
        "resolution_u": curve.resolution_u,
        "spline_digests": [_spline_digest(s) for s in curve.splines],
    }


def _mesh_fp(mesh) -> dict:
    out = {
        "verts": len(mesh.vertices),
        "edges": len(mesh.edges),
        "faces": len(mesh.polygons),
        "co": _hash(_floats(mesh.vertices, "co", 3).tobytes()),
        "topology": _hash(_ints(mesh.loops, "vertex_index").tobytes()),
        "uv_layers": [layer.name for layer in mesh.uv_layers],
    }
    if mesh.uv_layers:
        out["uv"] = _hash(_floats(mesh.uv_layers[0].data, "uv", 2).tobytes())
    if mesh.skin_vertices:
        out["skin"] = _hash(_floats(mesh.skin_vertices[0].data, "radius", 2).tobytes())
    return out


def _armature_fp(armature) -> dict:
    bones = armature.bones
    return {
        "bones": len(bones),
        "names": _text([b.name for b in bones]),
        "parents": _text([b.parent.name if b.parent else "" for b in bones]),
        "connect": _text([str(b.use_connect) for b in bones]),
        "geometry": _hash(
            _floats(bones, "head_local", 3).tobytes()
            + _floats(bones, "tail_local", 3).tobytes()
            + _floats(bones, "head_radius", 1).tobytes()
            + _floats(bones, "tail_radius", 1).tobytes()
        ),
    }


def fcurves_of(ob) -> list:
    ad = ob.animation_data
    if not ad or not ad.action or not ad.action_slot:
        return []
    channelbag = anim_utils.action_get_channelbag_for_slot(ad.action, ad.action_slot)
    return list(channelbag.fcurves) if channelbag else []


_MODIFIER_PARAMS = {
    "FNGENERATOR": ("amplitude", "phase_offset", "phase_multiplier", "value_offset", "use_additive"),
    "NOISE": ("scale", "strength", "offset", "phase", "use_restricted_range", "frame_end", "blend_in", "blend_out"),
}


def _animation_fp(ob) -> dict:
    curves = fcurves_of(ob)
    params = []
    for fc in curves:
        for mod in fc.modifiers:
            values = [getattr(mod, name) for name in _MODIFIER_PARAMS.get(mod.type, ())]
            params.append(f"{mod.type}:" + ",".join(repr(v) for v in values))
    return {
        "fcurves": len(curves),
        "paths": _text([f"{c.data_path}[{c.array_index}]" for c in curves]),
        "modifiers": _text(params),
    }


def _vertex_groups_fp(ob) -> str:
    if not ob.vertex_groups or ob.type != "MESH":
        return ""
    members = []
    for v in ob.data.vertices:
        members.append(",".join(f"{g.group}:{g.weight!r}" for g in v.groups))
    return _text([g.name for g in ob.vertex_groups] + members)


def fingerprint() -> dict:
    """A compact, order-sensitive summary of every object in the scene and its data."""
    out = {}
    for ob in sorted(bpy.data.objects, key=lambda o: o.name):
        entry: dict[str, Any] = {
            "type": ob.type,
            "parent": ob.parent.name if ob.parent else None,
            "modifiers": [m.type for m in ob.modifiers],
            "vertex_groups": _vertex_groups_fp(ob),
            "instance_type": ob.instance_type,
        }
        if ob.type == "CURVE":
            entry["data"] = _curve_fp(ob.data)
        elif ob.type == "MESH":
            entry["data"] = _mesh_fp(ob.data)
        elif ob.type == "ARMATURE":
            entry["data"] = _armature_fp(ob.data)
            entry["animation"] = _animation_fp(ob)
        out[ob.name] = entry
    return out
