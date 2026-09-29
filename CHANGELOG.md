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
- Presets leaked values into each other: a preset that lacks settings (willow lacks about 35)
  kept those of the preset loaded before it. Every preset now sets every generation setting.
- A preset that failed to load only printed to the console; the operator now reports it and
  cancels. Unreadable, malformed or badly named user preset files are listed with the reason.
- Armature Levels 0 took the 4th level's Bone Step for the leaves, so with Make Mesh the leaves
  hung on the parent branch; Armature Levels above 4 raised `IndexError`.
- Making the armature also put any other selected armature into edit mode.
- Calling `curve.tree_add` from a script with a UI-only keyword (`chooseSet`, `limitImport`)
  made no tree.
- Instanced leaves without a leaf object failed late; they now cancel before anything is made.
- *Leaf Material* went onto Instance Points leaves, which have no faces.
- *Make Mesh* without an armature left the skin mesh outside the tree (not parented to it).

### Added

- **Leaf Material** (on by default): mesh leaves get *Sapling Leaf*, a Principled BSDF in Thin
  Wall mode with Subsurface Weight 1.0, so light scatters through the leaves; EEVEE uses
  Thickness mode Slab with Thickness 0. Branches get *Sapling Bark*.
  Measured on a single backlit leaf seen from its unlit side (mean green): Cycles opaque 0.11 →
  0.54; Thin Wall + Transmission 0.3 gives 0.76 but looks like clear glass, so it was not used.
  EEVEE opaque 0.11 → 0.23. On a backlit tree in Cycles, leaf pixels are 2.3× brighter.
- **Edit Sapling Tree** (sidebar *Sapling* tab and *Object* menu): regenerate a tree from the
  settings stored on it, in place: same transform, parent (object, bone or vertex parent) and
  collections; your objects parented to the tree are re-attached, or listed in a warning when
  their part of the tree is gone. The new tree is built before the old one is removed, so a
  failed edit keeps the old tree; a duplicated tree (Shift+D) is edited on its own.
- New trees are added at the 3D cursor, in the active collection, selected and active.

### Changed

- The code is rewritten as classes (`model/`, `build/`, `ui/`); the generated trees are
  bit-identical to 0.3.7 for every built-in preset, except where a fix above changes them.
- User presets live in the extension's user folder.
- Faster generation: the spline count Blender walks as a linked list and the per-stem pruning
  snapshots made growth O(n²), and leaf rotations were rebuilt per vertex. The built-in presets
  generate 18–56 % faster than in 0.3.7 (japanese_maple 4.4 s → 1.9 s); see the README.
- Wind F-curves are grouped by bone in the Graph Editor.
- The tree curve is always the top object; the armature hangs under it (it was the other way
  round). Clicking the branches and moving the tree used to pull the curve and the leaves away
  from their bones; now the whole tree moves.
- The armature's bones are hidden after generation, in the bone collection *Sapling Bones*.
  *Fast Preview* shows them and draws the tree as its bounding box (it hid the tree).
- Errors fail fast with a message instead of silent defaults; a failed Add leaves nothing behind.
- The settings stored on a tree are versioned JSON.
- Development: `tools/check.py` gates ruff (complexity ≤ 10, docstrings, annotations), mypy,
  the manifest and the Blender test suite with branch coverage ≥ 98 %; a pre-commit hook runs
  the fast part. Tests include 38 exact golden trees, 100 fuzzed trees and architecture checks.
