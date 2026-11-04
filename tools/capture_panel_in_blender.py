# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside a Blender window (started with --enable-event-simulate) for tools/capture_panel.py: a picture of each
page of the Adjust Last Operation panel for the help pages.

Argument after `--`: the out folder. The steps run on timers, because Blender handles the simulated input between
them: close the splash, add a tree with the F3 menu search (so Blender records it as the last operation, as when a
user adds it), open the panel, then for each page draw it and save the panel's region as <page>.png. Then Blender
quits. Each picture prints "WROTE <file>"; a failure prints "FAILED: <reason>" and quits.
"""

import sys
from collections.abc import Callable
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)


class PanelCapture:
    """The capture steps, each run by a timer after the one before."""

    STEP_SECONDS = 1.0  # between two steps: time for Blender to handle the simulated input
    SEARCH = "sapling tree gen"  # the F3 menu search that finds Add > Curve > Sapling Tree Gen
    MARGIN = 6  # pixels round the panel's region in a picture

    def __init__(self, out: Path) -> None:
        """Pictures into `out`."""
        self.out = out
        self.window = bpy.context.window_manager.windows[0]

    def view(self) -> bpy.types.Area:
        """The 3D view of the window."""
        for area in self.window.screen.areas:
            if area.type == "VIEW_3D":
                return area
        raise RuntimeError("the window has no 3D view")

    def region(self, kind: str) -> bpy.types.Region:
        """The 3D view's region of the kind ('WINDOW', 'HUD')."""
        for region in self.view().regions:
            if region.type == kind:
                return region
        raise RuntimeError(f"the 3D view has no {kind} region")

    def key(self, kind: str, x: int, y: int, text: str = "") -> None:
        """Simulate a key press and release at (x, y)."""
        # stub: the event type is a Literal of key names; these names are built from SEARCH at run time
        self.window.event_simulate(type=kind, value="PRESS", unicode=text, x=x, y=y)  # type: ignore[arg-type]
        self.window.event_simulate(type=kind, value="RELEASE", x=x, y=y)  # type: ignore[arg-type]

    def click(self, x: int, y: int) -> None:
        """Simulate a left click at (x, y)."""
        self.window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
        self.window.event_simulate(type="LEFTMOUSE", value="PRESS", x=x, y=y)
        self.window.event_simulate(type="LEFTMOUSE", value="RELEASE", x=x, y=y)

    def close_splash(self) -> None:
        """Close the splash screen; empty the scene."""
        self.key("ESC", 400, 400)
        bpy.data.batch_remove(list(bpy.data.objects))

    def add_tree(self) -> None:
        """Add a tree with the F3 menu search, in the middle of the 3D view."""
        view = self.region("WINDOW")
        x = view.x + view.width // 2
        y = view.y + view.height // 2
        self.window.event_simulate(type="MOUSEMOVE", value="NOTHING", x=x, y=y)
        self.key("F3", x, y)
        for letter in self.SEARCH:
            kind = letter.upper()
            if letter == " ":
                kind = "SPACE"
            self.key(kind, x, y, letter)
        self.key("RET", x, y)

    def open_panel(self) -> None:
        """Click the header of the collapsed panel. Raises RuntimeError when the tree was not added from the UI."""
        operators = [operator.bl_idname for operator in bpy.context.window_manager.operators]
        if not operators or operators[-1] != "CURVE_OT_tree_add":
            raise RuntimeError(f"the menu search added no tree (last operations: {operators[-3:]})")
        hud = self.region("HUD")
        self.click(hud.x + 40, hud.y + hud.height // 2)

    def capture_pages(self) -> None:
        """Draw each page and save the panel's region as <page>.png."""
        operator = bpy.context.window_manager.operators[-1]
        pages = operator.properties.bl_rna.properties["chooseSet"].enum_items
        for page in pages:
            operator.properties.chooseSet = page.identifier
            with bpy.context.temp_override(window=self.window):
                bpy.ops.wm.redraw_timer(type="DRAW_WIN_SWAP", iterations=2)
            self.save(page.name.lower().replace(" ", "-"))

    def save(self, name: str) -> None:
        """Save the panel's region of a window screenshot as <name>.png."""
        whole = self.out / f"{name}.window.png"
        with bpy.context.temp_override(window=self.window, area=self.view()):
            bpy.ops.screen.screenshot(filepath=str(whole))
        image = bpy.data.images.load(str(whole))
        width: int = image.size[0]  # type: ignore[index]  # stub: bpy_prop_array is indexable at run time
        height: int = image.size[1]  # type: ignore[index]  # stub: as above
        pixels = np.empty(width * height * 4, dtype=np.float32)
        image.pixels.foreach_get(pixels)
        bpy.data.images.remove(image)
        whole.unlink()
        hud = self.region("HUD")
        low_x = max(hud.x - self.MARGIN, 0)
        low_y = max(hud.y - self.MARGIN, 0)
        high_x = min(hud.x + hud.width + self.MARGIN, width)
        high_y = min(hud.y + hud.height + self.MARGIN, height)
        crop = pixels.reshape(height, width, 4)[low_y:high_y, low_x:high_x].copy()
        picture = bpy.data.images.new(name, crop.shape[1], crop.shape[0])
        picture.pixels.foreach_set(crop.ravel())  # type: ignore[arg-type]  # stub: as above
        path = self.out / f"{name}.png"
        picture.filepath_raw = str(path)
        picture.file_format = "PNG"
        picture.save()
        bpy.data.images.remove(picture)
        print(f"WROTE {path}", flush=True)

    def run(self) -> None:
        """Start the steps on timers."""
        steps = [self.close_splash, self.add_tree, self.open_panel, self.capture_pages]
        for index, step in enumerate(steps):
            last = index == len(steps) - 1
            bpy.app.timers.register(self.timed(step, last), first_interval=(index + 1) * self.STEP_SECONDS)

    @staticmethod
    def timed(step: Callable[[], None], last: bool) -> Callable[[], None]:
        """A timer callback that runs `step` once and quits Blender after the last step. On a failure it prints
        FAILED and quits: the driver reads the output, because a timer cannot set Blender's exit code."""

        def callback() -> None:
            try:
                step()
            except RuntimeError as error:  # a failed step ends the capture: the driver sees the FAILED line
                print(f"FAILED: {error}", flush=True)
                bpy.ops.wm.quit_blender()
                return
            if last:
                bpy.ops.wm.quit_blender()

        return callback


def main() -> None:
    """Enable the add-on and start the capture into the out folder."""
    out = Path(sys.argv[sys.argv.index("--") + 1])
    out.mkdir(parents=True, exist_ok=True)
    bpy.ops.preferences.addon_enable(module=MODULE)
    PanelCapture(out).run()


main()
