# Sapling Tree Gen manual

Sapling Tree Gen adds parametric trees and shrubs to Blender, with leaves, blossoms, an armature rig and wind
animation. This manual tells how to use it and what each setting does.

- [Getting started](getting-started.md): add a tree, choose a preset, change it, edit it later, add wind or a rig,
  export it.
- [Troubleshooting](troubleshooting.md): the messages of the extension and what to do.
- [The presets](../presets.md): a picture of each built-in preset.

## Where the settings are

You add a tree with *Add > Curve > Sapling Tree Gen*. Its settings are in the *Adjust Last Operation* panel at the
bottom left of the 3D view (or press F9). The panel has nine pages. Select a page in the *Settings* menu at the top of
the panel.

| Page | What it sets |
| --- | --- |
| [Geometry](geometry.md) | The bevel and the resolution, the crown shape, the scale, the random seed, the presets |
| [Branch Radius](branch-radius.md) | The thickness of the trunk and the branches |
| [Branch Splitting](branch-splitting.md) | The levels, the trunks, the splits and the number of branches |
| [Branch Angles](branch-angles.md) | The angles of the splits and the branches |
| [Branch Growth](branch-growth.md) | The length and the curvature of the branches |
| [Pruning](pruning.md) | The pruning envelope and the shape that the wind gives the crown |
| [Leaves](leaves.md) | The leaves and the blossoms |
| [Armature](armature.md) | The armature rig and the baked mesh |
| [Animation](animation.md) | The wind animation |

## Levels

A tree grows in levels. Level 1 is the trunk. Level 2 is the branches that grow from the trunk. Level 3 is the
branches that grow from level 2, and so on. Many settings have one value for each level: the panel shows them in one
row, under the heading *Level 1* to *Level 4*. The panel draws the values of the levels that the tree does not have
(above *Levels*) inactive, because they have no effect.

## Pictures

Each picture shows one preset with one setting at three values, at true scale. The black figure is 1.8 m tall.
