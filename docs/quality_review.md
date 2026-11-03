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

### State, duplication, style

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
- **Q14** `model/sprouting.py` `SproutArrays`: a frozen dataclass (one commented field per array), built with
  keywords in the same order; `take` and `concatenate` read the names from `fields()` (the `FIELDS` list of Q21 is
  gone). The golden trees do not change.
- **Q15** at most 6 parameters besides self/cls in source/ (lizard -a 7 finds nothing): `FlatCurve` and `LeafSet`
  are frozen dataclasses built with keywords; new records `GridStart` (`LevelGrid`), `LevelPlace`
  (`LevelStarter.children`), `TrunkGroups` (`TrunkPick._rotate_choice`), `SplitStep` (`LevelGrower._split_rows`),
  `HandleArrays` (`AutoHandles.recalculate_flat`). Every value is computed where it was, in the same order; the
  golden trees do not change. `FamilyPositions` and `GrownTree` are frozen dataclasses too.
- **Q16** no tuple returns in tests/ and tools/ (an AST scan finds none outside the port tools): the shared helpers
  became support classes with named records (`OperatorStandIn` from three copies, `RiggedTree` from two copies with
  `assert_selected_and_movable`, `Foliage.grow_with_tree` and `GrownLeaves` from two copies of `Foliage.grow`, also
  Q23 for the tests), `MeshCounts`, `TimedStage`, `DeclaredProperty`, and local records `HelixLevel`, `Turns`,
  `BuildTime`, `LoadedCurve`.
- **Q28** `NodeTrees.counts` frees its temporary mesh in `finally`.
- **Q19** `model/params.py`: `_floats/_bools/_ints` became list comprehensions at the 15 calls, the generic
  `_choice[T]` three explicit membership checks with the same messages (its `{s: s for s in ...}` also shadowed the
  settings parameter `s`, the Q26 item); `requirements_check.verified_ids` matches an `ast.Name` explicitly.
  (`evaluated.py` was Q7; `check.py blender_of` keeps "" for "not set", which `all_blenders` reports at once.)
- **Q26** `curve_data.py`: the comment says why the neighbour arrays are complete; `armature.py`: the comment left the
  `for` header and the bones are named first; `requirements_check.py`: the `while` loop's end is named. Checked and
  kept: `blender_env.py` says the tools run on Python 3.10, which is right (`tools/run_tests.py` runs on the system
  Python, 3.10 here; only the venv is 3.13).
- **Q27** every `assertTrue(all(...))` and `assertFalse(any(...))` (13) asserts that the list of offenders is empty, so a
  failure names them (the first 5 where a list can be long); the three positive `assertTrue(any(...))` stay.
- **Q20** `build/wind.py`: no lambda per bone; each loop makes the bone's X and Z curves (X first, as before) and
  `_write` takes them. `build/tree_root.py`: the closure is the method `_sampled` (the nodes made in the same order).
  `ui/pages.py` keeps its dispatch by name (a draw, not a hot loop); a new unit test checks that `ORDER` has one
  drawing method per entry of `Choices.PAGES`, and the page test takes the page count from `Choices.PAGES`.
- **Q21** class and module constants are immutable (54, rewritten in place by an AST tool, only the brackets
  change): lists became tuples, sets frozensets, dicts `MappingProxyType`. They stay sets where Blender wants a set:
  `bl_options` and the property options `OldSettingNames.HIDDEN`; `PresetChoice._items` stays a list (Blender
  T83360). The port tools wait for the owner's decision. Found on the way: Blender prints a property that fails to
  register (a frozenset `options`) and registers the operator without it and every property after it, so the add-on
  enabled half made; `Registration.check_properties` now raises after each class, naming the missing properties
  (unit test with a probe operator).
- **Q23** one `except` for the four preset read errors; `FollowWindNodes.JOINT` is `NodeWind.JOINT`; the
  `fk_a @ fk_s` chain is `WindNodes._inclusive` (the nodes made in the same order); Attract Out and Wind Bend share
  `LevelGrower._turned` (the same float operations; the golden trees do not change); `Trees.add_with_leaves` calls
  `Trees.add`. Checked and kept: `OldSettingNames` declares each old id (Blender needs a declared property per
  name; `TreeSettings.RENAMED` maps them); `SettingsPages.ORDER` is checked against `Choices.PAGES` by a unit test
  (Q20). The test-helper duplicates were Q16.
- **Q18** the service hands the generator a named type, `SettingValues` (a tree's settings as attributes, a
  missing one named), not a `SimpleNamespace`; `TreeGenerator` takes `SettingValues`, `TreeService.replaced` a
  `TreeResult`. The model's `TreeParams` keeps reading attributes from what it is given (the tests pass their own
  settings objects). Unit tests for `SettingValues`.
- **Q17** `JointSwayBuilder` holds the sway (moved from `Joints`, which keeps the topology); `BranchAngles` holds the
  down-angle taper, the running rotate and the crown shape ratio that `TrunkPick` and `LevelStarter` share;
  `TreeGrower.grow` makes its grower, pruning and level collector together (`TreeGrowth`), no placeholders, the root
  key once; `TreeEdit.claim(name, view_layer)` claims the tree, the constructor only stores.
- **Q22** module functions in classes (an AST tool, every use named through the class): `BlenderEnv` (blender_env,
  9, and its 5 importers), `Gate` (check.py), `BenchScene`, and the test helpers (`ProjectModules`, `CurveFixtures`,
  `KernelFixtures`, `StatsCase`, `RequirementFixtures`); the `main` functions stay. The port tools wait for the owner.
- **Q24** one assignment per line: 31 multiple and chained assignments split (an AST tool: only where no value reads
  a target, a chained value only a name or constant); the float operations unchanged.
- **Q25** docstrings: the 44 constructors and magic methods of source/, the 8 tool functions, the test-support
  functions and the test classes (owner 2026-11-03: test methods keep their sentence names); ruff's D1 is on for
  tools/ and tests/ except the test methods.
