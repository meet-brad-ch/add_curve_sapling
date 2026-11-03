# Quality review (simple-code and sw-quality)

The review of the whole code base of 2026-11-03 (plan step 2b), by area: source/model, source/build + service +
ui + root modules, tools + tests. Each finding has an ID; its fix commit names the ID, and a fixed item moves to
"Fixed" with the commit. **[N]**: the fix could change computed trees (the golden data), so the owner decides.

Already good (keep): no broad or empty `except`, no swallowed error, the layering holds (ui -> service ->
build/model, UI CCN <= 3), every function under 60 lines, named dataclasses in most records, fail-fast messages
that name the value, the documented clamps that follow Blender or the original model (float32 radius clip,
`MAX_BASE_SIZE`, `min_radius`, `np.clip` before `arccos`), the vectorized kernels and the loops kept sequential
for the stdlib `Random` stream order.

## Open

### Owner decisions (change computed trees)

### Complexity and control flow (no change to computed trees)
- **Q4 (rest)** lizard CCN > 10 (bug S2): `tools/port_treegen_in_blender.py` `convert` (15, 86 lines),
  `shape_points` (14), after the owner's decision on the port tools (Appendix B). Then lizard -C 10 in the gate.
- **Q7 (rest)** a call inside `?:` in `tools/port_treegen_in_blender.py` (3 sites), after the owner's decision on the
  port tools (Appendix B).

### Fail fast
- **Q10 (rest)** the port tools' bare `next()` and `args[...]` (`port_treegen_in_blender.py`,
  `render_ports_in_blender.py`), after the owner's decision on the port tools (Appendix B).
- **Q11** Silent fallbacks in the port tool: `port_treegen_in_blender.py:148` (leaf shape -> default), `:164`
  (`baseSize_s` 0.25), `:121` (`per_level` pads with 0). Fix: raise, or add to the `Ported.clamped` report.

### Records and structure
- **Q14** `model/sprouting.py:17-90` `SproutArrays`: 11 positional constructor arguments, names repeated in `FIELDS`.
  Fix: a dataclass built with keywords, names from `fields()`.
- **Q15** More than 6 parameters / records as plain classes: model `branching.py:149, 267`, `growth.py:251, 301`,
  `level_grid.py:103`, `leaves.py:76`, `curve_data.py:57, 122`; `LeafSet`, `FlatCurve`, `FamilyPositions`, `GrownTree`.
  Fix: frozen dataclasses and context records (`StepContext`, `TrunkGroups`, `LevelPlace`).
- **Q16** Tuples instead of records: `requirements_check.py:257` `properties()`, `tests/support/timing.py:14`
  stages, `node_trees.py:36` counts, and the tuple returns of 10 test helpers. Fix: frozen dataclasses.
- **Q17** OOD splits: `model/joints.py` `Joints` holds topology and sway (move sway to `JointSwayBuilder`);
  `model/branching.py` `TrunkPick` uses `LevelStarter`'s static methods (a `BranchAngles` object);
  `model/tree.py:64-79` placeholder grower and pruning (temporal coupling), `root_key` twice;
  `build/tree_record.py:159` `TreeEdit.__init__` changes data (an explicit `claim` step).
- **Q18** Duck typing at the service boundary: `service/trees.py:111` and `generator.py:79` (`SimpleNamespace`/`Any`),
  `service/trees.py:122` `replaced(result: Any)`. Fix: named types.
- **Q19** Generic helpers: `model/params.py:58-77` `_floats/_bools/_ints`, the generic `_choice[T]`;
  `getattr(x, "id", "")` in `requirements_check.py:333`, `evaluated.py:71`; `check.py` `blender_of` sentinel.
- **Q20** Callbacks in hot loops: `build/wind.py:93, 105, 116` (a lambda per bone); `tree_root.py:196` closure;
  `ui/pages.py:28` the getattr dispatch.

### State, duplication, style
- **Q21** Mutable class-level lists and dicts: model `params.py:43, 87`, `blossoms.py:37-52`, `leaves.py:33-49`,
  `geometry.py:109`, `sprouting.py:28`; `__init__.py:20`, `settings.py:23, 25, 34`, the `INPUTS` lists of
  `leaf_object.py`, `node_wind.py`, `tree_root.py`, `wind.py`, `ui/properties.py:96`; tests and tools module
  constants (`test_settings.py` CAPS..., `test_architecture.py` LAYERS..., `check.py` DEAD_CODE, the port and render
  tools). Fix: tuples, frozensets, MappingProxyType as class constants. (`PresetChoice._items` stays: Blender T83360.)
- **Q22** Module-level functions (full OOD): 36 in tools (check.py, blender_env.py 9, port_treegen 6, render_ports 10,
  bench 2, the `main`s), 16 in tests (run.py 3, test_trunk `root_of` - a copy of `Trees.root_of`, test_architecture 3,
  test_curve_data 4, test_kernels 2, test_model_stats 1, test_requirements_check 2). Fix: classes, `main` stays.
- **Q23** Duplication: `node_wind.py:32, 186` `JOINT` twice, the `fk_a @ fk_s` subgraph twice; `ui/properties.py`
  repeats `TreeSettings.RENAMED`, `ui/pages.py` `ORDER` repeats `Choices.PAGES`; `growth.py:205-225`
  `_attract_out/_attract_wind`; `Trees.add_with_leaves` vs `Trees.add`; `presets.py:94-105` four equal `except`s.
- **Q24** One idea per line, named locals: model (branching, growth, helix, leaves, curve_data, joints, sprouting,
  wind_model; keep left-to-right order: [N] if regrouped), build (joint_proxy, objects, tree_record, tree_copy,
  settings, leaf_object, node_wind, tree_root: keep the node creation order), tools (render/port multi-assignments),
  `growth.py:106-108` (state changes hidden in an argument list). Magic numbers `growth.py:202`, `branching.py:433`.
- **Q25** Docstrings missing: 9 in source (generator, armature, materials, node_wind, the Blender overrides of ui),
  24 in tests/support, 22 in tools, 308 test methods, 59 classes, 123 other test functions.
- **Q26** Comments and names: `curve_data.py:75` stale comment; `params.py:208` shadows `s`; `blender_env.py:25`
  says Python 3.10 (the venv is 3.13: tomllib); `armature.py:146-151` a comment in a `for` header, a redundant test;
  the bounded `while` loops of `requirements_check.py:235` and `test_trunk.py:20` need their bound named.
- **Q27** Tests: 6 `assertTrue(all/any(...))` without the offenders (test_baked_mesh:48, test_rig:201,
  test_pruning:96, test_flutter:94, test_wind:227, test_tree_structure:239). Fix: assert the offender list is empty.
- **Q28** `tests/support/node_trees.py:36` `to_mesh_clear()` not in `finally`.

## Fixed

- **Q1** (owner 2026-11-03: validate the input, remove the nudge) the zero-scale nudge removed; SWR-0076
  refuses Scale - Scale Variation <= 0. Measured: 14 of 77 golden cases change visibly (12 in element counts),
  the others by less than 0.1 %; golden data re-recorded. Commit: see git log for SWR-0076.
- **Q2** (no fallbacks) the four clamps replaced by explicit rules: a pruned-away stem (length 0) has no wave;
  a joint of radius 0 raises (a model defect); Prune Base Height and Trunk Height at 1 are refused (SWR-0077);
  Flutter Speed <= 0 with Leaf Flutter is refused (SWR-0125). Measured: 7 golden cases have pruned-away stems,
  none reaches the other three; the golden data does not change (the removed stems have no joints).
- **Q3** (owner: merge) one envelope formula: `envelope()` calls `envelopes()`, which computes each branch only on
  its own ratios (no suppressed divide warnings; runs under -W error). The vector formula is bit-identical to
  before on 630 parameter sets; the old scalar one differed by at most 1.1e-16, which the envelope curve's
  float32 points round away: the golden data does not change.
- **Q29** (found by the owner-rule scan) `model/rotations.py` `from_matrices`: all four Shepperd branches ran on every
  matrix under `np.errstate(ignore)`; now each runs only on its own matrices (no division by zero, no clamp in the
  sqrt), and a non-finite result raises. Bit-identical on 200,005 matrices, warning-free under -W error.
- **Q30** `settings.py` `old_wind_without_rig`: the nested `.get(..., False)` is an explicit rule with the named
  `TreeSettings.RIG_DEFAULT` (a left-out setting has its default, SWR-0047); a unit test checks it equals useRig's.
- **Q31** `build/node_groups.py` `set_input`: `getattr(i, "name", "")` became an explicit input-socket match.
- **Q32** `model/params.py` `PlainParams`: `getattr(self, "_frozen", False)` became a class attribute.
  `model/randomness.py`: the remaining `errstate(over="ignore")` are the hash's defined uint64 wrap (commented).
- **Q4 (source part)** `build/tree_copy.py` `complete` split into `_copy_parts`/`_copy_of_part`/`_copy_face_instances`/
  `_relink_all`/`_retag`, `_relink_modifiers` into `_relink_armature`/`_relink_node_inputs`; `settings.py`
  `_check_migratable` with `_check_angle_sources` and `angle_source_level` (the `min(levels, 3)` once). lizard -C 10 on
  source/ now finds nothing. (Open: the tools and tests functions of Q4.)
- **Q5 (source part)** `settings.py` `plain()`: one explicit level (Blender's array properties), a nested or unknown
  value raises SettingsError. (Open: tests/support `FingerprintDiff`.)
- **Q6** the loops over parent links are bounded: `joints.depths`, `joints.nearest_joint`, `tree_record._top`; a cycle
  raises. Unit tests force each raise.
- **Q4 (tests part)** `tests/run.py` `main` became `RunOptions` (a dataclass, parsed once), `CoverageRun` and
  `TestRun` (also its Q7 ternaries, the Q16 `minimums` tuple and its Q22 module functions); the fuzz test's `features`
  and `check_tree`, `assert_whole_copy` and `test_every_trunk_base_stays_still` split into named helpers. lizard -C 10
  on source/ and tests/ finds nothing. (Open: the port tool's `convert` and `shape_points`: Appendix B proposes the
  port tools for retirement, the owner decides first.)
- **Q5** `FingerprintDiff`: an explicit work list (`DiffStep`), depth first in key order, the same report text;
  unit tests in tests/unit/support. `test_trunk.root_of` (Q22/Q26: a bone's parent chain, not a copy of
  `Trees.root_of`) is a bounded method of its test class.
- **Q7** every conditional expression with a call or a nested one (found by an AST scan of every `IfExp`: 19 in
  source, 14 in tests and tools/check.py) became an `if` statement; each call stays in its own branch and the float
  expressions are unchanged. The nested `np.where` of `geometry._customs` names its inner segment. `evaluated.py` names an ID input by `isinstance(value, bpy.types.ID)`, not `hasattr`;
  `test_architecture.defined_name` matches Name and Attribute targets, not `getattr(..., "id", "")` (also Q19 there).
- **Q8** `build/envelope.py`: the profile's axis is the index of the coordinate that holds the width; no branch in
  the point loop.
- **Q9** `build/node_math.py` `math`: more values than enabled inputs raises ValueError (it dropped them); unit test.
- **Q12** `tests/support/coverage.py`: the imported `coverage` module (only `CoverageRun` imports it) tells whether
  coverage is measured; no ImportError decides.
- **Q13** `model/randomness.py` `pick`: a count below 1 raises (it gave index -1); the `np.minimum` clamp is removed:
  `uniform` is k * 2**-53, so the floor stays below the count (checked for every count up to 2,000,000 and near each
  power of two up to 2**52: the clamp acted on none). Unit tests.
- **Q10** a missing view layer raises before any work (`TreeService.view_layer`, `TreeCopies.duplicate`); a material
  without its node names it (`MaterialLibrary._node`); `requirements_check` names a missing Appendix A heading,
  `bench` a preset without a baseline time, `blender_env` a failed `--version`; the test helpers name what they did
  not find. `ui/duplicate.py`: a Move that does not start leaves the copy in place, as Blender's Duplicate does
  (commented, not an error). Unit tests for the new raises.
