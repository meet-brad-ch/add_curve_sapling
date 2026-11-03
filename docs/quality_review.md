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
- **Q2 [N]** Silent clamps in the model: `wind_model.py:50, 64` (`max(x, 1e-6)`, `max(speed, 0.001)`),
  `pruning.py:88`, `joints.py:276` (`np.maximum(radius, 1e-6)`). Fix: refuse the setting with
  `InvalidSettingError`, or name on the line why the clamp is the original behaviour. Changes trees only for the
  inputs that reach the clamp.
- **Q3 [N]** `source/model/geometry.py:92-107`: the scalar `envelope` repeats the vector `envelopes` formula. Fix:
  the scalar calls the vector one. Python `**` and `np.power` may round differently.

### Complexity and control flow (no change to computed trees)
- **Q4** lizard CCN > 10 (bug S2): `build/tree_copy.py` `complete` (12, also a call in `?:`), `_relink_modifiers`
  (11, nesting 4); `settings.py` `_check_migratable` (11, `min(levels, 3)` twice); `tools/port_treegen_in_blender.py`
  `convert` (15, 86 lines), `shape_points` (14); `tests/run.py` `main` (16); tests `features` (11), `check_tree` (12),
  `assert_whole_copy` (11), `test_every_trunk_base_stays_still` (11). Then lizard -C 10 in the gate.
- **Q5** Recursion: `tests/support/fingerprint.py` `FingerprintDiff.first/in_dict/in_list` (mutual);
  `source/settings.py:185` `plain()`. Fix: an explicit work list.
- **Q6** Unbounded loops that end only on data: `model/joints.py:187, 226`, `build/tree_record.py:85` `_top`.
  Fix: a `for` bounded by the size, then raise.
- **Q7** Nested conditional expressions and calls inside `?:`: model `geometry.py:89, 107`, `growth.py:113, 129,
  285`, `branching.py:287, 388`, `level_grid.py:221`, `leaves.py:157`, `joints.py:213`, `params.py:189`, `tree.py:46`;
  `generator.py:179`, `armature.py:131, 229`, `presets.py:80`, `leaf_object.py:97-101`, `settings.py:168-169`,
  `service/trees.py:110`; tools `timing.py:19-21`, `render_ports_in_blender.py:89-90`, `run.py:37, 50`.
- **Q8** A branch on data inside an inner loop: `build/envelope.py:48` (`axis == 0`).

### Fail fast
- **Q9** `build/node_math.py:53` `zip(..., strict=False)` drops values silently. Fix: check the count, raise.
- **Q10** Unchecked `None`/bare errors: `service/trees.py:142` `view_layer() -> Any`, `service/copies.py:21`;
  `build/materials.py:89, 93` and tools `port_treegen_in_blender.py:89-90`, `render_ports_in_blender.py:74, 102`
  `next()` without a default (bare StopIteration); `requirements_check.py:184` `lines.index` (bare ValueError);
  tools `args[0..4]` without a length check; `bench.py:84` `baseline[preset]`; `blender_env.py:62` `--version`
  return code; `ui/duplicate.py:38` the translate result. Fix: raise with a message that names the item.
- **Q11** Silent fallbacks in the port tool: `port_treegen_in_blender.py:148` (leaf shape -> default), `:164`
  (`baseSize_s` 0.25), `:121` (`per_level` pads with 0). Fix: raise, or add to the `Ported.clamped` report.
- **Q12** `tests/support/coverage.py:20` an ImportError decides the coverage mode. Fix: run.py passes the mode.
- **Q13** `model/randomness.py:107` `counts == 0` silently gives index -1; the clamp has no comment.

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
