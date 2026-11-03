# Bug list

The problems found and not fixed yet, newest first. Each item: **ID**, where, what was seen (evidence), cause (or
*hypothesis*, not proven), the fix. A fixed item leaves this list, and its fix commit names its ID. A requirement
that the validation finds broken (`docs/requirements.md`) is entered here with the requirement's ID.

## Open

### S4 The README points at a GitHub download and holds dated history
- **Where:** `README.md` "Download" (GitHub Releases page), "To release a version" (a tag pushed to GitHub),
  "Decisions" ("The owner accepted this on 2026-10-04").
- **Seen:** 2026-11-03, while planning 1.0.0. The official home is projects.blender.org and the Extensions Platform.
- **Fix:** the README rewrite (plan step 5): install from *Get Extensions*, the release procedure, no dated history.

### S3 The GitHub workflow cannot run in the official repository
- **Where:** `.github/workflows/build.yml`.
- **Seen:** 2026-11-03. projects.blender.org does not run GitHub workflows. The workflow publishes a GitHub Release.
- **Fix:** remove it when the code moves to the official repository (plan step 7); the release tool replaces it.

### S2 Eleven functions are over complexity 10 (lizard)
- **Where:** `source/build/tree_copy.py` `complete` (12), `_relink_modifiers` (11); `source/settings.py`
  `_check_migratable` (11); `tools/port_treegen_in_blender.py` `shape_points` (14), `convert` (15);
  `tests/helpers.py` `fingerprint` (12); `tests/run.py` `main` (16); `tests/test_features.py`
  `test_every_trunk_base_stays_still` (11); `tests/test_fuzz.py` `features` (11), `check_tree` (12);
  `tests/test_tree_record.py` `assert_whole_copy` (11).
- **Seen:** 2026-11-03, `lizard -C 10 -w source tools tests -x "./source/presets/*"`. ruff's C901 passes them: it does
  not count `and`/`or` and comprehensions as lizard does.
- **Fix:** the quality pass (plan step 2b), then lizard in `tools/check.py`.

### S1 Version 0.3.7 on the Extensions Platform fails on Blender 5.x
- **Where:** extensions.blender.org, Sapling Tree Gen 0.3.7, Blender range "4.4 and newer".
- **Seen:** 2026-11-03, two reviews on the listing: animation fails in Blender 5.2.1 with
  `'Action' object has no attribute 'fcurves'` in `create_armature`. The platform API gives 0.3.7 to Blender 5.2.
- **Cause:** Blender 5.0 removed `Action.fcurves` (slotted actions). 0.3.7's range is open.
- **Fix:** set 0.3.7's `blender_version_max` to 5.0.0 on the website (plan step 10); 1.0.0 serves Blender 5.2+.
