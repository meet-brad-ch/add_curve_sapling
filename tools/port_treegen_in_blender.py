# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/port_treegen.py: tree-gen species parameters -> Sapling preset files.

tree-gen (https://github.com/friggog/tree-gen) implements Weber-Penn like Sapling. The mapping below follows
both projects' code (tree-gen parametric/gen.py, Sapling source/model):

- Each species is merged over tree-gen's own defaults (tree_param.py), as tree-gen does.
- Per-level arrays with the same Weber-Penn meaning are copied; branches[0] is the number of trunks (Trunks).
  tree-gen turns each trunk of a clump to face out, so it curves away from the centre: Trunks Face Out.
- tree-gen counts a level's branches above the bare base and keeps leaves off the last level's bare base too:
  Count Above Base and Leaves Above Base are on. Fan leaves tilt by the down angle and vary their turn: Fan
  Angles is on for a negative leaf count.
- Trunk length is scale * length[0] in both; Sapling's scale0/scaleV0 only scale the trunk radius.
- base_size per level -> baseSize = base_size[0], baseSize_s = base_size[1] / base_size[0]
  (Sapling: level n base size = baseSize * baseSize_s ** n; at most 1, so a longer level-1 base is clamped).
- Negative down_angle_v (vary along the parent) is the Weber-Penn formula Sapling has as useOldDownAngle.
  For the leaves the signs are the other way round: tree-gen's down_angle_v >= 0 is a random variation, which
  is Sapling's negative Leaf Down Angle Variation, so the leaf value is negated.
- flare f: tree-gen multiplies the trunk base radius by 1 + 0.99 f, which is Sapling's rootFlare.
- tropism z: tree-gen bends level 2 and deeper by it (only its horizontal part on levels 0-1); Sapling's
  attractUp is per level, vertical only.
- Negative curve_v draws a helix in tree-gen: Helix on that level, with |curve_v| as the helix angle.
- bend_v is Bend Variation (its size; tree-gen draws the sign).
- Blossoms: blossom_rate is Blossom Rate, blossom_shape 1/2/3 is cherry/orange/magnolia, and Blossom Scale is
  blossom_scale times the width of tree-gen's blossom geometry (leaf_shapes.py `blossom()`), as Sapling's
  templates are 1 across.
- Leaves: leaf_blos_num per last-level stem -> leaves (negative: a fan at the stem tip in both). Leaf length is
  leaf_scale in both; the width is the tree-gen shape's width (from its leaf_shapes.py geometry) times
  leaf_scale_x; linear leaves become rect, all others hex. Leaves take level 3's down and rotate angles.
- radius_mod -> radiusTweak and the pruning envelope are set only when they do something (not all ones, prune
  on); otherwise Sapling's defaults stay.
- taper above 1: tree-gen tapers by 2 - taper up to 2 and not at all from 2 on (with a rounded end Sapling
  cannot draw); Sapling's taper ends at 1, so it gets the same amount of taper.
- Split angles are halved: tree-gen tilts each fork (and the continuing stem) by half the split angle, so
  the forks end up split_angle apart; Sapling turns each new fork by its full split angle. tree-gen then
  turns the forks back toward the stem's direction over their remaining segments; Sapling cannot.
- Negative base_splits: tree-gen only reads base_splits when it is positive, so it means no base splits.
- Not mapped: leaf_bend (a different method).
- Display settings every upstream preset sets: bevel on (the add-on default draws wire branches), bevel
  resolution 1, minimum radius 0.0015, no trunk radius variation.
"""

import ast
import sys
from pathlib import Path
from typing import Any

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entry above)

LINEAR = 2  # tree-gen leaf shape ids: 1 ovate, 2 linear, 3 cordate, ... 8 elliptic (default), 10 triangle
BLOSSOM_SHAPES = {1: "cherry", 2: "orange", 3: "magnolia"}  # tree-gen blossom_shape -> Blossom Shape
DEFAULT_LEAF = 8
NEUTRAL_RADIUS = [1, 1, 1, 1]


def literal_dict(path: Path) -> dict[str, Any]:
    """The first dictionary literal in a tree-gen parameter file."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Dict):
            return ast.literal_eval(node)
    raise SystemExit(f"{path}: no parameter dictionary")


def shape_points(path: Path, function: str) -> list[list[tuple]]:
    """The vertex lists of the shapes a leaf_shapes.py function (`leaves` or `blossom`) returns, in order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function)
    returned = next(n for n in ast.walk(found) if isinstance(n, ast.Return)).value
    if isinstance(returned, ast.Subscript):  # `return [shape, shape, ...][t]`
        returned = returned.value
    if not isinstance(returned, ast.List):
        raise SystemExit(f"{path}: {function}() does not return a list")
    shapes = []
    for shape_id, shape in enumerate(returned.elts, start=1):
        if not (isinstance(shape, ast.Tuple) and isinstance(shape.elts[0], ast.List)):
            raise SystemExit(f"{path}: {function} shape {shape_id} has an unexpected form")
        shapes.append([ast.literal_eval(call.args[0]) for call in shape.elts[0].elts if isinstance(call, ast.Call)])
    return shapes


def leaf_widths(path: Path) -> dict[int, float]:
    """tree-gen leaf shape id -> width / length, from the vertices in leaf_shapes.py `leaves()`."""
    widths = {}
    for shape_id, points in enumerate(shape_points(path, "leaves"), start=1):
        xs, zs = [p[0] for p in points], [p[2] for p in points]
        widths[shape_id] = (max(xs) - min(xs)) / (max(zs) - min(zs))
    return widths


def blossom_widths(path: Path) -> dict[int, float]:
    """tree-gen blossom shape id -> its width across (x), from the vertices in leaf_shapes.py `blossom()`."""
    return {
        shape_id: max(p[0] for p in points) - min(p[0] for p in points)
        for shape_id, points in enumerate(shape_points(path, "blossom"), start=1)
    }


def per_level(values: list, cast: type = float) -> tuple:
    return tuple(cast(v) for v in (list(values) + [0, 0, 0, 0])[:4])


class Porter:
    def __init__(self, treegen: Path, commit: str) -> None:
        self.treegen = treegen
        self.commit = commit
        params = treegen / "parametric" / "tree_params"
        self.params_dir = params
        self.defaults_tg = literal_dict(params / "tree_param.py")
        self.widths = leaf_widths(treegen / "leaf_shapes.py")
        self.blossom_widths = blossom_widths(treegen / "leaf_shapes.py")
        package = sys.modules[MODULE + ".ui.operators"]
        self.names = package.AddTreeOperator.generation_names()
        self.rna = bpy.ops.curve.tree_add.get_rna_type().properties
        settings_cls = sys.modules[MODULE + ".settings"].TreeSettings
        self.defaults = settings_cls.defaults_from_rna(self.rna, self.names).values

    def convert(self, species: str) -> tuple[dict[str, Any], list]:
        """(Sapling settings, clamped values) for one tree-gen species."""
        tg = {**self.defaults_tg, **literal_dict(self.params_dir / f"{species}.py")}
        s = dict(self.defaults)
        levels = int(tg["levels"])
        leaf_level = min(levels, 3)  # tree-gen orients leaves with the next level's angles
        tropism_z = float(tg["tropism"][2])
        base = tg["base_size"]
        leaf_shape = abs(int(tg["leaf_shape"]))
        if not 1 <= leaf_shape <= 10:
            leaf_shape = DEFAULT_LEAF
        s.update(
            bevel=True,
            bevelRes=1,
            minRadius=0.0015,
            scaleV0=0.0,
            shape=str(abs(int(tg["shape"]))),
            scale=float(tg["g_scale"]),
            scaleV=float(tg["g_scale_v"]),
            levels=levels,
            ratio=float(tg["ratio"]),
            ratioPower=float(tg["ratio_power"]),
            rootFlare=1 + 0.99 * float(tg["flare"]),
            baseSplits=max(0, int(tg["base_splits"])),
            baseSize=float(base[0]),
            baseSize_s=float(base[1]) / float(base[0]) if base[0] else 0.25,
            trunks=max(1, int(tg["branches"][0])),
            trunksFaceOut=int(tg["branches"][0]) > 1,
            branches=(0, *per_level(tg["branches"], int)[1:]),
            countAboveBase=True,
            leavesAboveBase=True,
            length=per_level(tg["length"]),
            lengthV=per_level(tg["length_v"]),
            downAngle=per_level(tg["down_angle"]),
            downAngleV=per_level(tg["down_angle_v"]),
            useOldDownAngle=True,
            rotate=per_level(tg["rotate"]),
            rotateV=per_level(tg["rotate_v"]),
            taper=tuple(Porter.taper(v) for v in per_level(tg["taper"])),
            segSplits=per_level(tg["seg_splits"]),
            splitAngle=tuple(v / 2 for v in per_level(tg["split_angle"])),
            splitAngleV=tuple(v / 2 for v in per_level(tg["split_angle_v"])),
            curveRes=tuple(max(1, v) for v in per_level(tg["curve_res"], int)),
            curve=per_level(tg["curve"]),
            curveBack=per_level(tg["curve_back"]),
            curveV=tuple(abs(v) for v in per_level(tg["curve_v"])),
            helix=tuple(v < 0 for v in per_level(tg["curve_v"])),
            bendV=tuple(abs(v) for v in per_level(tg["bend_v"])),
            attractUp=(0.0, 0.0, tropism_z, tropism_z),
            branchDist=1.0,
            showLeaves=True,
            leaves=int(tg["leaf_blos_num"]),
            leafDist="3",  # cylindrical: the count is not shaped along the stem, as in tree-gen
            leafShape="rect" if leaf_shape == LINEAR else "hex",
            leafScale=float(tg["leaf_scale"]),
            leafScaleX=self.widths[leaf_shape] * float(tg["leaf_scale_x"]),
            leafDownAngle=float(tg["down_angle"][leaf_level]),
            leafDownAngleV=-float(tg["down_angle_v"][leaf_level]),
            fanAngles=int(tg["leaf_blos_num"]) < 0,
            leafRotate=float(tg["rotate"][leaf_level]),
            leafRotateV=float(tg["rotate_v"][leaf_level]),
        )
        blossom = int(tg["blossom_shape"])
        if float(tg["blossom_rate"]) > 0:
            s.update(
                blossomRate=float(tg["blossom_rate"]),
                blossomShape=BLOSSOM_SHAPES[blossom],
                blossomScale=float(tg["blossom_scale"]) * self.blossom_widths[blossom],
            )
        if list(tg["radius_mod"]) != NEUTRAL_RADIUS:
            s["radiusTweak"] = per_level(tg["radius_mod"])
        if float(tg["prune_ratio"]) > 0:
            # The same Weber-Penn envelope; tree-gen measures it from the trunk's base size
            s.update(
                prune=True,
                pruneRatio=float(tg["prune_ratio"]),
                pruneWidth=float(tg["prune_width"]),
                pruneWidthPeak=float(tg["prune_width_peak"]),
                prunePowerLow=float(tg["prune_power_low"]),
                prunePowerHigh=float(tg["prune_power_high"]),
                pruneBase=float(base[0]),
            )
        clamped = self.clamp(s)
        if set(s) != set(self.names):
            raise SystemExit(f"{species}: settings do not match the add-on's generation settings")
        return s, clamped

    @staticmethod
    def taper(value: float) -> float:
        """tree-gen taper -> Sapling taper (the same amount of taper; see the module docstring)."""
        if value <= 1:
            return value
        return max(0.0, 2 - value)

    def clamp(self, s: dict[str, Any]) -> list:
        """Clamp numbers to the operator's hard limits; return what was changed."""
        clamped = []
        for key, value in s.items():
            prop = self.rna[key]
            if prop.type not in {"FLOAT", "INT"}:
                continue
            vector = isinstance(value, tuple | list)
            values = list(value) if vector else [value]
            fixed = [min(max(v, prop.hard_min), prop.hard_max) for v in values]
            if fixed != values:
                clamped.append((key, value, fixed))
                s[key] = tuple(fixed) if vector else fixed[0]
        return clamped

    def header(self, species: str) -> str:
        text = (self.params_dir / f"{species}.py").read_text(encoding="utf-8")
        title = text.split('"""')[1].strip().title()
        lines = [
            "# SPDX-FileCopyrightText: 2017-2021 Charlie Hewitt and tree-gen contributors",
            "# SPDX-FileCopyrightText: 2026 Brad Chamberlain",
            "#",
            "# SPDX-License-Identifier: GPL-3.0-only",
            "#",
            f"# {title}. Ported from tree-gen (https://github.com/friggog/tree-gen, GPL-3.0),",
            f"# parametric/tree_params/{species}.py at commit {self.commit}: its Weber-Penn parameters mapped to"
            " Sapling's.",
        ]
        return "\n".join(lines) + "\n\n"


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    treegen, commit, presets = Path(args[0]), args[1], Path(args[2])
    bpy.ops.preferences.addon_enable(module=MODULE)
    porter = Porter(treegen, commit)
    for spec in args[3:]:
        species, _, preset = spec.partition(":")
        settings, clamped = porter.convert(species)
        path = presets / f"{preset or species}.py"
        path.write_text(
            porter.header(species) + repr(dict(sorted(settings.items()))) + "\n", encoding="utf-8", newline="\n"
        )
        print(f"PORTED {species} -> {path.name}; clamped: {clamped or 'nothing'}")
    sys.stdout.flush()


main()
