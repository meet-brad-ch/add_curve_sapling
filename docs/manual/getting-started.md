# Getting started

## Add a tree

1. In the 3D view, select *Add > Curve > Sapling Tree Gen*. The extension adds a tree at the 3D cursor.
2. Open the *Adjust Last Operation* panel at the bottom left of the 3D view (or press F9).
3. On the *Geometry* page, select a preset in the *Presets* menu. The tree changes to the preset.
4. Change the settings on the nine pages. The tree changes after each change.

The tree is one object, *tree*. Its other parts (the branch curves, the leaves, the blossoms, the rig) are children of
it. When you move, turn or scale the tree, all parts move with it.

## Save your own preset

1. On the *Geometry* page, type a name in the field under the *Presets* menu.
2. Click *Save Preset*. To replace a preset of the same name, select *Overwrite* first.

Your presets are in the user folder of the extension, so an update of the extension keeps them. They show in the
*Presets* menu with the built-in presets.

## Edit a tree later

The *Adjust Last Operation* panel closes when you do another operation. To change a tree later:

1. Select a part of the tree.
2. In the sidebar of the 3D view (press N), open the *Sapling* tab and click *Edit Sapling Tree*. The *Object* menu
   has the same command.
3. The settings that made the tree open again in the *Adjust Last Operation* panel. Change them.

The extension makes the tree again in the same place. The tree keeps its transform, its parent, its collections and
its children.

## Duplicate a tree

Press Shift+D or Alt+D, as for other objects. The copy is a whole tree, with all its parts, and you can edit it
separately. *Duplicate Sapling Tree* in the *Sapling* tab does the same from any part of the tree.

## Add wind

1. On the *Animation* page, select *Wind*. Select *Leaf Flutter* to make the leaves move too.
2. Play the animation (Space).

The wind needs no bones: Geometry Nodes move the branches. *Fast Preview* makes the playback faster while you work.
See [Animation](animation.md).

## Add an armature rig

1. On the *Armature* page, select *Armature Rig*.
2. *Joint Levels* and *Joint Length* set the number of bones. Fewer bones build faster.

With *Wind*, the wind moves the bones. See [Armature](armature.md).

## Export the tree

The branches are a live Geometry Nodes sweep. An export with modifiers applied (for example glTF or FBX) writes them
as a mesh. To keep a plain mesh in Blender, select *Make Mesh* on the *Armature* page. With a rig, the extension
weights the mesh to the bones, so it exports as a skinned mesh.
