# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/render_presets.py: one view of each preset on white, with a black 1.8 m human
silhouette for scale and a soft ground shadow.

Arguments after `--`: the out folder, the seed, then the preset names. Each preset is added with the add-on's
operator as a user adds it (the preset loaded by the operator), measured, and rendered with Cycles on the GPU: an
orthographic camera that looks down a little, a sun from the front left, a shadow-catcher floor, a transparent film.
The picture is then laid on white, so only the tree, the figure and their shadows show, and saved as <name>.jpg.
Each preset's measures go to <name>.json beside it (the driver collects them), and one line is printed:
"RENDERED <name> <height m> <width m> <seconds>".
"""

import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import bpy
import numpy as np
from mathutils import Euler, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)


@dataclass(frozen=True, slots=True)
class Bounds:
    """World-space bounds of the rendered objects: the lowest and highest corner, (3,) arrays in metres."""

    low: np.ndarray
    high: np.ndarray


@dataclass(frozen=True, slots=True)
class Look:
    """The fixed look of every picture (a change here needs `render_presets.py --all`)."""

    margin: float = 0.06  # of the framed extent, on each side
    picture_height: int = 900  # pixels
    tilt: float = 12.0  # degrees the camera looks down
    sun_strength: float = 4.0
    sun_angle: tuple[float, float, float] = (math.radians(50.0), 0.0, math.radians(-35.0))  # front left, above
    sky_strength: float = 0.35  # the fill light; low, so the crown keeps its light and shade
    samples: int = 128
    floor_white: float = 0.97  # floor pixels this bright or brighter become pure white (the faint sky occlusion)
    jpeg_quality: int = 88  # the pictures are mostly white: about 150 KB each
    figure_gap: float = 1.0  # m between the figure and the tree


class Silhouette:
    """The scale figure: tools/render_assets/standing_man.png on a card, black where the figure is."""

    IMAGE = Path(__file__).resolve().parent / "render_assets" / "standing_man.png"
    HEIGHT = 1.8  # m, the figure
    # The figure's rows in the image, counted from the bottom (tools/render_assets/SOURCES.md)
    FEET_ROW = 58
    HEAD_ROW = 1458
    RIGHT_COLUMN = 732  # the figure's right edge, in image columns from the left

    @classmethod
    def add(cls, right: float, y: float) -> None:
        """Add the card facing -Y, the figure's feet on the floor at depth `y` and its right edge at x = `right`."""
        if not cls.IMAGE.is_file():
            raise SystemExit(f"FAILED: the scale figure {cls.IMAGE} is missing")
        image = bpy.data.images.load(str(cls.IMAGE))
        width_px: int = image.size[0]  # type: ignore[index]  # stub: bpy_prop_array is indexable at run time
        height_px: int = image.size[1]  # type: ignore[index]  # stub: as above
        metres_per_row = cls.HEIGHT / (cls.HEAD_ROW - cls.FEET_ROW)
        card_height = height_px * metres_per_row
        card_width = width_px * metres_per_row
        bottom = -cls.FEET_ROW * metres_per_row
        half = card_width / 2
        figure_right = cls.RIGHT_COLUMN * metres_per_row - half  # from the card's centre
        vertices = [
            (-half, 0.0, bottom),
            (half, 0.0, bottom),
            (half, 0.0, bottom + card_height),
            (-half, 0.0, bottom + card_height),
        ]
        mesh = bpy.data.meshes.new("render_silhouette")
        mesh.from_pydata(vertices, [], [(0, 1, 2, 3)])
        uv = mesh.uv_layers.new(name="UVMap")
        for loop, corner in zip(uv.data, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)), strict=True):
            loop.uv = corner
        mesh.materials.append(cls.material(image))
        ob = bpy.data.objects.new("render_silhouette", mesh)
        ob.location = (right - figure_right, y, 0.0)
        bpy.context.scene.collection.objects.link(ob)

    @staticmethod
    def material(image: bpy.types.Image) -> bpy.types.Material:
        """Black (an emission of black) where the image's alpha is 0.5 or more, transparent elsewhere."""
        material = bpy.data.materials.new("render_silhouette")
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        output = None
        for node in list(nodes):
            if node.type == "OUTPUT_MATERIAL":
                output = node
            else:
                nodes.remove(node)
        if output is None:
            raise SystemExit("FAILED: a new material has no output node")
        texture = nodes.new("ShaderNodeTexImage")
        texture.image = image
        cut = nodes.new("ShaderNodeMath")
        cut.operation = "GREATER_THAN"
        cut.inputs[1].default_value = 0.5
        black = nodes.new("ShaderNodeEmission")
        black.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        clear = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        links.new(texture.outputs["Alpha"], cut.inputs[0])
        links.new(cut.outputs[0], mix.inputs["Fac"])
        links.new(clear.outputs[0], mix.inputs[1])
        links.new(black.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], output.inputs["Surface"])
        return material


class PresetScene:
    """An empty scene with the fixed light, the shadow-catcher floor and the Cycles settings."""

    def __init__(self, look: Look) -> None:
        """A scene builder with the fixed look."""
        self.look = look

    def reset(self) -> None:
        """Remove every object and its data, then add the sun and the floor, and set the world and the renderer."""
        data = bpy.data
        data.batch_remove(
            [*data.objects, *data.curves, *data.meshes, *data.armatures, *data.actions, *data.cameras, *data.lights]
        )
        sun_data = bpy.data.lights.new("render_sun", "SUN")
        sun_data.energy = self.look.sun_strength
        sun_data.angle = math.radians(2.0)  # a slightly soft shadow edge
        sun = bpy.data.objects.new("render_sun", sun_data)
        sun.rotation_euler = self.look.sun_angle
        bpy.context.scene.collection.objects.link(sun)
        bpy.ops.mesh.primitive_plane_add(size=500.0, location=(0.0, 0.0, 0.0))
        floor = bpy.context.active_object
        floor.name = "render_floor"
        floor.is_shadow_catcher = True
        self.world()
        self.renderer()

    def world(self) -> None:
        """A white sky of low strength: a fill light (the film is transparent, the white comes after)."""
        world = bpy.context.scene.world
        if world is None:
            raise SystemExit("FAILED: the scene has no world")
        background = None
        for node in world.node_tree.nodes:
            if node.type == "BACKGROUND":
                background = node
        if background is None:
            raise SystemExit("FAILED: the world has no Background node")
        background.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        background.inputs["Strength"].default_value = self.look.sky_strength

    def renderer(self) -> None:
        """Cycles on the GPU (path tracing and denoising), a transparent film, the Standard view transform, an RGBA
        PNG."""
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.cycles.device = "GPU"
        scene.cycles.samples = self.look.samples
        scene.cycles.use_denoising = True
        scene.cycles.denoising_use_gpu = True  # else OpenImageDenoise runs on the CPU: 9 of the 10 s of a render
        self.gpu()
        scene.render.film_transparent = True
        scene.view_settings.view_transform = "Standard"  # AgX would grey the white
        scene.render.image_settings.file_format = "PNG"
        scene.render.image_settings.color_mode = "RGBA"

    @staticmethod
    def gpu() -> None:
        """Turn on Cycles' GPU devices (OptiX, else CUDA). Raises SystemExit when there is no GPU device."""
        preferences = bpy.context.preferences.addons["cycles"].preferences
        for backend in ("OPTIX", "CUDA"):
            preferences.compute_device_type = backend
            preferences.get_devices()
            gpus = [device for device in preferences.devices if device.type == backend]
            if gpus:
                for device in preferences.devices:
                    device.use = device.type == backend
                print(f"GPU {backend}: {', '.join(device.name for device in gpus)}", flush=True)
                return
        raise SystemExit("FAILED: Cycles found no OptiX or CUDA device")


class PresetPicture:
    """Adds one preset's tree with the figure, renders it and lays the picture on white."""

    def __init__(self, scene: PresetScene, out: Path, seed: int) -> None:
        """Pictures into `out`, every tree with `seed`."""
        self.scene = scene
        self.out = out
        self.seed = seed

    def render(self, name: str) -> None:
        """Add the preset's tree, place the figure and the camera, render <name>.png on white and print its line."""
        self.scene.reset()
        started = time.perf_counter()
        result = bpy.ops.curve.tree_add(preset=name, preset_pending=True, do_update=True, seed=self.seed)
        seconds = time.perf_counter() - started
        if result != {"FINISHED"}:
            raise SystemExit(f"FAILED: tree_add of {name} returned {result}")
        tree = self.bounds()
        Silhouette.add(float(tree.low[0]) - self.scene.look.figure_gap, float(tree.low[1]))
        both = self.bounds()
        self.add_camera(both, tree)
        rendered = self.out / f"{name}.render.png"
        bpy.context.scene.render.filepath = str(rendered)
        bpy.ops.render.render(write_still=True)
        self.on_white(rendered, self.out / f"{name}.jpg")
        rendered.unlink()
        height = round(float(tree.high[2] - tree.low[2]), 2)
        width = round(float(max(tree.high[0] - tree.low[0], tree.high[1] - tree.low[1])), 2)
        measures = {"height_m": height, "width_m": width, "seconds": round(seconds, 2)}
        (self.out / f"{name}.json").write_text(json.dumps(measures) + "\n", encoding="utf-8")
        print(f"RENDERED {name} {height} {width} {seconds:.2f}", flush=True)

    @staticmethod
    def bounds() -> Bounds:
        """The world bounds of every rendered object except the floor, evaluated."""
        bpy.context.view_layer.update()
        graph = bpy.context.evaluated_depsgraph_get()
        low = np.full(3, np.inf)
        high = np.full(3, -np.inf)
        for ob in bpy.data.objects:
            if ob.type not in {"MESH", "CURVE", "CURVES"} or ob.hide_render or ob.name == "render_floor":
                continue
            evaluated = ob.evaluated_get(graph)
            for corner in evaluated.bound_box:
                point = np.array(evaluated.matrix_world @ Vector(corner))
                low = np.minimum(low, point)
                high = np.maximum(high, point)
        if not np.isfinite(low).all():
            raise SystemExit("FAILED: nothing to render")
        return Bounds(low=low, high=high)

    def add_camera(self, both: Bounds, tree: Bounds) -> None:
        """An orthographic camera from the front (-Y), looking down by the tilt, that frames the corners of `both`
        (the tree and the figure, the floor under them and the shadows) with the margin, the tree in the middle."""
        look = self.scene.look
        rotation = Euler((math.radians(90.0 - look.tilt), 0.0, 0.0))
        matrix = rotation.to_matrix()
        right = matrix @ Vector((1.0, 0.0, 0.0))
        up = matrix @ Vector((0.0, 1.0, 0.0))
        forward = matrix @ Vector((0.0, 0.0, -1.0))
        corners = []
        for cx in (both.low[0], both.high[0]):
            for cy in (both.low[1], both.high[1]):
                for cz in (0.0, both.high[2]):
                    corners.append(Vector((float(cx), float(cy), float(cz))))
        corners += self.shadow_corners(both)
        across = [corner.dot(right) for corner in corners]
        along = [corner.dot(up) for corner in corners]
        middle = Vector(((tree.low + tree.high) / 2).tolist()).dot(right)  # the tree's middle, across the picture
        half = max(middle - min(across), max(across) - middle)  # the wider side: the figure's or the shadow's
        width = 2 * half
        height = max(along) - min(along)
        centre = right * middle + up * ((max(along) + min(along)) / 2)
        extent = max(width, height) * (1 + 2 * look.margin)
        data = bpy.data.cameras.new("render_camera")
        data.type = "ORTHO"
        data.ortho_scale = extent
        data.clip_end = 10000.0
        camera = bpy.data.objects.new("render_camera", data)
        bpy.context.scene.collection.objects.link(camera)
        camera.rotation_euler = rotation
        camera.location = centre - forward * (extent * 4)
        scene = bpy.context.scene
        scene.camera = camera
        scene.render.resolution_y = look.picture_height
        scene.render.resolution_x = round(look.picture_height * (width / height if height > 0 else 1.0))

    def shadow_corners(self, both: Bounds) -> list[Vector]:
        """Where the sun casts the bounds' top corners onto the floor: the far end of the shadows."""
        sun = Euler(self.scene.look.sun_angle).to_matrix() @ Vector((0.0, 0.0, -1.0))  # the light's direction
        if sun.z >= 0:
            raise SystemExit("FAILED: the sun does not shine down")
        out = []
        for cx in (both.low[0], both.high[0]):
            for cy in (both.low[1], both.high[1]):
                top = Vector((float(cx), float(cy), float(both.high[2])))
                out.append(top - sun * (top.z / sun.z))
        return out

    def on_white(self, rendered: Path, picture: Path) -> None:
        """Lay the rendered RGBA picture on white and save it as the JPEG `picture`. The floor's pixels (not opaque:
        the shadow catcher) are remapped so that floor_white and brighter is pure white and the shadows fade to it."""
        image = bpy.data.images.load(str(rendered))
        width: int = image.size[0]  # type: ignore[index]  # stub: bpy_prop_array is indexable at run time
        height: int = image.size[1]  # type: ignore[index]  # stub: as above
        flat = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(flat)
        pixels = flat.reshape(height, width, 4)
        alpha = pixels[:, :, 3:4]
        pixels[:, :, :3] = pixels[:, :, :3] * alpha + (1.0 - alpha)
        white = self.scene.look.floor_white
        floor = pixels[:, :, 3] < 0.999
        lifted = np.clip(pixels[:, :, :3] / white, 0.0, 1.0)
        pixels[:, :, :3][floor] = lifted[floor]
        pixels[:, :, 3] = 1.0
        image.pixels.foreach_set(pixels.ravel())  # type: ignore[arg-type]  # stub: it takes a numpy buffer
        image.filepath_raw = str(picture)
        image.file_format = "JPEG"
        scene = bpy.context.scene
        scene.render.image_settings.file_format = "JPEG"
        scene.render.image_settings.color_mode = "RGB"
        scene.render.image_settings.quality = self.scene.look.jpeg_quality
        image.save_render(str(picture), scene=scene)
        bpy.data.images.remove(image)


def main() -> None:
    """Enable the add-on and render each preset named after the out folder and the seed."""
    arguments = sys.argv[sys.argv.index("--") + 1 :]
    out = Path(arguments[0])
    seed = int(arguments[1])
    names = arguments[2:]
    bpy.ops.preferences.addon_enable(module=MODULE)
    picture = PresetPicture(PresetScene(Look()), out, seed)
    for name in names:
        picture.render(name)


if __name__ == "__main__":  # tools/render_listing_in_blender.py imports the classes
    main()
