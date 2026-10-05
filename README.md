# Sapling Tree Gen for Blender 5.2 LTS

**What:** A Blender 5.2 LTS extension that makes parametric trees (Weber–Penn model) with leaves,
pruning, an armature rig and wind animation. It is a fork of the official Sapling Tree Gen, which is
no longer maintained.

**Why:** The original extension does not work correctly on Blender 5.x. For example, the wind
animation stops with an error. This fork makes the extension work on Blender 5.2 LTS and corrects
old bugs. It also uses the Thin Wall shading of Blender 5.2 for the leaves. The code is
restructured into classes, with tests, lint and type checks.

**Status:** Working on Blender 5.2.2 LTS. Tree generation, pruning, the armature rig, wind, presets,
tree editing and the leaf material are complete. 242 automated tests pass in headless Blender, with
99.7 % line and 97.7 % branch coverage. The features were also checked by hand in the Blender user
interface.

## Download

The built extension is on the GitHub Releases page:
<https://github.com/meet-brad-ch/add_curve_sapling/releases>. In Blender 5.2, select
*Edit > Preferences > Get Extensions*, then *Install from Disk*, and select the zip.

## How to run

The default Blender is `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe` (5.2.2 LTS).
To use a different Blender, set the `BLENDER` environment variable.

```
py -3.13 -m venv .venv                                  # one time: Python 3.13, the same as Blender 5.2
.venv/Scripts/python -m pip install -r requirements-dev.txt
git config core.hooksPath tools/hooks                   # one time: the fast checks before each commit
python tools/check.py            # all checks: ruff, format, mypy, manifest, tests with line and branch coverage
python tools/check.py --fast     # all checks except the Blender tests (the pre-commit hook runs this)
python tools/run_tests.py        # tests only (-k NAME selects tests, --record-golden writes new golden files)
python tools/port_treegen.py <tree-gen clone> acer ...   # convert tree-gen species to presets
python tools/render_ports.py <tree-gen clone> <out> acer  # render tree-gen's tree next to the preset
blender -c extension build --source-dir source --output-dir build
blender -c extension install-file -r user_default -e build/sapling_tree_gen-0.4.0.zip
```

The tests build the extension zip and install it into a temporary profile in `build/test-profile`
(through `BLENDER_USER_RESOURCES`). The tests do not change your own Blender profile.

Line and branch coverage are measured inside Blender. The test runner adds the `coverage` package
of the `.venv` to the `sys.path` of Blender. This works because both use Python 3.13. The run fails
when either value is less than its minimum in `tools/check.py` (`LINE_COVERAGE_MIN`,
`BRANCH_COVERAGE_MIN`).

To release a version:

1. Set `version` in `source/blender_manifest.toml` and add the version to `CHANGELOG.md`.
2. Commit, then tag the commit `v<version>`, for example `git tag v0.4.0`.
3. Push the tag to GitHub: `git push github v0.4.0`.

The workflow `.github/workflows/build.yml` then downloads Blender 5.2.2 and checks its SHA-256.
It builds the zip with `blender -c extension build` and publishes it as a GitHub Release. The
workflow stops if the tag is not the manifest version.

**Prerequisites:** Blender 5.2 LTS (with Python 3.13), Python 3.10 or later for the tools, and
Python 3.13 for the `.venv`. `requirements-dev.txt` pins ruff, mypy, coverage and the Blender stubs.

## Using it

- **Add a tree:** Select *Add > Curve > Sapling Tree Gen*. The tree appears at the 3D cursor. The
  settings are in the *Adjust Last Operation* panel (F9), on eight pages from Geometry to Animation.
- **Presets:** On the Geometry page, select a preset from the list. The preset applies immediately.
  *Limit Import* (off by default) loads a preset with 2 levels and no leaves. This is faster, but
  trees with more levels look bare. To save your settings, type a name and click *Save Preset*. Your
  presets are in the user folder of the extension (`extensions/.user/<repo>/sapling_tree_gen/presets`).
  Fifteen built-in presets come from tree-gen: *Acer*, *Apple*, *Balsam Fir*, *Black Oak*, *Black
  Tupelo*, *Cambridge Oak*, *Douglas Fir*, *European Larch*, *Hill Cherry*, *Lombardy Poplar*,
  *Quaking Aspen Treegen*, *Sassafras*, *Silver Birch*, *Sphere Tree* and *Willow* (see Credits).
  *Cambridge Oak*, the largest preset, generates in about 1 s.
- **Edit Sapling Tree:** Select a part of a generated tree. Click *Edit Sapling Tree* in the
  *Sapling* tab of the sidebar (N) or in the *Object* menu. The settings that made the tree open
  again. The tree is made again in the same place. It keeps its transform, its parent and its
  collections. Objects that you parented to the tree stay attached.
- **Leaf Material** (Leaves page, on by default): Mesh leaves get the material *Sapling Leaf*. This
  material is a Principled BSDF in the **Thin Wall** mode of Blender 5.2, with thin subsurface
  scattering, so light goes through the leaves. Branches get the material *Sapling Bark*. The
  extension makes each material one time and then uses it again, so your changes to them stay.
- **The tree object:** The tree (*tree*) is a mesh whose *Sapling Tree* modifier sweeps the branches
  from a hidden Curves object, *tree_curves*. *Bevel Depth*, *Bevel Resolution*, *Resolution U* and
  *Fill Caps* are live inputs of that modifier. To edit the splines, show *tree_curves* in *Object
  Properties > Visibility*. A click on the branches selects the tree. When you move the tree, all
  parts move with it.
- **Armature Rig** (Armature page): The armature (*treeArm*) is a child of the tree. After
  generation, the bones are hidden in the bone collection *Sapling Bones*. To show them, click the
  eye icon of that collection in *Armature Properties > Bone Collections*. *Fast Preview* shows the
  bones and draws the tree as its bounding box.
  The bones move the bark through a hidden mesh, *tree_joints*. This mesh holds every curve point and
  handle, weighted to its bone. The tree's modifier reads the posed points from it and sweeps the
  bark from them. So the bark stays smooth across the joints, and the *Bevel* inputs stay live.
  *Joint Levels* and *Joint Length* set how many bones the rig has. Level 1 rigs the trunk, level 2
  adds its branches, and so on. A stem above the levels follows the nearest bone below it. One bone
  spans *Joint Length* stem segments. Blender creates each bone in time proportional to the bones
  that already exist, so the build time of a rig grows with the square of its bone count (measured:
  79,648 bones took 415 s). The operator warns above 10,000 bones and refuses above 40,000.
- **Wind** (Animation page): With *Armature Rig*, the wind animates the bones with F-curves. Without
  the rig, the wind moves the same joints in Geometry Nodes and needs no bones. A hidden Curves
  object, *tree_wind*, holds one point per joint. The *Sapling Wind* modifier composes the joint
  transforms on it every frame. The tree's sweep, the leaves and a baked mesh read their joint's
  transform from it.
- **Make Mesh** (Armature page): Bakes the branches into a plain mesh in the tree object. With a rig,
  the mesh is weighted to the bones, so it exports as a skinned mesh. Without a rig, the mesh follows
  the node wind. The *Bevel* inputs are then fixed, *Fast Preview* shows the bounds, and playback is
  heavier because every vertex is deformed. Without *Make Mesh* the branches stay a live Geometry
  Nodes sweep. An export with modifiers applied also writes that sweep as a mesh.
- **Trunks** (Branch Splitting page): More than 1 grows a clump, such as bamboo. The further trunks
  stand on a disc around the first, each with its own size, curve direction and branches. *Trunks
  Face Out* turns them so that they curve away from the centre.
- **Bend Variation** (Branch Growth page): Turns each segment of a level sideways by a random angle,
  up to the value divided by the level's segments. The first segment of a stem and a segment that
  splits do not turn.
- **Count Above Base** (Branch Splitting page), **Leaves Above Base** and **Fan Angles** (Leaves
  page): tree-gen's ways to count branches above the bare base, keep leaves off it, and cup a
  palmate fan. Palms and bamboo need them. Each is off by default.
- **Blossoms** (Leaves page): *Blossom Rate* is the part of the leaf positions that grows a flower
  instead of a leaf. The flowers (cherry, orange or magnolia, *Blossom Scale* across) are in a
  separate *blossoms* object and move with the leaves.
- **Helix** (Branch Growth page): Grows the stems of a level as helixes, half a turn per segment.
  *Curvature Variation* sets the helix angle. It must be less than 90 degrees. Helix stems do not
  split, curve or bend.
- **Pruning:** Stems that grow out of the pruning envelope are shortened. With *Prune Ratio* 1, a
  stem that would keep less than 15 % of its length is removed, with its leaves. The envelope (two
  profile curves) is hidden after generation. *Object Properties > Visibility* shows it.
- **Instance Points** leaves: A Geometry Nodes modifier (*Sapling Leaf Instancer*) puts your leaf
  object on each leaf point, with a rotation for each leaf. The leaf object itself does not move.

## Performance

The table shows the time to generate each built-in preset with leaves on, in Blender 5.2.2 on
Windows, at the 0.4.0 release. Each value is a median of 5 runs. The 0.4.0 values are the median of
3 runs of `python tools/bench.py`. During these runs, other processes used 2 of the 24 logical cores,
and the values changed by up to approximately 12 % between runs. Thus, the changes are approximate.

| Preset | Leaves | 0.3.7 (upstream) | 0.4.0 | Change |
| --- | ---: | ---: | ---: | ---: |
| callistemon | 9 588 | 145 ms | 86 ms | −40 % |
| douglas_fir | 52 454 | 1 437 ms | 727 ms | −49 % |
| japanese_maple | 106 800 | 4 418 ms | 1 934 ms | −56 % |
| quaking_aspen | 882 | 16 ms | 12 ms | −25 % |
| small_maple | 36 290 | 862 ms | 516 ms | −40 % |
| small_pine | 48 607 | 881 ms | 600 ms | −32 % |
| weeping_willow | 62 340 | 993 ms | 592 ms | −40 % |
| white_birch | 18 918 | 495 ms | 310 ms | −37 % |
| willow | 1 328 | 59 ms | 48 ms | −18 % |

In 0.4.0, stem growth was no longer O(n²). The old code counted the curve splines for each new
stem, and Blender counts them through a linked list. The old code also copied the bone map for each
stem, also without pruning. In addition, the leaf rotations were calculated one time, not for each
vertex. After 0.4.0, the model moved to NumPy arrays and the tree to Geometry Nodes. `CHANGELOG.md`
(Unreleased) gives the measurements of each step. The benchmark is not part of the checks, because
the times depend on the machine.

## Layout

- `source/` — the extension package
  - `model/` — the tree as arrays, without Blender: `TreeGrower`, `LevelGrower`, `LevelStarter`,
    `LevelSprouts`, `LevelPruning`, `LevelGrid`, `KeyedRandom`, `LeafGenerator`, the joints and their
    sway (`Joints`, `WindModel`), the parameters (`TreeParams`, `WindParams`) and the rotation kernels
  - `build/` — the Blender objects: curves, leaves, armature, wind, baked mesh, materials, tree record,
    and their parameters (`BuildParams`)
  - `ui/` — the Add Tree operator, its properties and pages, the panels and the menus
  - `generator.py` (`TreeGenerator`), `settings.py` (`TreeSettings`), `presets.py` (`PresetStore`)
  - `presets/` — the built-in presets (one Python dictionary each): 7 from upstream, 15 from tree-gen
- `tests/` — the unittest suite, which runs in headless Blender. `tests/golden/` holds the exact
  fingerprints of 55 generated trees. `test_fuzz` grows 100 trees from random settings.
  `test_architecture` checks the layers and the rule of no module-level state.
- `tools/` — `check.py` (all checks), `run_tests.py`, `bench.py` (with `bench_in_blender.py` and
  `bench_baseline.json`), `blender_env.py` and `hooks/pre-commit`

## Decisions

Each item gives the decision and the reason for it.

- **Blender 5.2 LTS only.** Older versions are not supported. Thus the code uses the 5.x animation
  API and the Thin Wall input of the Principled BSDF directly.
- **Classes only.** All code in `source/` is in classes. `test_architecture` checks this rule.
  `tests/` and `tools/` can use functions.
- **Named records.** Every record in `source/` is a class with named fields: no tuple and no
  dictionary holds a record, also as a return value. A sequence of values of one kind is a list or a
  NumPy array. Only Blender's enum items are tuples, because its API takes them. `test_architecture`
  checks this rule.
- **One joint layout for the rig and the wind.** The rig's bones and the node wind's joints come from
  the same `Joints`, with the same sway numbers. The lengths match the old per-bone mathutils code to
  the bit. A bone direction can differ in its last float32 bit, because the reciprocal in mathutils'
  normalize is not the correctly rounded one (measured on 20,000 vectors).
- **The model grows the tree as NumPy arrays, without Blender.** All stems of a level advance one
  segment per step. Blender's handle calculation is ported in float32, and a test compares it with
  Blender bit for bit. The vectorized model draws its random numbers per stem, so the trees differ
  from 0.4.0 (same species, a different individual). The owner accepted this on 2026-10-04.
- **The tree is a mesh that Geometry Nodes fill.** The *Sapling Tree* modifier sweeps the hidden
  curves to the bark. A mesh exports, selects and renders like any other object, and the bevel,
  the resolution and the material stay live inputs.
- **Golden tests use exact values.** The fingerprints hash float32 values without rounding. They are
  valid for Blender 5.2.2 on Windows. A commit that changes a fingerprint must give the reason.
- **Tests use the installed extension.** The tests build the extension zip and install it in a
  temporary user profile, because `bpy.utils.extension_path_user` accepts only an installed package.
- **Pruning is a bisection per trunk.** Each trunk's family is grown again at a smaller scale until
  it fits the envelope. The random numbers are keyed by stem, so a regrown stem is the same stem.
- **Translucent leaves.** Leaves use Thin Wall with Subsurface Weight 1.0. Thin Wall with Transmission
  makes the leaves look like clear glass. `CHANGELOG.md` gives the measurements.
- **Geometry Nodes for Instance Points.** A script cannot set vertex normals since Blender 4.1. Thus
  a Geometry Nodes instancer rotates each leaf from a stored rotation.
- **Errors stop the operation.** The code has no silent defaults. The user can correct a
  `SettingsError` (or a `PresetError`). The operator's `execute` method shows these errors and
  cancels. The sidebar panel's `draw` method also catches a `SettingsError`, because a draw method
  cannot report: the panel shows the reason. A failed generation removes what it made and puts the
  user's leaf object back where it was.
- **Older settings are completed, and the operator says so.** A preset or a tree from an older
  version can lack settings. The operator fills them with the defaults and reports them in a warning.
  The built-in presets are complete. Value conversions are not defaults: one Vertical Attraction
  value becomes the per-level values, and leaf angles of the oldest presets come from the branch
  angles.
- **A tree is its root and the root's descendants with the same tree id.** Edit Sapling Tree makes
  the new tree before it removes the old tree. If the edit fails, the old tree stays.
- **The tree mesh is always the root.** A click on the branches selects the tree. If the armature
  were the root, a move of the tree would separate it from its bones.
- **Objects that a user can select are not hidden.** A hidden object is deselected, and Move, Rotate
  and Scale ignore it. Thus a bone collection hides the bones, and Fast Preview shows the tree as
  its bounding box.
- **Rigs are capped.** Blender creates each bone in time proportional to the bones that exist, so a
  rig of 80,000 bones takes minutes. The operator warns above 10,000 bones and refuses above 40,000.
  *Joint Levels* and *Joint Length* make smaller rigs. Wind without the rig needs no bones.
- **`tools/check.py` checks all code.** It runs ruff (complexity 9 or less, docstrings and type
  annotations in `source/`) and mypy. It also runs the tests and requires 99 % line and 96 % branch
  coverage. Each `type: ignore` must give its reason.

## Credits

Upstream: <https://projects.blender.org/extensions/add_curve_sapling> (v0.3.7). Andrew Hale
(TrumanBlending) and Aaron Buchler wrote the original extension. CansecoGPC, Campbell Barton, Nika
Kutsniashvili and many Blender contributors maintained it (see `git log`). The license is
GPL-3.0-or-later (see `source/blender_manifest.toml`).

Fifteen presets are ported from tree-gen: `acer`, `apple`, `balsam_fir`, `black_oak`, `black_tupelo`,
`cambridge_oak`, `douglas_fir`, `european_larch`, `hill_cherry`, `lombardy_poplar`,
`quaking_aspen_treegen`, `sassafras`, `silver_birch`, `sphere_tree` and `willow` (tree-gen's weeping
willow). They come from tree-gen (<https://github.com/friggog/tree-gen>) by Charlie Hewitt and
contributors. `tools/port_treegen.py` maps their Weber–Penn values to the settings of Sapling and
documents the mapping. These files are GPL-3.0-only, as tree-gen is. Its palm, fan palm and bamboo
are not ported: their fronds do not map to Sapling's leaves.
