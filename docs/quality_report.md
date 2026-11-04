# Quality report (sw-quality §38)

The engineering report of the 1.0.0 work on the branch `revamp-5.2`. The work is the rewrite, the requirements
and their tests, the thin UI, the quality pass and the presets page. `docs/quality_review.md` lists the items of
the quality pass (Q1 to Q31). Measured on
commit 838e65d with Blender 5.2.2 on Windows (2026-11-03).

## Implementation

Requirements implemented:

```text
docs/requirements.md: 86 requirements (SWR-nnnn, EARS form). 83 are verified by test, 3 by inspection or
analysis. The tests in tests/requirements/ hold one test class per requirement.
```

Primary components:

```text
source/model/    the tree as NumPy arrays, without Blender (growth, branching, pruning, leaves, joints, wind)
source/build/    the Blender objects (curves, node groups, leaves, materials, armature, wind, baked mesh)
source/service/  the operations and their rules (add, edit, duplicate, presets), without the user interface
source/ui/       the operators, settings, pages, panels and menus (Blender glue only, CCN 3 or less)
source/presets/  the 32 built-in presets, each with a description line
tools/           the gate (check.py), the test runner, the benchmark, the requirement check, the preset renders
```

## Verification

```text
Build:                 PASS  (blender --command extension build and validate, in the gate)
Unit tests:            PASS  (tests/unit, in the 364-test run)
Integration tests:     PASS  (tests/requirements in headless Blender 5.2.2: 364 tests, OK)
Lint:                  PASS  (ruff, D1 docstrings on source, tools and tests)
Formatting:            PASS  (ruff format)
Static type check:     PASS  (mypy, 145 files)
Static analysis:       PASS  (vulture dead code with a checked whitelist, lizard)
Cyclomatic complexity: PASS  (lizard -C 10 on source, tools and tests; -C 3 on source/ui)
Line coverage:         99.6 % (gate minimum 99 %)
Branch coverage:       97.4 % (gate minimum 96 %)
```

The full gate on Blender 5.3.0 beta (`--all-blenders`) last passed on commit 9a880fb (line 99.6 %, branch 97.4 %).
After that commit, only the presets, the preset render tool and the documents changed. The gate runs on 5.3 again at
the end of the plan.

Coverage:

```text
Line coverage:            99.6 %
Branch coverage:          97.4 %
Critical uncovered areas: none. The 18 uncovered lines are (a) user-interface entry points that need a window or a
                          mouse event (the redo panel's draw and invoke, the Duplicate operator's invoke: plan step
                          R5c checks them in a live Blender) and (b) raises for a broken install or a corrupt
                          settings JSON (fail-fast messages, each a single line).
```

## Engineering Review

```text
DRY:                         PASS
Unnecessary complexity:      PASS
Hidden fallback behavior:    PASS
Swallowed errors:            PASS
UI/backend separation:       PASS
Testability:                 PASS
Global mutable state:        PASS
OOD compliance:              PASS
Dead code:                   PASS
Dependency hygiene:          PASS
```

- **DRY:** the shared test helpers are support classes (Q16, Q23). One envelope formula (Q3). One joint layout for
  the rig and the wind.
- **Complexity:** every function has CCN 10 or less (the gate's complexity step), at most 6 parameters (Q15) and at
  most 60 lines.
- **Fallbacks and errors:** no silent default, clamp or nudge (Q1, Q2, Q13, Q29). No empty or broad `except`. A
  failed operation removes what it made (SWR tests in `tests/requirements/failures`).
- **Separation:** `source/ui/` calls only the service. An architecture test checks the imports and the UI
  complexity.
- **Global state:** module and class constants are immutable (Q21). No module-level mutable state
  (`test_architecture`).
- **OOD:** behaviour lives in classes. Free functions are only entry points (`main`) and Blender callbacks (Q22).
- **Dead code:** vulture passes. Each whitelisted name is a name that Blender or unittest calls by name, or a
  write to Blender data.
- **Dependencies:** the extension needs only Blender and its bundled NumPy. `requirements-dev.txt` pins the tools.

## Remaining Issues

Introduced by this work:

- `tools/render_presets.py` has no unit tests. Its destructive part, the removal of retired pictures, deletes only
  files that the manifest names. The owner checked the tool's output by eye and approved the sheet.
  `--check` tells when a picture is out of date.

Pre-existing:

- **S3** (`docs/bug_list.md`): the GitHub workflow cannot run in the official repository. Fix: remove it in plan
  step 7.
- **S1** (`docs/bug_list.md`): version 0.3.7 on the Extensions Platform fails on Blender 5.x. Fix: its Blender
  range on the website (plan step 10).

Intentionally deferred:

- The owner's keep or retire decisions (plan step R6, `docs/requirements.md` Appendix B) and the 4 open questions on
  unwanted behaviour (`docs/requirements.md`, "Open questions").
- The setting-effect probe (plan step R3b).
- The user-interface checks in a live Blender (plan step R5c). They also cover the uncovered UI entry points above.
- The release procedure and tool (plan step 6b) and the Blender compatibility checklist (plan step 2a).
