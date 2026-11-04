# SPDX-License-Identifier: GPL-3.0-or-later

"""Render the built-in presets for the presets page and write the page (docs/presets.md).

    python tools/render_presets.py              # the presets that are new or out of date, then the page
    python tools/render_presets.py --all        # every preset again (e.g. after a change to the look)
    python tools/render_presets.py acer palm    # only these presets, then the page
    python tools/render_presets.py --check      # exit 1 when a picture is missing or out of date (no Blender)
    python tools/render_presets.py --page       # only write the page from docs/presets/presets.json

Each picture's key is a hash of its preset's settings (not its comments), its golden tree fingerprint
(tests/golden/preset_<name>.json), the render script and the scale figure: a change to any of them makes the picture
out of date. docs/presets/presets.json
holds each picture's key and the tree's height, width and generation time; the page is written from it, with each
preset's description from the one `# Description: ` comment line of its preset file. Cycles renders on the GPU.
"""

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass

from blender_env import ROOT, SOURCE, BlenderEnv

OUT = ROOT / "docs" / "presets"
MANIFEST = OUT / "presets.json"
PAGE = ROOT / "docs" / "presets.md"
GOLDEN = ROOT / "tests" / "golden"
SCRIPT = ROOT / "tools" / "render_presets_in_blender.py"
FIGURE = ROOT / "tools" / "render_assets" / "standing_man.png"
DESCRIPTION = "# Description: "


@dataclass(frozen=True)
class Picture:
    """One preset's picture as the manifest records it."""

    key: str
    image: str
    height_m: float
    width_m: float
    seconds: float


class PresetFiles:
    """The built-in presets: their names, descriptions and picture keys."""

    @staticmethod
    def names() -> list[str]:
        """The names of the built-in presets (source/presets/*.py), sorted."""
        return sorted(path.stem for path in (SOURCE / "presets").glob("*.py"))

    @staticmethod
    def key(name: str) -> str:
        """The hash of everything the preset's picture depends on. Raises SystemExit when its golden file is missing."""
        golden = GOLDEN / f"preset_{name}.json"
        if not golden.is_file():
            raise SystemExit(f"FAILED: {golden} is missing: record the golden trees first (tools/run_tests.py)")
        preset = (SOURCE / "presets" / f"{name}.py").read_bytes()
        settings = preset[preset.index(b"{") :]  # the comments above the settings do not change the picture
        digest = hashlib.sha256(settings)
        for path in (golden, SCRIPT, FIGURE):
            digest.update(path.read_bytes())
        return digest.hexdigest()[:16]

    @staticmethod
    def description(name: str) -> str:
        """The preset's description for the page: its one `# Description: ` comment line. Raises SystemExit when the
        preset has none or more than one."""
        lines = (SOURCE / "presets" / f"{name}.py").read_text(encoding="utf-8").splitlines()
        found = [line.removeprefix(DESCRIPTION) for line in lines if line.startswith(DESCRIPTION)]
        if len(found) != 1:
            raise SystemExit(f"FAILED: preset {name} has {len(found)} '{DESCRIPTION}' lines, it needs exactly one")
        return found[0].strip()


class Manifest:
    """docs/presets/presets.json: the pictures by preset name."""

    @staticmethod
    def read() -> dict[str, Picture]:
        """The recorded pictures (none when the file does not exist yet)."""
        if not MANIFEST.is_file():
            return {}
        data = json.loads(MANIFEST.read_text(encoding="utf-8"))
        return {name: Picture(**entry) for name, entry in data.items()}

    @staticmethod
    def write(pictures: dict[str, Picture]) -> None:
        """Write the pictures, sorted by name."""
        data = {name: asdict(pictures[name]) for name in sorted(pictures)}
        MANIFEST.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


class PresetRender:
    """Which presets need a picture, the run in Blender, and the page."""

    @staticmethod
    def stale(pictures: dict[str, Picture]) -> list[str]:
        """The built-in presets whose picture is missing or has another key."""
        out = []
        for name in PresetFiles.names():
            picture = pictures.get(name)
            if picture is None or picture.key != PresetFiles.key(name) or not (OUT / picture.image).is_file():
                out.append(name)
        return out

    @staticmethod
    def render(names: list[str], pictures: dict[str, Picture], seed: int) -> int:
        """Render `names` in Blender and record their pictures. Returns Blender's exit code."""
        OUT.mkdir(parents=True, exist_ok=True)
        BlenderEnv.install_fresh()
        code = BlenderEnv.run_script(SCRIPT, [str(OUT), str(seed), *names])
        if code != 0:
            return code
        for name in names:
            measures_file = OUT / f"{name}.json"
            if not measures_file.is_file():
                raise SystemExit(f"FAILED: Blender wrote no measures for {name}")
            measures = json.loads(measures_file.read_text(encoding="utf-8"))
            measures_file.unlink()
            pictures[name] = Picture(key=PresetFiles.key(name), image=f"{name}.jpg", **measures)
        return 0

    @staticmethod
    def check(pictures: dict[str, Picture]) -> int:
        """Print whether every picture is up to date. Returns 0 when it is, else 1."""
        stale = PresetRender.stale(pictures)
        if stale:
            print(f"FAILED: pictures missing or out of date: {stale} (run tools/render_presets.py)")
            return 1
        print("presets page: every picture is up to date")
        return 0

    @staticmethod
    def update(requested: list[str], every: bool, pictures: dict[str, Picture], seed: int) -> int:
        """Render the requested presets (none named: every preset when `every`, else the out-of-date ones), drop the
        retired pictures and write the manifest. Returns Blender's exit code. Raises SystemExit on an unknown name."""
        builtin = PresetFiles.names()
        unknown = [name for name in requested if name not in builtin]
        if unknown:
            raise SystemExit(f"FAILED: not built-in presets: {unknown}")
        names = requested
        if not names:
            names = builtin if every else PresetRender.stale(pictures)
        if names:
            print(f"rendering {len(names)}: {', '.join(names)}", flush=True)
            code = PresetRender.render(names, pictures, seed)
            if code != 0:
                return code
        PresetRender.remove_retired(pictures)
        Manifest.write(pictures)
        return 0

    @staticmethod
    def remove_retired(pictures: dict[str, Picture]) -> None:
        """Remove the pictures of presets that are no longer built in."""
        builtin = set(PresetFiles.names())
        for name in sorted(set(pictures) - builtin):
            (OUT / pictures[name].image).unlink(missing_ok=True)
            del pictures[name]
            print(f"removed the picture of {name} (no longer a built-in preset)")

    @staticmethod
    def page(pictures: dict[str, Picture]) -> None:
        """Write docs/presets.md from the pictures. Raises SystemExit when a built-in preset has no picture."""
        missing = [name for name in PresetFiles.names() if name not in pictures]
        if missing:
            raise SystemExit(f"FAILED: no picture for {missing}: run tools/render_presets.py")
        lines = [
            "# The built-in presets",
            "",
            "Every built-in preset of Sapling Tree Gen, with its default seed. The black figure is 1.8 m tall. This",
            "page and its pictures are made by `tools/render_presets.py`; the pictures are CC0.",
            "",
        ]
        for name in PresetFiles.names():
            picture = pictures[name]
            title = name.replace("_", " ").capitalize()
            lines += [
                f"## {title}",
                "",
                f"![{title}](presets/{picture.image})",
                "",
                PresetFiles.description(name),
                "",
                f"Height {picture.height_m:.1f} m, width {picture.width_m:.1f} m. Preset name: `{name}`. "
                f"Generated in {picture.seconds:.2f} s.",
                "",
            ]
        PAGE.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    """Render what the arguments ask for and write the page. Returns 0 on success, else 1."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("presets", nargs="*", help="preset names (default: the new and out-of-date ones)")
    parser.add_argument("--all", action="store_true", help="render every built-in preset")
    parser.add_argument("--check", action="store_true", help="exit 1 when a picture is missing or out of date")
    parser.add_argument("--page", action="store_true", help="only write the page")
    parser.add_argument("--seed", type=int, default=1, help="the seed of every tree")
    args = parser.parse_args()

    pictures = Manifest.read()
    if args.check:
        return PresetRender.check(pictures)
    if not args.page:
        code = PresetRender.update(args.presets, args.all, pictures, args.seed)
        if code != 0:
            return code
    PresetRender.page(pictures)
    print(f"wrote {PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
