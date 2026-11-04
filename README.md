# Sapling Tree Gen

Sapling Tree Gen is a Blender extension that makes parametric trees and shrubs with the Weber–Penn
model. A tree has bark, leaves, blossoms, an armature rig and wind animation. You can change all its
settings after you add it.

![Cambridge Oak, a built-in preset, beside a 1.8 m figure](docs/presets/cambridge_oak.jpg)

The extension started as the Sapling Tree Gen add-on that came with Blender until version 4.1 (see
Credits). Version 1.0.0 has all new code, for Blender 5.2 and later. It keeps the settings and the
presets of the add-on and adds the features below.

## Features

- **29 built-in presets:** broadleaf trees, conifers, palms, bamboo and shrubs. The
  [presets page](docs/presets.md) shows a picture of each one, with its height and generation time.
- **Edit a tree at any time:** *Edit Sapling Tree* opens the settings that made a tree again. The new
  tree keeps the transform, the parent, the collections and the children of the old tree.
- **Duplicate a tree:** Shift+D or Alt+D gives a whole, independent tree, with all its hidden parts.
- **A live tree object:** the tree is a mesh that a Geometry Nodes modifier sweeps from hidden curves.
  *Bevel Depth*, *Bevel Resolution*, *Resolution U* and *Fill Caps* stay live inputs. A click on the
  branches selects the whole tree, and the tree moves as one object.
- **Leaves and blossoms:** leaves as mesh faces or as instances of your own leaf object. Blossoms
  (cherry, orange, magnolia) grow on a part of the leaf positions.
- **Translucent materials:** the leaves and blossoms use the Thin Wall mode of the Principled BSDF, so
  light goes through them. The extension makes each material one time, so your changes to it stay.
- **Wind animation:** with or without an armature. Without bones, Geometry Nodes move the joints of the
  tree. *Leaf Animation* turns each leaf with a Geometry Nodes modifier.
- **Armature rig:** a rig that you can export as a skinned mesh. *Joint Levels* and *Joint Length* set
  the number of bones.
- **Make Mesh:** bakes the branches into a plain mesh, weighted to the bones or moved by the node wind.
- **Growth from tree-gen:** clumps of trunks (bamboo), helix stems, random branch bend, branch counts
  above the bare base of a stem, and palm fans.
- **Pruning:** an envelope of two profile curves shortens the stems that grow out of it.
- **Your own presets:** save your settings as a preset. Your presets stay in the extension's user
  folder, so an update does not remove them.
- **Clear errors:** a setting that cannot make a tree stops the operation with a message that names
  the setting. A failed operation removes all that it made.

## Install

The extension needs Blender 5.2 or later.

1. In Blender, select *Edit > Preferences > Get Extensions*.
2. Search for *Sapling Tree Gen* and click *Install*.

The listing is <https://extensions.blender.org/add-ons/sapling-tree-gen/>. Blender does not update
extensions automatically: click *Check for Updates* in *Get Extensions* to get a new version.

## Use it

- **Add a tree:** select *Add > Curve > Sapling Tree Gen*. The tree appears at the 3D cursor. The
  settings are in the *Adjust Last Operation* panel (F9), on nine pages from *Geometry* to *Animation*.
- **Load a preset:** on the *Geometry* page, select a preset from the list. To save your settings, type a
  name and click *Save Preset*.
- **Edit a tree:** select a part of the tree. Click *Edit Sapling Tree* in the *Sapling* tab of the
  sidebar (N) or in the *Object* menu.
- **Duplicate a tree:** press Shift+D or Alt+D, or click *Duplicate Sapling Tree* in the *Sapling* tab.
- **Show the bones:** after generation, the bone collection *Sapling Bones* hides the bones. To show
  them, click the eye icon of that collection in *Armature Properties > Bone Collections*. *Fast
  Preview* shows the bones and draws the tree as its bounding box.
- **Show the hidden parts:** the branch curves (*tree_curves*) and the pruning envelope are hidden.
  *Object Properties > Visibility* shows them.

A rig with many bones takes a long time to build. Blender needs more time for each new bone when the
rig has more bones. The extension warns above 10,000 bones and refuses more than 40,000.
Lower *Joint Levels*, or increase *Joint Length*, to make a smaller rig. Wind without a rig needs no
bones.

## Performance

The built-in presets generate in 0.01 s to 1.9 s with leaves (Blender 5.2, Windows, one process). The
[presets page](docs/presets.md) gives the time of each preset. The table gives the times of *Cambridge
Oak*, the largest preset, with leaves and *Leaf Animation*, in headless Blender:

| | Build | Seconds per animation frame |
| --- | --- | --- |
| Wind | 0.91 s | 0.02–0.03 |
| Wind, Make Mesh | 1.04 s | 0.01–0.02 |
| Rig with wind | 1.66 s | 0.03–0.04 |
| Rig with wind, Make Mesh | 2.93 s | 0.02 |

## Development

You need Blender 5.2 (it has Python 3.13) and Python 3.13 for the tools. The default Blender is
`C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. The `BLENDER` environment variable
selects a different one.

```
py -3.13 -m venv .venv                                  # one time
.venv/Scripts/python -m pip install -r requirements-dev.txt
git config core.hooksPath tools/hooks                   # one time: the fast checks before each commit
python tools/check.py                 # the gate: lint, format, types, complexity, dead code, requirements, tests
python tools/check.py --fast          # the gate without the Blender tests (the pre-commit hook)
python tools/check.py --all-blenders  # the full gate on each supported Blender (BLENDER_5_3 and so on)
python tools/run_tests.py -k NAME     # some tests only; --record-golden writes new golden files
python tools/render_presets.py        # render the new and changed presets and write docs/presets.md
python tools/render_listing.py        # render the listing's featured picture, gallery and icon into docs/listing/
```

- The tests run in headless Blender. They build the extension zip and install it in a temporary
  profile (`build/test-profile`), so they do not change your own Blender profile.
- The gate fails below 99 % line or 96 % branch coverage. It also fails on a method with a cyclomatic
  complexity above 10 (above 3 in `source/ui/`). Each `type: ignore` gives its reason.
- `docs/requirements.md` holds the requirements. Each requirement has a test class in
  `tests/requirements/` that verifies it. `tools/requirements_check.py` checks the form of each
  requirement and that each one has its test.
- `tests/golden/` holds exact fingerprints of the generated trees. A commit that changes a fingerprint
  must give the reason.
- `tools/render_presets.py` makes the presets page from the presets. `render_presets.py --check` tells
  you when a picture is out of date.

### Layout

- `source/`: the extension package.
  - `model/`: the tree as NumPy arrays, without Blender: growth, branching, pruning, leaves, joints
    and wind.
  - `build/`: the Blender objects: curves, node groups, leaves, materials, armature, wind, baked mesh.
  - `service/`: the operations (add, edit, duplicate, presets) and their rules, without the user
    interface.
  - `ui/`: the operators, the settings, the pages, the panels and the menus. They only call the service.
  - `presets/`: the built-in presets, one file each.
- `tests/`: `requirements/` (one test class per requirement), `unit/` (the internals), `support/`,
  `golden/`.
- `tools/`: the gate, the test runner, the benchmark, the requirement check and the preset renders.
- `docs/`: the requirements, the presets page, the release notes and the listing media.

### Release

1. Set `version` in `source/blender_manifest.toml` and add its section to `CHANGELOG.md`.
2. Run `python tools/check.py --all-blenders`.
3. Build and check the zip:
   `blender -c extension build --source-dir source --output-dir build`, then
   `blender -c extension validate build/sapling_tree_gen-<version>.zip`.
4. Tag the commit `v<version>` and push it to <https://projects.blender.org/extensions/add_curve_sapling>.
5. Upload the zip on the listing page of the Extensions Platform.

## Credits

Andrew Hale (TrumanBlending) and Aaron Buchler wrote the original Sapling Tree Gen add-on. CansecoGPC,
Campbell Barton, Nika Kutsniashvili and many Blender contributors maintained it. Its home is
<https://projects.blender.org/extensions/add_curve_sapling>.

Fifteen presets come from tree-gen (<https://github.com/friggog/tree-gen>) by Charlie Hewitt and
contributors: `acer`, `apple`, `balsam_fir`, `bamboo`, `black_oak`, `black_tupelo`, `cambridge_oak`,
`douglas_fir`, `european_larch`, `fan_palm`, `hill_cherry`, `lombardy_poplar`, `palm`,
`sassafras` and `silver_birch`. The port converts
their Weber–Penn values to the settings of Sapling. These files are GPL-3.0-only, as tree-gen is. The
blossoms are this extension's own geometry.

The extension is GPL-3.0-or-later (see `LICENSE` and `source/blender_manifest.toml`). The pictures of the
presets page are CC0.
