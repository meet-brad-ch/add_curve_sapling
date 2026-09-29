# Sapling Tree Gen (Blender 5.2 LTS fork)

**What:** A Blender 5.2 LTS extension that generates parametric trees (Weber–Penn based), with
leaves, pruning, armature and wind animation, forked from the orphaned official Sapling Tree Gen.

**Why:** Upstream is orphaned and broken on Blender 5.x (wind animation crashes); this fork makes
it work on 5.2 LTS, fixes long-standing bugs, restructures the code (OO, tests, lint), and uses
5.2's Thin Wall shading for leaves.

**Status:** partly working — revamp in progress. Tree, leaf and armature generation run on
5.2.2 LTS; the OO restructure, tests and the Thin Wall leaf material are not done yet.

## How to run

Blender is at `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (5.2.2 LTS).

```
blender -c extension validate source
blender -c extension build --source-dir source --output-dir build
blender -c extension install-file -r user_default -e build/sapling_tree_gen-<version>.zip
```

In Blender: *Add > Curve > Sapling Tree Gen*. The settings are in the *Adjust Last Operation*
panel (F9).

**Prerequisites:** Blender 5.2 LTS (Python 3.13 inside Blender). `ruff` 0.11+ for lint.

## Layout

- `source/` — the extension package (`blender_manifest.toml`, Python modules)
- `source/presets/` — built-in tree presets (one Python dict literal per file)

## Decisions

- 2026-09-29 — target Blender 5.2 LTS only; no backward compatibility, so the 5.x animation API
  and the Principled BSDF *Thin Wall* input can be used directly.
- 2026-09-29 — full OO restructure, guarded by golden-output tests recorded before the refactor,
  so every preset still produces the same tree.
- 2026-09-29 — tests run inside headless Blender (`unittest`) against the built and installed
  extension zip in a throwaway user profile, because `bpy.utils.extension_path_user` only accepts
  a real extension package.
- 2026-09-29 — work stays local on branch `revamp-5.2`; nothing is pushed.

## Credits

Upstream: <https://projects.blender.org/extensions/add_curve_sapling> (v0.3.7), originally
written by Andrew Hale (TrumanBlending) and Aaron Buchler, maintained over the years by
CansecoGPC, Campbell Barton, Nika Kutsniashvili and many Blender contributors (see `git log`).
Licensed GPL-3.0-or-later (see `source/blender_manifest.toml`).
