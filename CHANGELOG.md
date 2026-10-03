# Changelog

## Unreleased

### Added

- 13 presets ported from tree-gen (friggog/tree-gen, GPL-3.0): *Acer*, *Apple*, *Balsam Fir*, *Black
  Oak*, *Black Tupelo*, *Cambridge Oak*, *European Larch*, *Hill Cherry*, *Lombardy Poplar*, *Quaking
  Aspen Treegen*, *Sassafras*, *Silver Birch* and *Sphere Tree*. Its Weber–Penn values are mapped to the
  settings of Sapling by `tools/port_treegen.py`, checked against renders of tree-gen's own trees in
  Blender 5.2. Not carried over: blossoms (Apple, Hill Cherry), helix stems (Black Oak, Sphere Tree) and
  random branch bending, which Sapling does not have. *Cambridge Oak* takes about 15 s to generate.
  tree-gen's palm, fan palm and bamboo are not ported (no multi-stem clumps or fronds in Sapling).

### Changed

- *Douglas Fir* and *Willow* are replaced with tree-gen's Douglas fir and weeping willow. The old
  presets loaded bare: Douglas Fir had leaves off and hexagon leaves, and Willow had only 2 of its
  4 levels and almost no leaves.
- Split angles from tree-gen are halved: tree-gen tilts each fork by half its split angle, Sapling by the
  full angle, so the trunk forks spread into near-horizontal limbs (seen first on the willow).
- Ported presets take tree-gen's defaults for values a species leaves out: *Black Tupelo* and *Douglas Fir*
  get its slight upward bend of the fine branches. *Silver Birch* leaves are 0.7 as wide as long (the
  heart-shaped leaf's real proportion), not 1.0.
- *Quaking Aspen* has 3 levels again, as in the original preset from 2011. A 2016 rewrite had cut it to
  2, which left it nearly bare (882 leaves, now about 12,000).
- *Quaking Aspen* and *Weeping Willow* load with their leaves. Both were saved with Show Leaves off
  since 2011, so they were the only presets whose leaves had to be turned on by hand.
- Pruning removes a stem that would keep less than 15 % of its length when *Prune Ratio* is 1, as
  tree-gen does. Before, such stems became stubs of about 1 cm: invisible, but their leaves floated
  next to the branches.
- The pruning envelope is hidden after generation. Its two profile curves showed as lines in the
  viewport; *Object Properties > Visibility* shows them again.
- *Limit Import* is off by default. With it on, every preset loaded with 2 levels and no leaves, so
  trees with more levels looked bare when the leaves were turned on.

## 0.4.0 — Blender 5.2 LTS revamp (2026-09-29)

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
