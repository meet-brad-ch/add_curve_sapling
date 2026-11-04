# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/render_listing.py: the media of the Extensions Platform listing, with the look of
the presets page (tools/render_presets_in_blender.py).

Argument after `--`: the out folder. It writes:
- featured.jpg: 1920 x 1080, presets side by side at true scale, the 1.8 m figure at the left;
- gallery_<preset>.jpg: 1920 x 1080, one preset beside the figure;
- icon.png: 256 x 256, one preset on a transparent background (rendered at 512 x 512, then scaled).
Each file prints one line "WROTE <file>".
"""

import math
import sys
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)
from render_presets_in_blender import Bounds, Look, PresetPicture, PresetScene, Silhouette  # noqa: E402  (as above)


@dataclass(frozen=True, slots=True)
class Media:
    """What the listing shows (a change here needs a new upload of the media)."""

    featured: tuple[str, ...] = ("coyote_brush", "japanese_maple", "lombardy_poplar", "weeping_willow", "fan_palm")
    gallery: tuple[str, ...] = ("cambridge_oak", "hill_cherry")
    icon: str = "sphere_tree"
    gap: float = -1.5  # m between two trees of the featured lineup (negative: the crowns overlap)
    stagger: float = 3.0  # m every second tree of the lineup stands back
    wide: tuple[int, int] = (1920, 1080)  # pixels of the featured and gallery pictures
    icon_render: int = 512  # pixels of the icon's render
    icon_size: int = 256  # pixels of the icon (the platform's size)
    icon_margin: float = 0.02  # of the framed extent, on each side
    seed: int = 1


@dataclass(frozen=True, slots=True)
class View:
    """The presets' camera direction: from the front (-Y), looking down by the tilt."""

    rotation: Euler
    right: Vector
    up: Vector
    forward: Vector

    @staticmethod
    def of(look: Look) -> "View":
        """The view of the presets page."""
        rotation = Euler((math.radians(90.0 - look.tilt), 0.0, 0.0))
        matrix: Matrix = rotation.to_matrix()
        right = matrix @ Vector((1.0, 0.0, 0.0))
        up = matrix @ Vector((0.0, 1.0, 0.0))
        forward = matrix @ Vector((0.0, 0.0, -1.0))
        return View(rotation=rotation, right=right, up=up, forward=forward)


class ListingMedia:
    """Adds presets at true scale and renders the listing's pictures."""

    def __init__(self, media: Media, out: Path) -> None:
        """The pictures of `media` into `out`."""
        self.media = media
        self.out = out
        self.look = Look()
        self.scene = PresetScene(self.look)
        self.picture = PresetPicture(self.scene, out, media.seed)
        self.view = View.of(self.look)

    def lineup(self, names: tuple[str, ...], stem: str) -> None:
        """The presets side by side from x = 0, the figure at the left, in one wide picture `stem`.jpg."""
        self.scene.reset()
        left = 0.0
        for index, name in enumerate(names):
            back = self.media.stagger * (index % 2)
            right = self.add(name, left, back)
            left = right + self.media.gap
        trees = self.picture.bounds()
        Silhouette.add(float(trees.low[0]) - self.look.figure_gap, float(trees.low[1]))
        both = self.picture.bounds()
        self.wide_camera(both)
        self.shoot(stem)

    def add(self, name: str, left: float, back: float) -> float:
        """Add the preset with its lowest x at `left`, `back` metres behind the line. Returns its highest x."""
        before = {ob.name for ob in bpy.data.objects}
        result = bpy.ops.curve.tree_add(preset=name, preset_pending=True, do_update=True, seed=self.media.seed)
        if result != {"FINISHED"}:
            raise SystemExit(f"FAILED: tree_add of {name} returned {result}")
        made = [ob for ob in bpy.data.objects if ob.name not in before]
        bounds = self.bounds_of(made)
        shift = left - float(bounds.low[0])
        for ob in made:
            if ob.parent is None:
                ob.location.x += shift
                ob.location.y += back
        return float(bounds.high[0]) + shift

    @staticmethod
    def bounds_of(objects: list[bpy.types.Object]) -> Bounds:
        """The world bounds of the rendered objects among `objects`, evaluated. Raises SystemExit when none renders."""
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        low = np.full(3, np.inf)
        high = np.full(3, -np.inf)
        for ob in objects:
            if ob.type not in {"MESH", "CURVE", "CURVES"} or ob.hide_render:
                continue
            evaluated = ob.evaluated_get(graph)
            for corner in evaluated.bound_box:
                point = np.array(evaluated.matrix_world @ Vector(corner))
                low = np.minimum(low, point)
                high = np.maximum(high, point)
        if not np.isfinite(low).all():
            raise SystemExit("FAILED: a preset made nothing to render")
        return Bounds(low=low, high=high)

    @staticmethod
    def box_corners(bounds: Bounds, floor: bool) -> list[Vector]:
        """The 8 corners of `bounds`; with `floor`, the low corners on the floor (z = 0)."""
        low_z = 0.0
        if not floor:
            low_z = float(bounds.low[2])
        corners = []
        for cx in (bounds.low[0], bounds.high[0]):
            for cy in (bounds.low[1], bounds.high[1]):
                for cz in (low_z, float(bounds.high[2])):
                    corners.append(Vector((float(cx), float(cy), cz)))
        return corners

    def wide_camera(self, both: Bounds) -> None:
        """A camera of the wide size that frames the trees and the figure across (a long shadow may leave the
        picture at the side) and the shadows down the picture, with the margin."""
        corners = self.box_corners(both, floor=True)
        across = [corner.dot(self.view.right) for corner in corners]
        corners += self.picture.shadow_corners(both)
        along = [corner.dot(self.view.up) for corner in corners]
        width_px, height_px = self.media.wide
        aspect = width_px / height_px
        width = max(across) - min(across)
        height = max(along) - min(along)
        extent = max(width, height * aspect) * (1 + 2 * self.look.margin)
        centre = self.view.right * ((max(across) + min(across)) / 2) + self.view.up * ((max(along) + min(along)) / 2)
        self.camera(centre, extent, width_px, height_px)

    def camera(self, centre: Vector, extent: float, width_px: int, height_px: int) -> None:
        """An orthographic camera of the view, centred on `centre`, `extent` metres across, at the pixel size."""
        data = bpy.data.cameras.new("render_camera")
        data.type = "ORTHO"
        data.ortho_scale = extent
        data.clip_end = 10000.0
        camera = bpy.data.objects.new("render_camera", data)
        bpy.context.scene.collection.objects.link(camera)
        camera.rotation_euler = self.view.rotation
        camera.location = centre - self.view.forward * (extent * 4)
        scene = bpy.context.scene
        scene.camera = camera
        scene.render.resolution_x = width_px
        scene.render.resolution_y = height_px

    def shoot(self, stem: str) -> None:
        """Render and lay the picture on white as `stem`.jpg."""
        rendered = self.out / f"{stem}.render.png"
        bpy.context.scene.render.filepath = str(rendered)
        bpy.ops.render.render(write_still=True)
        picture = self.out / f"{stem}.jpg"
        self.picture.on_white(rendered, picture)
        rendered.unlink()
        print(f"WROTE {picture}", flush=True)

    def icon(self) -> None:
        """The icon's preset alone, square, on transparency (the floor and its shadow hidden), as icon.png."""
        self.scene.reset()
        bpy.data.objects["render_floor"].hide_render = True
        before = {ob.name for ob in bpy.data.objects}
        name = self.media.icon
        result = bpy.ops.curve.tree_add(preset=name, preset_pending=True, do_update=True, seed=self.media.seed)
        if result != {"FINISHED"}:
            raise SystemExit(f"FAILED: tree_add of {name} returned {result}")
        tree = self.bounds_of([ob for ob in bpy.data.objects if ob.name not in before])
        corners = self.box_corners(tree, floor=False)
        across = [corner.dot(self.view.right) for corner in corners]
        along = [corner.dot(self.view.up) for corner in corners]
        extent = max(max(across) - min(across), max(along) - min(along)) * (1 + 2 * self.media.icon_margin)
        centre = self.view.right * ((max(across) + min(across)) / 2) + self.view.up * ((max(along) + min(along)) / 2)
        size = self.media.icon_render
        self.camera(centre, extent, size, size)
        rendered = self.out / "icon.render.png"
        bpy.context.scene.render.filepath = str(rendered)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(str(rendered))
        image.scale(self.media.icon_size, self.media.icon_size)
        icon = self.out / "icon.png"
        image.filepath_raw = str(icon)
        image.file_format = "PNG"
        image.save()
        bpy.data.images.remove(image)
        rendered.unlink()
        print(f"WROTE {icon}", flush=True)


def main() -> None:
    """Enable the add-on and render the featured picture, the gallery and the icon into the out folder."""
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    out = Path(arguments[0])
    bpy.ops.preferences.addon_enable(module=MODULE)
    media = Media()
    listing = ListingMedia(media, out)
    listing.lineup(media.featured, "featured")
    for name in media.gallery:
        listing.lineup((name,), f"gallery_{name}")
    listing.icon()


main()
