# Sapling Tree Gen (Blender 5.2 LTS fork)

**What:** A Blender 5.2 LTS extension that generates parametric trees (Weber–Penn based), with
leaves, pruning, armature and wind animation, forked from the orphaned official Sapling Tree Gen.

**Why:** Upstream is orphaned and broken on Blender 5.x (wind animation crashes); this fork makes
it work on 5.2 LTS, fixes long-standing bugs, restructures the code (OO, tests, lint), and uses
5.2's Thin Wall shading for leaves.

**Status:** working on Blender 5.2.2 LTS — generation, pruning, armature, wind, presets, re-edit
and the Thin Wall leaf material are done, reviewed and tested headless (74 tests, 98.7 % branch
coverage) and checked by hand in the Blender 5.2.2 UI (2026-09-29); it generates trees 18–56 %
faster than 0.3.7 (see Performance).

## How to run

Blender is at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (5.2.2 LTS); set
`BLENDER` to use another one.

```
py -3.13 -m venv .venv                                  # once: Python 3.13, the same as Blender 5.2's
.venv/Scripts/python -m pip install -r requirements-dev.txt
git config core.hooksPath tools/hooks                   # once: the fast gate before each commit
python tools/check.py            # the full gate: ruff, format, mypy, manifest, tests with branch coverage
python tools/check.py --fast     # the same without the Blender tests (what the pre-commit hook runs)
python tools/run_tests.py        # tests only (-k NAME filters, --record-golden rewrites golden)
blender -c extension build --source-dir source --output-dir build
blender -c extension install-file -r user_default -e build/sapling_tree_gen-0.4.0.zip
```

The tests build the extension zip and install it into a throwaway profile under
`build/test-profile` (`BLENDER_USER_RESOURCES`), so your own Blender profile is never touched.

Coverage runs inside Blender: the runner puts the venv's `coverage` package on Blender's
`sys.path` (both are Python 3.13, so its C tracer loads) and fails below `COVERAGE_MIN` in
`tools/check.py`.

**Prerequisites:** Blender 5.2 LTS (Python 3.13 inside Blender), Python 3.10+ to run the tools,
Python 3.13 for the `.venv` (ruff, mypy, coverage and the Blender stubs, pinned in
`requirements-dev.txt`).

## Using it

- *Add > Curve > Sapling Tree Gen* adds a tree at the 3D cursor. Its settings are in the
  *Adjust Last Operation* panel (F9), on eight pages (Geometry … Animation).
- **Presets:** Geometry page. Pick one from the list (it applies immediately; *Limit Import*
  keeps it to 2 levels without leaves, for speed), or type a name and *Save Preset*. Your presets
  are stored in the extension's user folder (`extensions/.user/<repo>/sapling_tree_gen/presets`).
- **Edit Sapling Tree:** select any part of a generated tree; the *Sapling* sidebar tab (N) and
  the *Object* menu re-open the settings it was made with and regenerate it in place (same
  transform, parent and collection; objects you parented to it stay attached).
- **Leaf Material** (Leaves page, on by default): mesh leaves get *Sapling Leaf*, a Principled
  BSDF in Blender 5.2's **Thin Wall** mode with thin subsurface scattering, so light shines
  through the leaves. Branches get *Sapling Bark*. Both are created once and then reused, so
  your edits to them are kept.
- **Armature:** the bones are hidden after generation (bone collection *Sapling Bones*); show
  them with its eye icon in *Armature properties > Bone Collections*. The armature object, the
  top of the tree, stays visible and selected, so the whole tree can be moved right away. *Fast
  Preview* shows the bones instead of the tree.
- **Instance Points** leaves put your leaf object on every leaf point with a Geometry Nodes
  modifier (*Sapling Leaf Instancer*), rotated per leaf; the leaf object itself is not moved.

## Performance

Generation time per built-in preset with leaves on, Blender 5.2.2, Windows. 0.3.7: median of 5,
measured 2026-09-29 before the revamp's performance work. 0.4.0: `python tools/bench.py` (median
of 5 per preset), run 3 times on 2026-09-29 after the code review; the table shows the median of
the 3 runs. Two unrelated jobs kept 2 of the 24 logical cores busy during these runs, and the runs
differed by up to about ±12 % per preset (weeping_willow 573–715 ms), so read the changes as
approximate.

| Preset | Leaves | 0.3.7 (upstream) | 0.4.0 | Change |
| --- | ---: | ---: | ---: | ---: |
| callistemon | 9 588 | 145 ms | 86 ms | −40 % |
| douglas_fir | 52 454 | 1 437 ms | 727 ms | −49 % |
| japanese_maple | 106 800 | 4 418 ms | 1 934 ms | −56 % |
| quaking_aspen | 882 | 16 ms | 12 ms | −25 % |
| small_maple | 36 290 | 862 ms | 516 ms | −40 % |
| small_pine | 48 607 | 881 ms | 600 ms | −32 % |
| weeping_willow | 62 340 | 993 ms | 592 ms | −40 % |
| white_birch | 18 918 | 495 ms | 310 ms | −37 % |
| willow | 1 328 | 59 ms | 48 ms | −18 % |

The gains come from growth no longer being O(n²) (Blender walks the spline list on every
`len(curve.splines)`; unpruned stems copied the bone map), and from leaf rotations built once
instead of per vertex. The benchmark is not part of the gate: timings depend on the machine.

## Layout

- `source/` — the extension package
  - `model/` — tree growth on the curve: `TreeGrower`, `StemBuilder`, `StemGrower`,
    `BranchSpawner`, `SproutPlanner`, `LeafGenerator`, `TreeParams`, geometry helpers
  - `build/` — Blender objects: curve, leaves, armature, wind, skin mesh, materials, tree record
  - `ui/` — the Add Tree operator, its properties and pages, panels and menus
  - `generator.py` (`TreeGenerator`), `settings.py` (`TreeSettings`), `presets.py` (`PresetStore`)
  - `presets/` — built-in presets (one Python dict literal each)
- `tests/` — unittest suite run inside headless Blender; `tests/golden/` holds exact fingerprints
  of 38 generated trees; `test_fuzz` grows 100 trees from random settings; `test_architecture`
  checks the layering and the no-module-state rule
- `tools/` — `check.py` (the gate), `run_tests.py`, `bench.py` (+ `bench_in_blender.py`,
  `bench_baseline.json`), `blender_env.py`, `hooks/pre-commit`

## Decisions

- 2026-09-29 — target Blender 5.2 LTS only; no backward compatibility, so the 5.x animation API
  and the Principled BSDF *Thin Wall* input can be used directly.
- 2026-09-29 — full OO restructure, guarded by golden-output tests recorded before the refactor,
  so every preset still produces the same tree.
- 2026-09-29 — tests run inside headless Blender (`unittest`) against the built and installed
  extension zip in a throwaway user profile, because `bpy.utils.extension_path_user` only accepts
  a real extension package.
- 2026-09-29 — work stays local on branch `revamp-5.2`; nothing is pushed.
- 2026-09-29 — stems grow on real bpy curve splines, not in a pure-Python model: Blender computes
  bezier handles in C on every write and stores float32, and the trees depend on both.
- 2026-09-29 — golden fingerprints hash exact float32 values (no rounding); they are valid for
  Blender 5.2.2 on Windows and are re-recorded only in their own commits, with the reason.
- 2026-09-29 — pruning grows its search passes in a scratch curve and copies the final pass into
  the tree, so spline order, stem indices and bone names stay aligned (issue #4).
- 2026-09-29 — leaves use Thin Wall + Subsurface Weight 1.0 (translucent), not Thin Wall +
  Transmission (clear like glass): measured on a backlit leaf, see `CHANGELOG.md`.
- 2026-09-29 — Instance Points leaves use a Geometry Nodes instancer with a stored rotation per
  leaf: vertex normals can no longer be set (Blender 4.1+), so vertex instancing lost the rotation.
- 2026-09-29 — fail fast: no silent defaults or fallbacks. Errors the user can fix are
  `SettingsError` (with `PresetError`), which the operator's `execute` reports and cancels on — the
  only catch; everything else raises with a message that names the thing.
- 2026-09-29 — a tree is its root plus the descendants carrying the root's id (not every object
  with the tag), and Edit builds the new tree before removing the old one, so a failed edit
  keeps the old tree and a failed Add leaves nothing.
- 2026-09-29 — quality gates in `tools/check.py`: ruff (with complexity ≤ 10, docstrings and
  annotations for `source/`), mypy with typed signatures, and branch coverage ≥ 98 % measured
  inside Blender. A `type: ignore` is allowed only with its reason (stub gaps, values Blender
  always sets); `warn_unused_ignores` flags the ones that become unnecessary.
- 2026-09-29 — the armature's bones are hidden after generation through a hidden bone collection,
  not by hiding the armature object: a hidden object is deselected and left out of
  Move/Rotate/Scale (measured on 5.2.2), and the armature is the tree's root (owner's choice).

## Credits

Upstream: <https://projects.blender.org/extensions/add_curve_sapling> (v0.3.7), originally
written by Andrew Hale (TrumanBlending) and Aaron Buchler, maintained over the years by
CansecoGPC, Campbell Barton, Nika Kutsniashvili and many Blender contributors (see `git log`).
Licensed GPL-3.0-or-later (see `source/blender_manifest.toml`).
