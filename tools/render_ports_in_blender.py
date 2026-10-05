# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/render_ports.py: tree-gen's tree and the ported presets side by side.

Arguments after `--`: the tree-gen clone, the out folder, the seed, the preset folders (comma separated), then
the species (species or species:preset_name). tree-gen is imported from the clone as a package and builds its
tree with parametric.gen.construct; the presets are generated with the add-on's operator. Workbench renders with
fixed bark and leaf colours, orthographic front and top views framing all trees.
"""

import ast
import importlib
import sys
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)


@dataclass(frozen=True, slots=True)
class Colour:
    """A viewport colour, each component 0..1."""

    red: float
    green: float
    blue: float

    @property
    def rgba(self) -> list[float]:
        return [self.red, self.green, self.blue, 1.0]


@dataclass(frozen=True, slots=True)
class MaterialColour:
    """The sheet colour of the add-on's materials whose names start with `prefix`."""

    prefix: str
    colour: Colour


@dataclass(frozen=True, slots=True)
class Bounds:
    """World-space bounds: the lowest and highest corner, (3,) arrays."""

    low: np.ndarray
    high: np.ndarray


BARK = Colour(0.35, 0.22, 0.12)
LEAF = Colour(0.15, 0.5, 0.12)
BLOSSOM = Colour(0.95, 0.75, 0.8)
SAPLING_MATERIALS = [
    MaterialColour("Sapling Bark", BARK),
    MaterialColour("Sapling Leaf", LEAF),
    MaterialColour("Sapling Blossom", BLOSSOM),
]
WIDTH = 2400  # pixels across a sheet


def material(name: str, colour: Colour) -> bpy.types.Material:
    found = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    found.diffuse_color = colour.rgba  # type: ignore[assignment]  # stub: a colour property takes a sequence
    return found


def preset(folder: Path, name: str) -> dict:
    """The settings dictionary of a preset file."""
    tree = ast.parse((folder / f"{name}.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n) for n in ast.walk(tree) if isinstance(n, ast.Dict))


def treegen_tree(gen, species: str, seed: int) -> bpy.types.Object:
    """tree-gen's tree of a species; its parts get the sheet's colours."""
    package = gen.__name__.removesuffix(".parametric.gen")
    params = importlib.import_module(f"{package}.parametric.tree_params.{species}").params
    root = gen.construct(dict(params), seed=seed, generate_leaves=True)
    for child in root.children:
        child.data.materials.clear()
        if child.type != "MESH":
            child.data.materials.append(material("render bark", BARK))
        else:
            child.data.materials.append(
                material(
                    "render blossom" if "Blossom" in child.name else "render leaf",
                    BLOSSOM if "Blossom" in child.name else LEAF,
                )
            )
    return root


def sapling_tree(settings: dict, seed: int) -> bpy.types.Object:
    """A tree from preset settings (the operator), returned as its root."""
    before = set(bpy.data.objects)
    result = bpy.ops.curve.tree_add(**dict(settings, seed=seed), do_update=True)
    if result != {"FINISHED"}:
        raise SystemExit(f"tree_add returned {result}")
    return next(ob for ob in bpy.data.objects if ob not in before and ob.parent is None)


def bounds() -> Bounds:
    """The world bounds of every renderable object, evaluated."""
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    low, high = np.full(3, np.inf), np.full(3, -np.inf)
    for ob in bpy.data.objects:
        if ob.type not in {"MESH", "CURVE"} or ob.hide_render:
            continue
        evaluated = ob.evaluated_get(graph)
        for corner in evaluated.bound_box:
            point = np.array(evaluated.matrix_world @ Vector(corner))
            low, high = np.minimum(low, point), np.maximum(high, point)
    return Bounds(low, high)


def camera(name: str, location: list[float], rotation: list[float], scale: float) -> bpy.types.Object:
    data = bpy.data.cameras.new(name)
    data.type = "ORTHO"
    data.ortho_scale = scale
    ob = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(ob)
    ob.location, ob.rotation_euler = location, rotation
    return ob


def render(cam: bpy.types.Object, path: Path, height: int) -> None:
    scene = bpy.context.scene
    scene.camera = cam
    scene.render.resolution_x, scene.render.resolution_y = WIDTH, max(height, 1)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def colour_sapling_materials() -> None:
    for found in bpy.data.materials:
        for rule in SAPLING_MATERIALS:
            if found.name.startswith(rule.prefix):
                found.diffuse_color = rule.colour.rgba  # type: ignore[assignment]  # stub: as above


def sheet(gen, out: Path, seed: int, folders: list, spec: str) -> None:
    species, _, name = spec.partition(":")
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob)
    roots = [treegen_tree(gen, species, seed)]
    roots += [sapling_tree(preset(folder, name or species), seed) for folder in folders]
    colour_sapling_materials()
    box = bounds()
    spacing = max(box.high[0] - box.low[0], box.high[1] - box.low[1]) * 1.1
    for column, root in enumerate(roots):
        root.location.x = column * spacing
    box = bounds()
    span = box.high - box.low
    centre = (box.low + box.high) / 2
    front = camera("front", [centre[0], box.low[1] - 100, centre[2]], [np.pi / 2, 0, 0], max(span[0], span[2]) * 1.05)
    top = camera("top", [centre[0], centre[1], box.high[2] + 100], [0, 0, 0], max(span[0], span[1]) * 1.05)
    render(front, out / f"{name or species}_front.png", int(WIDTH * span[2] / span[0]))
    render(top, out / f"{name or species}_top.png", int(WIDTH * span[1] / span[0]))
    print(f"RENDERED {species}: tree-gen, then {len(folders)} preset folder(s)", flush=True)


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    treegen, out, seed, folders = Path(args[0]), Path(args[1]), int(args[2]), [Path(f) for f in args[3].split(",")]
    sys.path.insert(0, str(treegen.parent))
    gen = importlib.import_module(f"{treegen.name}.parametric.gen")
    bpy.ops.preferences.addon_enable(module=MODULE)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    for spec in args[4:]:
        sheet(gen, out, seed, folders, spec)


main()
