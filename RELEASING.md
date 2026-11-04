# Releasing

How to release a version of Sapling Tree Gen to the Extensions Platform, and how to keep it working on new Blender
versions. `tools/release.py` does the steps that a script can do. It stops at the first failure and says why.

## Release a version

1. **Version.** Set `version` in `source/blender_manifest.toml`. Use major.minor.patch:
   - patch: fixes only;
   - minor: new features, every old preset and stored tree still loads;
   - major: a higher minimum Blender, or a change that users must learn again.
2. **Changelog.** Give the version's section in `CHANGELOG.md` its date: `## <version> (YYYY-MM-DD)`. Keep the
   Added, Changed, Removed and Fixed lists.
3. **Release notes.** Write `docs/release_notes/<version>.md`: the changes that a user sees, at most 1024
   characters (the platform's limit), in Simplified Technical English. The owner approves the notes.
4. **Commit and push** the release commit to `main` of <https://projects.blender.org/extensions/add_curve_sapling>.
5. **Dry run.** Run `python tools/release.py --dry-run`. It checks:
   - the work tree is clean and HEAD is `origin/main`;
   - the dated changelog section and the notes are present;
   - no tag `v<version>` exists, and the version is above the platform's newest;
   - the gate passes on every supported Blender (`tools/check.py --all-blenders`).
   Then it builds and validates the zip and prints its SHA-256.
6. **Release.** Set two tokens, in the shell only, never in a file:
   - `BLENDER_EXTENSIONS_TOKEN`: an API token from <https://extensions.blender.org/settings/tokens/>;
   - `PROJECTS_BLENDER_TOKEN`: an access token from <https://projects.blender.org/user/settings/applications>
     with write access to repositories.

   Run `python tools/release.py --notes-approved`. It runs step 5 again, then:
   - tags the commit `v<version>` with the notes as the tag message, and pushes the tag;
   - makes the tag's release page on projects.blender.org, with the notes and the zip;
   - uploads the zip with the notes to the Extensions Platform;
   - tells whether the platform lists the version, or whether the version awaits review.
7. **After the release:**
   - When the minimum Blender went up, set `blender_version_max` of the older versions on the website. Then the
     older Blenders keep a version that works.
   - Close the issues that the version fixes, with a note that names the version.

## Blender compatibility

The extension supports the current Blender LTS and every later release. `blender_version_min` is the current LTS.
The maximum stays open.

- **One code line.** The build code has no checks of the Blender version. When the Blender API changes, one adapter
  module checks for the feature (not the version) and has its own test. `source/build/wind.py` (slotted actions) is
  the model.
- **The supported versions.** `tools/blender_env.py` lists them (`SUPPORTED_VERSIONS`). `tools/check.py
  --all-blenders` runs the gate on each one. The executable of each version comes from `BLENDER_<major>_<minor>`.
- **One set of golden data.** A Blender version gets its own golden data only when a run proves a difference.
  Review and explain the difference first.
- **The tools follow the minimum Blender:** its bundled Python for the venv, ruff's target version and the
  fake-bpy-module stubs. Do not use newer Python syntax.

### For each Blender beta

1. Read the Python API page of the release notes (`https://developer.blender.org/docs/release_notes/<x.y>/python_api/`).
2. Install the beta beside the released versions (in `C:\Apps\OpenSource`) and set `BLENDER_<major>_<minor>`.
3. Run `python tools/check.py --all-blenders` with the beta added to `SUPPORTED_VERSIONS`. A beta failure is an
   early warning. It blocks a release only after Blender releases that version.
4. Fix each failure, and release the fix before the Blender release.

### When a Blender release breaks the extension

1. Set `blender_version_max` of the affected extension version on the website at once, so that the platform stops
   offering it to that Blender.
2. Fix the problem and release a new version.

### At each new Blender LTS

Decide whether to raise the minimum Blender to the new LTS. Raising it is a major version (step 1 above). Set
`blender_version_max` of the older version on the website, so that the older Blenders keep it.
