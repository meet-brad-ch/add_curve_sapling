# Troubleshooting

When a setting cannot make a tree, the extension stops and shows a message that names the setting. It removes what it
made, so the scene stays as it was. [Back to the manual](index.md)

## Messages about the settings

| The message names | Cause | What to do |
| --- | --- | --- |
| *Helix* and *Curvature Variation* | With *Helix*, *Curvature Variation* sets the helix angle. It must be less than 90 degrees. | Lower *Curvature Variation* on that level, or turn *Helix* off. |
| *Scale* and *Scale Variation* | Together they can give a tree with a height of 0 or less. | Make *Scale* larger than *Scale Variation*. |
| *Prune Base Height* and *Trunk Height* | With *Prune*, both at 1 give an envelope with no height. | Lower one of them. |
| *Flutter Speed* | With *Leaf Flutter*, the speed must be above 0. | Set *Flutter Speed* above 0. |
| *Leaf Object* | *Instance Faces* and *Instance Points* need a leaf object, and it must exist. | Select a *Leaf Object* on the *Leaves* page, or choose a mesh leaf shape. |
| *Leaf Object* is part of a Sapling tree | The leaf object must be your own object, not a part of a tree. | Choose another object. |
| No room for a trunk | With many *Trunks*, the extension found no free place for one more trunk on the disc round the first. | Use fewer *Trunks*. |

## Messages about presets

| Message | What to do |
| --- | --- |
| The preset exists. Enable Overwrite to replace it | Select *Overwrite*, or type another name. |
| The preset is not found | The preset file was moved or deleted. Choose another preset. |
| Cannot save the preset | The name is empty, has a path in it, or is the name of a built-in preset. Type another name. |
| The settings do not fit this version | The preset comes from a version with other settings. The message names them. |

## Messages about an edit

| Message | What to do |
| --- | --- |
| The settings are not of this version | The tree was made by another version of the extension, which stores its settings in another form. Make the tree again with this version. |
| The object is not part of a Sapling tree | *Edit Sapling Tree* works on the parts of a tree that the extension made. |
| No active collection | Select a collection in the Outliner, then add the tree. |

## A large armature rig

Blender needs more time for each new bone when the rig has more bones. The extension warns above 10,000 bones and
refuses more than 40,000. The message gives the number of bones and the settings that make it smaller: lower *Joint
Levels*, or increase *Joint Length*, on the [Armature](armature.md) page. Wind without a rig needs no bones.

## The playback is slow

- Select *Fast Preview* on the [Animation](animation.md) page while you work.
- Without *Make Mesh*, the wind moves only the joints of the tree, which is faster than a baked mesh.
- Fewer *Leaves* and fewer levels make the tree lighter.
