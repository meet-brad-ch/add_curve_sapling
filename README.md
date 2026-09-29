# Sapling Tree Gen (Blender 5.2 LTS fork)

**What:** A Blender 5.2 LTS extension that generates parametric trees (Weber–Penn based), with
leaves, pruning, armature and wind animation, forked from the orphaned official Sapling Tree Gen.

**Why:** Upstream is orphaned and broken on Blender 5.x (wind animation crashes); this fork makes
it work on 5.2 LTS, fixes long-standing bugs, restructures the code (OO, tests, lint), and uses
5.2's Thin Wall shading for leaves.

**Status:** working on Blender 5.2.2 LTS — generation, pruning, armature, wind, presets, re-edit
and the Thin Wall leaf material are done and tested headless; the redo panel and wind playback
still need a check by hand in the Blender UI.

## How to run

Blender is at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (5.2.2 LTS); set
`BLENDER` to use another one. `ruff` 0.11+ must be on PATH.

```
python tools/check.py            # the full gate: ruff check, ruff format --check, manifest, tests
python tools/run_tests.py        # tests only (-k NAME filters, --record-golden rewrites golden)
blender -c extension build --source-dir source --output-dir build
blender -c extension install-file -r user_default -e build/sapling_tree_gen-0.4.0.zip
```

The tests build the extension zip and install it into a throwaway profile under
`build/test-profile` (`BLENDER_USER_RESOURCES`), so your own Blender profile is never touched.

**Prerequisites:** Blender 5.2 LTS (Python 3.13 inside Blender), Python 3.10+ to run the tools,
`ruff` 0.11+.

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
- **Instance Points** leaves put your leaf object on every leaf point with a Geometry Nodes
  modifier (*Sapling Leaf Instancer*), rotated per leaf; the leaf object itself is not moved.

## Layout

- `source/` — the extension package
  - `model/` — tree growth on the curve: `TreeGrower`, `StemPruner`, `StemGrower`,
    `BranchSpawner`, `SproutPlanner`, `LeafGenerator`, `TreeParams`, geometry helpers
  - `build/` — Blender objects: curve, leaves, armature, wind, skin mesh, materials, tree record
  - `ui/` — the Add Tree operator, its properties and pages, panels and menus
  - `generator.py` (`TreeGenerator`), `settings.py` (`TreeSettings`), `presets.py` (`PresetStore`)
  - `presets/` — built-in presets (one Python dict literal each)
- `tests/` — unittest suite run inside headless Blender; `tests/golden/` holds exact fingerprints
  of 38 generated trees
- `tools/` — `check.py`, `run_tests.py`, `blender_env.py`

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

## Credits

Upstream: <https://projects.blender.org/extensions/add_curve_sapling> (v0.3.7), originally
written by Andrew Hale (TrumanBlending) and Aaron Buchler, maintained over the years by
CansecoGPC, Campbell Barton, Nika Kutsniashvili and many Blender contributors (see `git log`).
Licensed GPL-3.0-or-later (see `source/blender_manifest.toml`).
