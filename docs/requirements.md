# Software requirements

These are the requirements of the Sapling Tree Gen extension, version 1.0.0. They state what the extension does. A
function that no requirement keeps is retired (Appendix B). `tools/requirements_check.py` checks the form of each
requirement and the trace from each requirement to its tests.

## Rules

- **One sentence, one intent.** Each statement is one EARS sentence with "shall":

  | Form | Template |
  | --- | --- |
  | Ubiquitous | The Sapling Tree Gen extension shall *response*. |
  | Event | When *trigger*, the Sapling Tree Gen extension shall *response*. |
  | Unwanted behaviour | If *condition*, then the Sapling Tree Gen extension shall *response*. |
  | State | While *state*, the Sapling Tree Gen extension shall *response*. |
  | Option | Where *feature*, the Sapling Tree Gen extension shall *response*. |
  | Complex | The clauses in this order: Where, While, When or If, then the main clause. |

- **Words.** At most 25 words, active voice, no semicolons, Simplified Technical English. Values have units. These
  words are not used: fast, quickly, slow, appropriate, adequate, sufficient, user-friendly, easy, etc, and/or, as
  needed, as appropriate, if possible, usually, normally, minimal, maximum possible, state of the art, robust,
  flexible, efficient, may, should, could, some, several, many. Names of the user interface are in *italics* and do
  not count as these words (for example *Fast Preview*).
- **Fields.** Each requirement has an ID (`SWR-nnnn`, never used again after a requirement is removed), a title, the
  statement, the rationale, the verification method (test, analysis, inspection or review) and the verification
  criteria.
- **Trace.** A test names each requirement it verifies (`SWR_0001` in its name or docstring). A requirement verified
  by analysis, inspection or review names its evidence in its criteria.

## Installation and compatibility

### SWR-0001 Blender version
- **Statement:** The Sapling Tree Gen extension shall install and run in Blender 5.2 LTS and Blender 5.3.
- **Rationale:** 5.2 LTS is the current long-term release, and 5.3 is the next release. Version 0.3.7 stays for
  Blender 4.4 and 4.5.
- **Method:** test
- **Criteria:** The full gate (`tools/check.py`) passes in Blender 5.2 and in Blender 5.3.

### SWR-0002 Platform package
- **Statement:** The Sapling Tree Gen extension shall build into a package that `blender --command extension validate` accepts.
- **Rationale:** The Extensions Platform accepts only a valid package.
- **Method:** test
- **Criteria:** `tools/check.py --fast` builds the zip and validates it with no error.

### SWR-0003 Self-contained package
- **Statement:** The Sapling Tree Gen extension shall run with no network access and no Python module outside its package and Blender.
- **Rationale:** Platform rule: an extension is self-contained and needs no special permission.
- **Method:** inspection
- **Criteria:** The manifest has no `[permissions]` and no `wheels`. The architecture test finds no import outside
  the package, the standard library, NumPy and `bpy`.

### SWR-0004 User files
- **Statement:** The Sapling Tree Gen extension shall write files only into the folder that `bpy.utils.extension_path_user` gives.
- **Rationale:** Platform rule: a system installation is read-only, and an upgrade removes the package folder.
- **Method:** test
- **Criteria:** The architecture test finds no file write outside that folder. A saved preset is in that folder.

### SWR-0005 Disable and enable
- **Statement:** When the user disables the extension, the Sapling Tree Gen extension shall remove all its classes and menu entries.
- **Rationale:** A disabled extension leaves nothing in the interface.
- **Method:** test
- **Criteria:** After disable and enable, each menu has one entry of the extension.

### SWR-0006 Failed registration
- **Statement:** If registration fails, then the Sapling Tree Gen extension shall unregister the classes that it registered before the failure.
- **Rationale:** A failed start leaves Blender clean.
- **Method:** test
- **Criteria:** After a forced failure, none of the extension's classes is registered.

## Adding a tree

### SWR-0010 Add Tree
- **Statement:** When the user runs *Sapling: Add Tree*, the Sapling Tree Gen extension shall create a tree from the current settings.
- **Rationale:** This is the main function of the extension.
- **Method:** test
- **Criteria:** The operator returns FINISHED and the scene has the tree object with its curve.

### SWR-0011 Menu entry
- **Statement:** The Sapling Tree Gen extension shall show *Sapling: Add Tree* in the *Add > Curve* menu of the 3D Viewport.
- **Rationale:** The user finds new curve objects in that menu.
- **Method:** test
- **Criteria:** The menu draws the operator.

### SWR-0012 Place of a new tree
- **Statement:** When the extension adds a tree, the Sapling Tree Gen extension shall put it at the 3D cursor in the active collection, selected and active.
- **Rationale:** Blender's add operators place new objects so.
- **Method:** test
- **Criteria:** The tree's location equals the cursor location. The tree is in the active collection, selected and
  active.

### SWR-0013 Repeatable tree
- **Statement:** When the settings and the *Random Seed* are equal, the Sapling Tree Gen extension shall generate the same tree.
- **Rationale:** The user can make a tree again, and the tests compare trees.
- **Method:** test
- **Criteria:** The 38 golden trees match their recorded data exactly.

### SWR-0014 Settings on the page
- **Statement:** The Sapling Tree Gen extension shall offer the settings of Appendix A, with their pages, defaults and ranges, in the *Add Tree* panel.
- **Rationale:** Appendix A is the list of the settings that the user can change.
- **Method:** test
- **Criteria:** The requirement check compares Appendix A with `source/ui/properties.py` and `source/ui/pages.py`.

### SWR-0015 Update on change
- **Statement:** When the user changes a setting of the *Add Tree* panel, the Sapling Tree Gen extension shall generate the tree again with the new value.
- **Rationale:** The user sees the effect of each change.
- **Method:** test
- **Criteria:** A changed setting gives the tree of that setting.

### SWR-0016 Settings within range
- **Statement:** When every setting is within its range of Appendix A, the Sapling Tree Gen extension shall generate a tree without an error.
- **Rationale:** A setting that the panel allows must not break the tree.
- **Method:** test
- **Criteria:** 100 trees with random settings within their ranges generate (the fuzz test).

## Editing and duplicating

### SWR-0020 Stored settings
- **Statement:** The Sapling Tree Gen extension shall store the settings of each tree on the tree object as versioned JSON.
- **Rationale:** Edit Sapling Tree makes the tree again from these settings.
- **Method:** test
- **Criteria:** The tree object has the stored settings with a version number, and they load back unchanged.

### SWR-0021 Edit Sapling Tree
- **Statement:** When the user runs *Edit Sapling Tree* on a tree, the Sapling Tree Gen extension shall generate the tree again from its stored settings.
- **Rationale:** The user changes a tree after it was added.
- **Method:** test
- **Criteria:** The edited tree equals a new tree from the same settings.

### SWR-0022 Edit keeps the tree's place
- **Statement:** When the extension edits a tree, the Sapling Tree Gen extension shall keep its transform, parent and collections.
- **Rationale:** An edit changes the shape, not where the tree is in the scene.
- **Method:** test
- **Criteria:** Object, bone and vertex parents, the transform and the collections are equal before and after.

### SWR-0023 Edit keeps the user's children
- **Statement:** When the extension edits a tree, the Sapling Tree Gen extension shall attach the user's child objects to the same part of the new tree.
- **Rationale:** The user's objects stay with the tree.
- **Method:** test
- **Criteria:** A child object of a branch is a child of that branch after the edit.

### SWR-0024 Lost children
- **Statement:** If an edit removes the part that a child object follows, then the Sapling Tree Gen extension shall name the object in a warning.
- **Rationale:** The user knows which objects lost their place.
- **Method:** test
- **Criteria:** The warning names each such object.

### SWR-0025 Failed edit
- **Statement:** If an edit fails, then the Sapling Tree Gen extension shall keep the old tree unchanged.
- **Rationale:** A failed edit does not destroy work.
- **Method:** test
- **Criteria:** After a failed edit, the old tree and its parts are in the scene, unchanged.

### SWR-0026 Edit menu entries
- **Statement:** The Sapling Tree Gen extension shall show *Edit Sapling Tree* in the *Sapling* tab of the sidebar and in the *Object* menu.
- **Rationale:** The user finds the edit where the tree is selected.
- **Method:** test
- **Criteria:** The panel and the menu draw the operator.

### SWR-0027 Duplicate with Blender
- **Statement:** When the user duplicates a tree with *Duplicate* or *Duplicate Linked*, the Sapling Tree Gen extension shall give the copy all parts of the tree.
- **Rationale:** Blender copies only the selected objects. The hidden parts, the leaves and the blossoms are also part of a tree.
- **Method:** test
- **Criteria:** The copy has its own curves, wind and rig parts, leaves and blossoms, at the copy's place.

### SWR-0028 Duplicate Sapling Tree
- **Statement:** When the user runs *Duplicate Sapling Tree* on any part of a tree, the Sapling Tree Gen extension shall copy the whole tree.
- **Rationale:** The user can copy a tree from the part that is selected.
- **Method:** test
- **Criteria:** The copy has all parts of the tree.

### SWR-0029 Independent copies
- **Statement:** When the user edits a copied tree, the Sapling Tree Gen extension shall change only that copy.
- **Rationale:** A copy is a tree of its own.
- **Method:** test
- **Criteria:** After the edit of the copy, the original is unchanged.

### SWR-0030 Unreadable stored settings
- **Statement:** If the stored settings of a tree cannot be read, then the Sapling Tree Gen extension shall show the reason in the *Sapling* panel.
- **Rationale:** The panel does not fail at each redraw, and the user knows why the edit is not available.
- **Method:** test
- **Criteria:** The panel draws the reason and raises no error.

### SWR-0031 Edit on another object
- **Statement:** If *Edit Sapling Tree* runs on an object that is not a tree, then the Sapling Tree Gen extension shall cancel with a message.
- **Rationale:** Only a tree has the stored settings.
- **Method:** test
- **Criteria:** The operator cancels with a message and the object is unchanged.

## Presets

### SWR-0040 Built-in presets
- **Statement:** The Sapling Tree Gen extension shall offer the built-in presets of the `presets` folder in the *Geometry* page.
- **Rationale:** A preset gives a species without manual settings.
- **Method:** test
- **Criteria:** Each preset file shows in the list, and each one generates a tree (the smoke test).

### SWR-0041 Preset sets every setting
- **Statement:** The Sapling Tree Gen extension shall set every generation setting when the user chooses a built-in preset.
- **Rationale:** A setting of the preset before must not stay in the new tree.
- **Method:** test
- **Criteria:** Each built-in preset file has every generation setting. Two presets loaded in a sequence give the
  same tree as the second one alone.

### SWR-0042 Preset applies at once
- **Statement:** When the user chooses a preset, the Sapling Tree Gen extension shall generate the tree of that preset.
- **Rationale:** The user sees the preset at once.
- **Method:** test
- **Criteria:** The tree after the choice is the preset's tree.

### SWR-0043 Save Preset
- **Statement:** When the user runs *Save Preset*, the Sapling Tree Gen extension shall save the current settings as a UTF-8 file in the user folder.
- **Rationale:** The user keeps settings for later trees.
- **Method:** test
- **Criteria:** The file is in the folder of SWR-0004 and loads back to the same settings.

### SWR-0044 Preset names
- **Statement:** If a preset name contains a path or is a built-in name, then the Sapling Tree Gen extension shall refuse the save with the reason.
- **Rationale:** A name must not write outside the user folder or hide a built-in preset.
- **Method:** test
- **Criteria:** Names with path separators, "..", and built-in names are refused with a message.

### SWR-0045 Existing preset file
- **Statement:** If a user preset with the same name exists, then the Sapling Tree Gen extension shall save only with *Overwrite* on.
- **Rationale:** A save does not replace a preset by mistake.
- **Method:** test
- **Criteria:** Without *Overwrite* the save is refused and the file is unchanged.

### SWR-0046 Bad user preset files
- **Statement:** If a user preset file cannot be read, then the Sapling Tree Gen extension shall list the file with the reason.
- **Rationale:** The user can repair or remove the file.
- **Method:** test
- **Criteria:** Unreadable, malformed and badly named files are listed with their reasons.

### SWR-0047 Missing settings in old presets
- **Statement:** If a preset or a stored tree lacks settings, then the Sapling Tree Gen extension shall use their defaults and name them in a warning.
- **Rationale:** Presets and trees of older versions still load, and the user knows what was filled in.
- **Method:** test
- **Criteria:** A preset without some settings loads, and the warning names each missing setting.

### SWR-0048 Old setting names
- **Statement:** When a preset uses the setting names of version 0.3.x, the Sapling Tree Gen extension shall read them as the current settings.
- **Rationale:** Presets saved with 0.3.x still load.
- **Method:** test
- **Criteria:** Each old name of `OldSettingNames` loads into its current setting.

## Tree shape

### SWR-0060 Branch levels
- **Statement:** The Sapling Tree Gen extension shall grow trees with 1 to 6 branch levels.
- **Rationale:** *Levels* sets how many times branches grow from branches.
- **Method:** test
- **Criteria:** Trees with each level count from 1 to 6 generate, and level 6 has stems.

### SWR-0061 Clump of trunks
- **Statement:** Where *Trunks* is more than 1, the Sapling Tree Gen extension shall grow the further trunks on a disc, at least 2.5 trunk radii apart.
- **Rationale:** Clumps such as bamboo grow several stems from one root.
- **Method:** test
- **Criteria:** Each pair of trunk bases is at least 2.5 trunk radii apart.

### SWR-0062 Helix stems
- **Statement:** Where *Helix* is on for a level, the Sapling Tree Gen extension shall grow the stems of that level as helixes.
- **Rationale:** Some species grow spiral stems (tree-gen's negative curve variation).
- **Method:** test
- **Criteria:** Each segment of a helix stem is half a turn around the stem's start direction.

### SWR-0063 Helix angle
- **Statement:** If a helix level has *Curvature Variation* of 90 degrees or more, then the Sapling Tree Gen extension shall refuse it and name the level.
- **Rationale:** A helix angle of 90 degrees or more has no helix.
- **Method:** test
- **Criteria:** The operator cancels with a message that names the level, and it makes no objects.

### SWR-0064 Pruning
- **Statement:** Where *Prune* is on, the Sapling Tree Gen extension shall cut the branches back to the pruning envelope.
- **Rationale:** The envelope gives the crown its outline.
- **Method:** test
- **Criteria:** With *Prune Ratio* 1, no branch point is outside the envelope.

### SWR-0065 Short pruned stems
- **Statement:** Where *Prune Ratio* is 1, the Sapling Tree Gen extension shall remove each stem that keeps less than 15 % of its length.
- **Rationale:** Short stubs are invisible, but their leaves float beside the branches.
- **Method:** test
- **Criteria:** No stem shorter than 15 % of its unpruned length remains.

### SWR-0066 Hidden envelope
- **Statement:** The Sapling Tree Gen extension shall hide the pruning envelope after it generates the tree.
- **Rationale:** The envelope curves are helpers, not part of the tree.
- **Method:** test
- **Criteria:** The envelope objects are hidden in the viewport and in renders.

### SWR-0067 Enumerated settings
- **Statement:** If a setting has an unknown *Handle Type* or *Branching Mode*, then the Sapling Tree Gen extension shall refuse the tree and name the value.
- **Rationale:** An unknown value must not become another value without a message.
- **Method:** test
- **Criteria:** The operator cancels and the message names the value.

### SWR-0068 Wind shape
- **Statement:** Where *Wind Shear* or *Wind Bend* is more than 0, the Sapling Tree Gen extension shall shape the crown toward the *Wind Direction*.
- **Rationale:** Trees on windy coasts and ridges grow a one-sided crown.
- **Method:** test
- **Criteria:** *Wind Shear* moves the crown downwind. *Wind Bend* turns the branches downwind. A direction with both at 0 changes nothing.

### SWR-0069 Branch Base
- **Statement:** Where a level's *Branch Base* is more than 0, the Sapling Tree Gen extension shall grow no sprouts on that share of its stems.
- **Rationale:** Some species carry their foliage only at the outer part of the limbs.
- **Method:** test
- **Criteria:** No sprout of a level with *Branch Base* b lies on the first share b of its stem. Value 0 changes nothing.

### SWR-0070 No room for the trunks
- **Statement:** If the further trunks do not fit on the disc, then the Sapling Tree Gen extension shall refuse the tree and name the reason.
- **Rationale:** A clump with overlapping trunks is wrong.
- **Method:** test
- **Criteria:** The operator cancels with the reason and makes no objects.

### SWR-0071 Bend Variation
- **Statement:** Where a level's *Bend Variation* is more than 0, the Sapling Tree Gen extension shall turn its segments sideways by random angles up to it.
- **Rationale:** Branches of real trees wander sideways (tree-gen's bend variation).
- **Method:** test
- **Criteria:** A segment turns by at most the value divided by the level's segments. The first segment and a segment that splits do not turn. Value 0 changes nothing.

### SWR-0072 Count Above Base
- **Statement:** Where *Count Above Base* is on, the Sapling Tree Gen extension shall count each level's branches on the stem part above its bare base.
- **Rationale:** tree-gen counts branches so; the palm then gets its fronds in the crown.
- **Method:** test
- **Criteria:** The palm preset gets 25 fronds in the crown. The leaf count does not change.

### SWR-0073 Trunks Face Out
- **Statement:** Where *Trunks Face Out* is on, the Sapling Tree Gen extension shall curve each further trunk of a clump away from the clump's centre.
- **Rationale:** Bamboo culms lean out from the clump.
- **Method:** test
- **Criteria:** Each further trunk bends away from the centre. Off: the trunks bend in random directions.

### SWR-0074 Bevel
- **Statement:** Where *Bevel* is on, the Sapling Tree Gen extension shall sweep the bark around the branches with the radius settings.
- **Rationale:** The branches get thickness, and the sweep stays live for later edits.
- **Method:** test
- **Criteria:** The sweep has the vertex count of Blender's own bevel of the same curve. The Bevel inputs stay live. Apply gives the mesh.

### SWR-0075 Base Splits
- **Statement:** Where *Base Splits* is more than 0, the Sapling Tree Gen extension shall grow one first-level branch per height among the trunk's pieces.
- **Rationale:** A split trunk carries the branches of one trunk, not one set per piece.
- **Method:** test
- **Criteria:** *White Birch* with two base splits grows the first-level branch count of one trunk.

## Leaves and blossoms

### SWR-0080 Leaves
- **Statement:** Where *Show Leaves* is on, the Sapling Tree Gen extension shall grow leaves of the chosen *Leaf Shape* on the branches of the last level.
- **Rationale:** Leaves complete the tree.
- **Method:** test
- **Criteria:** The leaves object has *Leaves* leaves per branch at most, of the chosen shape.

### SWR-0081 Leaf object
- **Statement:** Where the *Leaf Shape* uses instances, the Sapling Tree Gen extension shall instance the *Leaf Object* at each leaf.
- **Rationale:** The user can use a modelled leaf.
- **Method:** test
- **Criteria:** Each leaf position has an instance of the object, turned by the leaf's rotation.

### SWR-0082 Missing leaf object
- **Statement:** If instanced leaves have no *Leaf Object*, then the Sapling Tree Gen extension shall refuse the tree before it makes objects.
- **Rationale:** A late failure leaves parts behind.
- **Method:** test
- **Criteria:** The operator cancels with a message and the scene is unchanged.

### SWR-0083 Palmate fans
- **Statement:** Where *Leaves* is negative, the Sapling Tree Gen extension shall grow a fan of −*Leaves* leaves at each branch tip.
- **Rationale:** Palms grow their leaves as fans.
- **Method:** test
- **Criteria:** Each branch tip has the given number of leaves in a fan.

### SWR-0084 Blossoms
- **Statement:** Where *Blossom Rate* is more than 0, the Sapling Tree Gen extension shall grow that share of the leaf positions as blossoms.
- **Rationale:** Flowering species show blossoms.
- **Method:** test
- **Criteria:** The blossoms object holds the given share of the positions (within one blossom). A higher rate keeps
  every blossom of a lower rate.

### SWR-0085 Leaf and bark materials
- **Statement:** Where *Leaf Material* is on, the Sapling Tree Gen extension shall give mesh leaves the *Sapling Leaf* material, blossoms *Sapling Blossom* and branches *Sapling Bark*.
- **Rationale:** The materials let light through the leaves as through real leaves.
- **Method:** test
- **Criteria:** The objects have these materials. *Sapling Leaf* is a Principled BSDF with Thin Wall and Subsurface
  Weight 1.0.

### SWR-0086 Leaf Face Up
- **Statement:** Where *Leaf Face Up* is more than 0, the Sapling Tree Gen extension shall turn each leaf's face toward the sky by that share.
- **Rationale:** Conifers and shrubs carry flat foliage pads.
- **Method:** test
- **Criteria:** Value 1 lays every leaf flat, 0.5 turns each one halfway. *Leaf Face Up Variation* tilts each leaf within its range.

### SWR-0087 Leaves Above Base
- **Statement:** Where *Leaves Above Base* is on, the Sapling Tree Gen extension shall grow no leaves on the bare base of their stems.
- **Rationale:** Leaves grow where branches grow.
- **Method:** test
- **Criteria:** No leaf lies on the bare base of its stem.

### SWR-0088 Fan Angles
- **Statement:** Where *Fan Angles* is on, the Sapling Tree Gen extension shall tilt the leaves of each palmate fan by *Leaf Down Angle* into a cup.
- **Rationale:** Palm fans are cupped, not flat (tree-gen's fans).
- **Method:** test
- **Criteria:** The fan leaves tilt by the down angle. Off: the fans are flat and even.

## Armature and baked mesh

### SWR-0100 Armature rig
- **Statement:** Where *Armature Rig* is on, the Sapling Tree Gen extension shall make an armature with one bone per *Joint Length* segments within the *Joint Levels*.
- **Rationale:** A rig lets the user pose and export the tree.
- **Method:** test
- **Criteria:** The bone count equals the count from the joint layout. Deeper levels follow the nearest bone below
  them.

### SWR-0101 Bones follow the branches
- **Statement:** Where *Armature Rig* is on, the Sapling Tree Gen extension shall move the bark, leaves and blossoms with their bones.
- **Rationale:** The rig moves the whole tree.
- **Method:** test
- **Criteria:** A rotated bone moves its branch, leaves and blossoms by the same transform.

### SWR-0102 Bone count limits
- **Statement:** If a rig needs more than 40,000 bones, then the Sapling Tree Gen extension shall refuse it and name the settings that lower it.
- **Rationale:** The build time grows with the square of the bone count: 79,648 bones took 415 s.
- **Method:** test
- **Criteria:** The operator cancels with the count and the settings in the message.

### SWR-0103 Bone count warning
- **Statement:** If a rig needs more than 10,000 bones, then the Sapling Tree Gen extension shall warn with the count and the estimated time.
- **Rationale:** The user can stop a long build.
- **Method:** test
- **Criteria:** The warning has the count and the time.

### SWR-0104 Make Mesh
- **Statement:** Where *Make Mesh* is on, the Sapling Tree Gen extension shall bake the branches into a mesh weighted to the rig's bones.
- **Rationale:** Game engines and other programs import a skinned mesh.
- **Method:** test
- **Criteria:** The tree object holds a mesh with one vertex group per bone, and the weights of each vertex sum to 1.

### SWR-0105 Hidden bones
- **Statement:** The Sapling Tree Gen extension shall hide the bones after it generates the rig, in the bone collection *Sapling Bones*.
- **Rationale:** The bones cover the tree in the viewport.
- **Method:** test
- **Criteria:** The bone collection exists and is hidden.

### SWR-0106 Tree hierarchy
- **Statement:** The Sapling Tree Gen extension shall make the tree curve the top object and parent every other part of the tree to it.
- **Rationale:** The whole tree moves when the user moves the tree.
- **Method:** test
- **Criteria:** Every part of the tree has the tree curve as its top parent.

### SWR-0107 Export
- **Statement:** Where *Make Mesh* and *Armature Rig* are on, the Sapling Tree Gen extension shall make bark that an FBX export writes as a skinned mesh.
- **Rationale:** Game engines import the tree with its rig.
- **Method:** test
- **Criteria:** An FBX or glTF export holds the bark mesh, the armature and the vertex weights.

## Wind

### SWR-0120 Wind
- **Statement:** Where *Wind* is on, the Sapling Tree Gen extension shall sway the branches with the *Wind Strength*, *Gust Strength* and *Gust Frequency*.
- **Rationale:** An animated tree for renders and games.
- **Method:** test
- **Criteria:** The branches move between frames. Wind Strength 0 gives no movement.

### SWR-0121 Wind on the rig
- **Statement:** Where *Wind* and *Armature Rig* are on, the Sapling Tree Gen extension shall animate the bones.
- **Rationale:** An exported rig carries the wind animation.
- **Method:** test
- **Criteria:** The bones have F-curves, and the rig's motion equals the node wind's motion within 1e-5.

### SWR-0122 Leaf Flutter
- **Statement:** Where *Wind* and *Leaf Flutter* are on, the Sapling Tree Gen extension shall turn each mesh leaf about its sprout with the flutter settings.
- **Rationale:** Leaves move on their own in wind.
- **Method:** test
- **Criteria:** Each leaf turns about its sprout point between frames.

### SWR-0123 Loop
- **Statement:** Where *Loop Frames* is more than 0, the Sapling Tree Gen extension shall repeat the wind motion after that number of frames.
- **Rationale:** A looped animation plays without a jump.
- **Method:** test
- **Criteria:** The tree at frame 1 and at frame 1 + *Loop Frames* is the same within 1e-5.

### SWR-0124 Fast Preview
- **Statement:** While *Fast Preview* is on, the Sapling Tree Gen extension shall draw the branches as curves and a rigged tree as bounds and bones.
- **Rationale:** The user plays the animation at a higher frame rate while working.
- **Method:** test
- **Criteria:** The display settings are as stated, and they return when *Fast Preview* is off.

## Failure behaviour

### SWR-0140 Failed Add
- **Statement:** If generation fails, then the Sapling Tree Gen extension shall show the reason and leave the scene as it was before.
- **Rationale:** A failure does not leave parts of a tree behind.
- **Method:** test
- **Criteria:** After a forced failure, the scene has the same objects and data as before, and the user's leaf
  object has its old parent and place.

### SWR-0141 Script call
- **Statement:** When a script calls `curve.tree_add` with settings, the Sapling Tree Gen extension shall create the tree as the panel does.
- **Rationale:** Scripts and pipelines make trees.
- **Method:** test
- **Criteria:** A script call with a preset's settings gives the preset's tree. Panel-only keywords do not stop it.

### SWR-0142 Own random numbers
- **Statement:** The Sapling Tree Gen extension shall use its own random number generator and leave Python's `random` module unchanged.
- **Rationale:** Other add-ons and scripts use the shared module.
- **Method:** test
- **Criteria:** The state of `random` is equal before and after a tree is generated.

### SWR-0143 No active collection
- **Statement:** If no collection is active, then the Sapling Tree Gen extension shall cancel *Sapling: Add Tree* with a message.
- **Rationale:** A new object must go into a collection.
- **Method:** test
- **Criteria:** The operator cancels with a message and makes no objects.

### SWR-0144 No orphan data
- **Statement:** The Sapling Tree Gen extension shall leave no orphan data blocks after it removes or generates a tree again.
- **Rationale:** Orphan meshes, curves and node groups fill the file.
- **Method:** test
- **Criteria:** The data block counts are equal before and after a remove and after a regenerate.

### SWR-0145 No other objects changed
- **Statement:** The Sapling Tree Gen extension shall change no object other than the tree that it builds or edits.
- **Rationale:** Other objects of the scene are the user's work.
- **Method:** test
- **Criteria:** Other objects, including another selected armature, keep their data, mode and selection.

## Performance

### SWR-0160 Generation time
- **Statement:** The Sapling Tree Gen extension shall generate each built-in preset with leaves in at most 60 % of the time of version 0.3.7.
- **Rationale:** The rewrite measured 44-82 % of the 0.3.7 times (README table). OPEN: is this the right measure,
  or an absolute time per preset on a reference machine?
- **Method:** analysis
- **Criteria:** `tools/bench.py` on the reference machine, 3 runs, median per preset, against the README's 0.3.7
  values.

### SWR-0161 Animation frame time
- **Statement:** While *Wind* plays on *Cambridge Oak* with leaves and flutter, the Sapling Tree Gen extension shall evaluate each frame in at most 0.05 s.
- **Rationale:** Measured 0.02-0.03 s per frame (CHANGELOG 1.0.0). OPEN: the limit and the reference machine.
- **Method:** analysis
- **Criteria:** Headless playback on the reference machine, frames 1-48, the slowest frame.

### SWR-0162 Leaf build scaling
- **Statement:** When the leaf count doubles, the Sapling Tree Gen extension shall take less than 2.6 times as long to build the leaves.
- **Rationale:** The build time must grow linearly with the leaves (measured in `tests/test_performance.py`).
- **Method:** test
- **Criteria:** The leaf stages at 40 and 80 leaves per branch, the shortest of 2 runs: the ratio is less than 2.6.

### SWR-0163 Build scaling
- **Statement:** The Sapling Tree Gen extension shall build trees in a time that grows with an exponent of less than 1.3 of the stem count.
- **Rationale:** A quadratic build made big trees take minutes in 0.3.7.
- **Method:** test
- **Criteria:** The fitted exponent of build time against stem count is less than 1.3 (1 is linear).

### SWR-0164 Model time
- **Statement:** The Sapling Tree Gen extension shall grow the model of *Quaking Aspen* with more than 1,000 stems in less than 0.1 s.
- **Rationale:** The model is the part of the build that is all Python.
- **Method:** test
- **Criteria:** The shortest model time of the test runs is less than 0.1 s, with more than 1,000 stems.

## Open questions (unwanted behaviour not yet stated)

1. A *Leaf Object* that the user deletes after the tree is made: what does Edit do? (Today: not known.)
2. The user stops a long generation (Esc): is the scene left as before? (Today: not known; Blender may not allow it
   during the operator.)
3. An edit of a tree whose stored settings are from a newer version of the extension: refuse, or load with a
   warning?
4. Settings outside their range from a script (the property ranges stop the panel, not every script path).

## Appendix A - settings

The settings that the user can change in the *Add Tree* panel (SWR-0014), from `source/ui/properties.py` and
`source/ui/pages.py`. An empty range means no limit. The other properties are internal: the page choice
(`chooseSet`), `do_update`, the preset name (`presetName`) and the 13 old names (SWR-0048).

| Page | Setting | Property | Default | Range |
| --- | --- | --- | --- | --- |
| Geometry | Bevel | `bevel` | False |  |
| Geometry | Bevel Resolution | `bevelRes` | 0 | 0 to 32 |
| Geometry | Curve Resolution | `resU` | 4 | 1 to - |
| Geometry | Handle Type | `handleType` | 0 |  |
| Geometry | Shape | `shape` | 7 |  |
| Geometry | Secondary Branches Shape | `shapeS` | 4 |  |
| Geometry | Custom Shape | `customShape` | [0.5, 1.0, 0.3, 0.5] | 0.01 to 1 |
| Geometry | Branch Distribution | `branchDist` | 1.0 | 0.1 to - |
| Geometry | Branch Rings | `nrings` | 0 | 0 to - |
| Geometry | Random Seed | `seed` | 0 |  |
| Geometry | Scale | `scale` | 13.0 | 0.0 to - |
| Geometry | Scale Variation | `scaleV` | 3.0 |  |
| Branch Radius | Ratio | `ratio` | 0.015 | 0.0 to - |
| Branch Radius | Radius Scale | `scale0` | 1.0 | 0.0 to - |
| Branch Radius | Radius Scale Variation | `scaleV0` | 0.2 | 0.0 to 1.0 |
| Branch Radius | Branch Radius Ratio | `ratioPower` | 1.2 | 0.0 to - |
| Branch Radius | Minimum Radius | `minRadius` | 0.0 | 0.0 to - |
| Branch Radius | Close Tip | `closeTip` | False |  |
| Branch Radius | Root Flare | `rootFlare` | 1.0 | 1.0 to - |
| Branch Radius | Auto Taper | `autoTaper` | True |  |
| Branch Radius | Taper | `taper` | [1, 1, 1, 1] | 0.0 to 1.0 |
| Branch Radius | Tweak Radius | `radiusTweak` | [1, 1, 1, 1] | 0.0 to 1.0 |
| Branch Splitting | Levels | `levels` | 3 | 1 to 6 |
| Branch Splitting | Trunks | `trunks` | 1 | 1 to - |
| Branch Splitting | Trunks Face Out | `trunksFaceOut` | False |  |
| Branch Splitting | Base Splits | `baseSplits` | 0 | 0 to - |
| Branch Splitting | Trunk Height | `baseSize` | 0.4 | 0.0 to 1.0 |
| Branch Splitting | Branch Base | `branchBase` | [0, 0, 0, 0] | 0.0 to 0.95 |
| Branch Splitting | Secondary Base Size | `baseSize_s` | 0.25 | 0.0 to 1.0 |
| Branch Splitting | Split Height | `splitHeight` | 0.2 | 0.0 to 1.0 |
| Branch Splitting | Split Bias | `splitBias` | 0.0 |  |
| Branch Splitting | Split Relative to Length | `splitByLen` | False |  |
| Branch Splitting | Count Above Base | `countAboveBase` | False |  |
| Branch Splitting | Branches | `branches` | [50, 30, 10, 10] | 0 to - |
| Branch Splitting | Segment Splits | `segSplits` | [0, 0, 0, 0] | 0 to - |
| Branch Splitting | Split Angle | `splitAngle` | [0, 0, 0, 0] |  |
| Branch Splitting | Split Angle Variation | `splitAngleV` | [0, 0, 0, 0] |  |
| Branch Splitting | Rotate Angle | `rotate` | [137.5, 137.5, 137.5, 137.5] |  |
| Branch Splitting | Rotate Angle Variation | `rotateV` | [0, 0, 0, 0] |  |
| Branch Splitting | Outward Attraction | `attractOut` | [0, 0, 0, 0] | 0.0 to 1.0 |
| Branch Growth | Wind Direction | `windDir` | 0.0 | 0.0 to 360.0 |
| Pruning | Wind Shear | `windShear` | 0.0 | 0.0 to 0.9 |
| Branch Growth | Wind Bend | `windBend` | [0, 0, 0, 0] | 0.0 to 1.0 |
| Branch Splitting | Branching Mode | `rMode` | BranchingMode.ROTATE |  |
| Branch Splitting | Curve Resolution | `curveRes` | [3, 5, 3, 1] | 1 to - |
| Branch Growth | Taper Crown | `taperCrown` | 0 | 0.0 to - |
| Branch Growth | Length | `length` | [1, 0.3, 0.6, 0.45] | 1e-06 to - |
| Branch Growth | Length Variation | `lengthV` | [0, 0, 0, 0] | 0.0 to 1.0 |
| Branch Growth | Down Angle | `downAngle` | [90, 60, 45, 45] |  |
| Branch Growth | Down Angle Variation | `downAngleV` | [0, -50, 10, 10] |  |
| Branch Growth | Curvature | `curve` | [0, -40, -40, 0] |  |
| Branch Growth | Curvature Variation | `curveV` | [20, 50, 75, 0] |  |
| Branch Growth | Back Curvature | `curveBack` | [0, 0, 0, 0] |  |
| Branch Growth | Bend Variation | `bendV` | [0, 0, 0, 0] | 0 to 360 |
| Branch Growth | Helix | `helix` | [False, False, False, False] |  |
| Branch Growth | Vertical Attraction | `attractUp` | [0, 0, 0, 0] |  |
| Branch Growth | Use Old Down Angle Variation | `useOldDownAngle` | False |  |
| Branch Growth | Use Parent Angle | `useParentAngle` | True |  |
| Pruning | Prune | `prune` | False |  |
| Pruning | Prune Ratio | `pruneRatio` | 1.0 | 0.0 to 1.0 |
| Pruning | Prune Width | `pruneWidth` | 0.4 | 0.0 to - |
| Pruning | Prune Base Height | `pruneBase` | 0.3 | 0.0 to 1.0 |
| Pruning | Prune Width Peak | `pruneWidthPeak` | 0.6 | 0.0 to - |
| Pruning | Prune Power High | `prunePowerHigh` | 0.5 |  |
| Pruning | Prune Power Low | `prunePowerLow` | 0.001 |  |
| Leaves | Show Leaves | `showLeaves` | False |  |
| Leaves | Leaf Shape | `leafShape` | LeafShape.HEX |  |
| Leaves | Leaf Object | `leafDupliObj` |  |  |
| Leaves | Leaves | `leaves` | 25 |  |
| Leaves | Leaf Distribution | `leafDist` | 6 |  |
| Leaves | Leaf Down Angle | `leafDownAngle` | 45 |  |
| Leaves | Leaf Down Angle Variation | `leafDownAngleV` | 10 |  |
| Leaves | Leaf Rotate Angle | `leafRotate` | 137.5 |  |
| Leaves | Leaf Rotate Angle Variation | `leafRotateV` | 0.0 |  |
| Leaves | Leaf Scale | `leafScale` | 0.17 | 0.0 to - |
| Leaves | Leaf Scale X | `leafScaleX` | 1.0 | 0.0 to - |
| Leaves | Leaf Scale Taper | `leafScaleT` | 0.0 | -1.0 to 1.0 |
| Leaves | Leaf Scale Variation | `leafScaleV` | 0.0 | 0.0 to 1.0 |
| Leaves | Blossom Rate | `blossomRate` | 0.0 | 0.0 to 1.0 |
| Leaves | Blossom Shape | `blossomShape` | BlossomShape.CHERRY |  |
| Leaves | Blossom Scale | `blossomScale` | 0.1 | 0.0 to - |
| Leaves | Leaf Angle | `leafangle` | 0.0 |  |
| Leaves | Leaf Material | `leafMaterial` | True |  |
| Leaves | Fan Angles | `fanAngles` | False |  |
| Leaves | Leaves Above Base | `leavesAboveBase` | False |  |
| Leaves | Leaf Face Up | `leafUp` | 0.0 | 0.0 to 1.0 |
| Leaves | Leaf Face Up Variation | `leafUpV` | 0.0 | 0.0 to 90.0 |
| Leaves | Horizontal Leaves | `horzLeaves` | True |  |
| Armature | Armature Rig | `useRig` | False |  |
| Armature | Make Mesh | `makeMesh` | False |  |
| Armature | Joint Levels | `jointLevels` | 2 | 0 to - |
| Armature | Joint Length | `jointStep` | [1, 1, 1, 1] | 1 to - |
| Animation | Wind | `windAnim` | False |  |
| Animation | Leaf Flutter | `leafFlutter` | False |  |
| Animation | Fast Preview | `fastPreview` | False |  |
| Animation | Animation Speed | `animationSpeed` | 1 | 0.001 to - |
| Animation | Loop Frames | `loopFrames` | 0 | 0 to - |
| Animation | Wind Strength | `windStrength` | 1.0 |  |
| Animation | Gust Strength | `gustStrength` | 1.0 |  |
| Animation | Gust Frequency | `gustFrequency` | 0.075 |  |
| Animation | Flutter Strength | `flutterStrength` | 1.0 |  |
| Animation | Flutter Speed | `flutterSpeed` | 1.0 |  |
| Animation | Flutter Randomness | `flutterRandomness` | 4.0 |  |
| Geometry | Preset Name | `presetName` |  |  |
| Geometry | Overwrite | `overwrite` | False |  |

106 settings

## Appendix B - retirement review

Each function or setting that no requirement above keeps, or that this review questions. The owner decides each
row: keep (then a requirement is added) or retire (then the code, the setting and the preset files go).

| Item | Kept by | Proposal | Reason (checked in `source/presets` on 2026-11-03) |
| --- | --- | --- | --- |
| *Use Old Down Angle Variation* (`useOldDownAngle`) | - | keep | On in 26 of the 32 presets (every tree-gen port uses it). Needs a requirement. |
| *Use Parent Angle* (`useParentAngle`) | - | keep | Off in *Japanese Maple*. Needs a requirement. |
| *Limit Import* (`limitImport`) | - | retired (owner 2026-11-03) | Loads presets with 2 levels and no leaves, for speed. It made trees with more levels look bare (CHANGELOG). The presets generate in 0.01-1.9 s. No preset sets it. |
| *Horizontal Leaves* (`horzLeaves`) | - | keep? | Off in *Small Pine* and *Weeping Willow*. Overlap with *Leaf Face Up* (on in 6 presets) to check. |
| *Leaf Angle* (`leafangle`) | - | keep? | Used by 5 presets (*Callistemon*, *Japanese Maple*, *Small Maple*, *Small Pine*, *White Birch*). Overlap with *Leaf Face Up* to check. |
| *Handle Type* (`handleType`) | - | keep | Auto handles in *Weeping Willow*. Needs a requirement. |
| *Branch Rings* (`nrings`) | - | keep | 7 rings in *Small Pine*. Needs a requirement. |
| *Custom Shape* (`customShape`) | - | keep | Custom shape in *Japanese Maple*, *Small Pine*, *White Birch*. Needs a requirement. |
| Preset *Quaking Aspen Treegen* | SWR-0040 | review | tree-gen's port of the species of the original *Quaking Aspen*. |
| Presets *Willow* and *Weeping Willow* | SWR-0040 | review | *Weeping Willow* is the original Sapling willow. *Willow* is now tree-gen's weeping willow (CHANGELOG). Two weeping willows. |
| Preset *Sphere Tree* | SWR-0040 | review | A shape test from tree-gen, not a species. |
| Old setting names (13 in `OldSettingNames`) | SWR-0048 | keep? | They load presets saved by 0.3.x. Retire only if 0.3.x presets need not load. |
| `.github/workflows` | - | retire | They cannot run on projects.blender.org. |
| The tree-gen port tools (`tools/port_treegen*.py`, `tools/render_ports*.py`) | - | keep? | Developer tools to port more tree-gen species. Not in the package. |
