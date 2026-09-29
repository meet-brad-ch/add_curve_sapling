# Changelog

## 0.4.0 — Blender 5.2 LTS revamp (unreleased)

Requires Blender 5.2 LTS.

### Fixed

- Wind and leaf animation crashed on Blender 5.x (`'Action' object has no attribute 'fcurves'`).
  Unlike upstream PR #7, each leaf's sway stays on its own leaf bone.
- Armature on a pruned tree failed (`KeyError: bone084.002`, issue #4) or hung bones on the wrong
  branches: pruning corrupted the spline-to-bone map and reordered the splines.
- `IndexError` in `interpStem` with a high Branch Distribution on pruned trees.
- A second tree's skin mesh used the first tree's armature.
- Leaf instance objects named N, O, NE, ONE, … were ignored (substring test).
- Close Tip and the last level's base size did nothing on trees with 5 or 6 levels.
- With Bone Step > 1: bone tail radius taken from the wrong point; the second trunk bone swayed.
- Instance Points leaves were rotated by their position instead of their normal (vertex normals
  are read-only since Blender 4.1): now a Geometry Nodes instancer with a rotation per leaf.
- Choosing a preset only took effect on the next change; it now applies immediately.
- Saving a preset ran `eval()` on operator data; names are now validated (no path traversal, no
  overwriting built-in presets) and files are UTF-8.
- The add-on reseeded Python's shared `random` module; it now has its own generator (same trees).
- Armature creation deselected the whole scene and left the armature in an odd active state.
- Typos and unclear labels in the panel.

### Added

- **Leaf Material** (on by default): mesh leaves get *Sapling Leaf*, a Principled BSDF in Thin
  Wall mode with Subsurface Weight 1.0, so light scatters through the leaves; EEVEE uses
  Thickness mode Slab with Thickness 0. Branches get *Sapling Bark*.
  Measured on a single backlit leaf seen from its unlit side (mean green): Cycles opaque 0.11 →
  0.54; Thin Wall + Transmission 0.3 gives 0.76 but looks like clear glass, so it was not used.
  EEVEE opaque 0.11 → 0.23. On a backlit tree in Cycles, leaf pixels are 2.3× brighter.
- **Edit Sapling Tree** (sidebar *Sapling* tab and *Object* menu): regenerate a tree from the
  settings stored on it, in place.
- New trees are added at the 3D cursor, in the active collection, selected and active.

### Changed

- The code is rewritten as classes (`model/`, `build/`, `ui/`); the generated trees are
  bit-identical to 0.3.7 for every built-in preset, except where a fix above changes them.
- User presets live in the extension's user folder.
