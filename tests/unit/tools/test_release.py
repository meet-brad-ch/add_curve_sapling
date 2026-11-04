# SPDX-License-Identifier: GPL-3.0-or-later

"""Unit tests of tools/: the release tool's checks and its destructive steps (tag, push, upload), with a fake shell
and a fake web."""

import tempfile
import unittest
from pathlib import Path

import release


class FakeShell:
    """Records each command; answers a command from `answers` by its first words, else with an empty output."""

    def __init__(self, answers: dict[str, str]) -> None:
        """A shell that answers with `answers` (key: the command's words joined by spaces, a prefix)."""
        self.answers = answers
        self.commands: list[list[str]] = []

    def run(self, command: list[str]) -> str:
        """Record the command and return its answer."""
        self.commands.append(command)
        text = " ".join(command)
        for prefix, answer in self.answers.items():
            if text.startswith(prefix):
                return answer
        return ""


class FakeWeb:
    """A platform that lists `listed` and records uploads."""

    def __init__(self, listed: str) -> None:
        """A platform whose newest version of the extension is `listed`."""
        self.listed = listed
        self.uploads: list[release.Upload] = []
        self.pages: list[release.ReleasePage] = []

    def get_json(self, url: str) -> dict:
        """The listing with the extension at the listed version."""
        return {"data": [{"id": release.EXTENSION_ID, "version": self.listed}]}

    def upload(self, upload: release.Upload) -> dict:
        """Record the upload."""
        self.uploads.append(upload)
        return {"message": "Extension version uploaded successfully!"}

    def release_page(self, page: release.ReleasePage) -> str:
        """Record the release page."""
        self.pages.append(page)
        return f"https://projects.blender.org/extensions/add_curve_sapling/releases/tag/{page.tag}"


class ReleaseFixtures:
    """A repository folder with a manifest, a changelog and release notes."""

    VERSION = "1.2.0"
    CLEAN = {"git status": "", "git rev-parse HEAD": "abc123\n", "git rev-parse origin/main": "abc123\n"}

    @staticmethod
    def root(folder: Path, notes: str = "Fixes and new presets.") -> Path:
        """Write the files of a release of VERSION into `folder` and return it."""
        (folder / "source").mkdir()
        (folder / "source" / "blender_manifest.toml").write_text(
            f'id = "sapling_tree_gen"\nversion = "{ReleaseFixtures.VERSION}"\n', encoding="utf-8"
        )
        (folder / "CHANGELOG.md").write_text(f"# Changelog\n\n## {ReleaseFixtures.VERSION} (2026-11-10)\n", "utf-8")
        (folder / "docs" / "release_notes").mkdir(parents=True)
        (folder / "docs" / "release_notes" / f"{ReleaseFixtures.VERSION}.md").write_text(notes, encoding="utf-8")
        return folder

    @staticmethod
    def release(
        root: Path, shell: FakeShell, web: FakeWeb, token: str = "secret", pages_token: str = "pages"
    ) -> release.Release:
        """A release of `root` through the fakes, with the two tokens set (or not, when empty)."""
        environment = {}
        if token:
            environment[release.TOKEN_VARIABLE] = token
        if pages_token:
            environment[release.PAGES_TOKEN_VARIABLE] = pages_token
        return release.Release(shell, web, environment, "origin", root, lambda text: None)


class Publish(unittest.TestCase):
    """Publishing tags the version with the notes, pushes only the tag, makes the release page with the zip, then
    uploads with the token and the notes; without either token it stops before any tag."""

    def test_tags_pushes_makes_the_page_then_uploads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ReleaseFixtures.root(Path(folder))
            shell = FakeShell({})
            web = FakeWeb(listed="1.1.0")
            package = root / "sapling_tree_gen-1.2.0.zip"
            package.write_bytes(b"zip")
            notes_text = "Fixes and new presets."
            ReleaseFixtures.release(root, shell, web).publish(package, notes_text)
            notes = str(root / "docs" / "release_notes" / "1.2.0.md")
            self.assertEqual(
                shell.commands, [["git", "tag", "-a", "v1.2.0", "-F", notes], ["git", "push", "origin", "v1.2.0"]]
            )
            self.assertEqual(len(web.uploads), 1)
            upload = web.uploads[0]
            self.assertEqual(upload.token, "secret")
            self.assertEqual(upload.notes, "Fixes and new presets.")
            self.assertEqual(upload.package, package)
            self.assertTrue(upload.url.endswith("/api/v1/extensions/sapling_tree_gen/versions/upload/"))
            self.assertEqual(len(web.pages), 1)
            page = web.pages[0]
            self.assertEqual((page.tag, page.token, page.notes, page.package), ("v1.2.0", "pages", notes_text, package))
            self.assertEqual(page.api, release.REPOSITORY_API)

    def test_no_token_stops_before_the_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ReleaseFixtures.root(Path(folder))
            shell = FakeShell({})
            web = FakeWeb(listed="1.1.0")
            with self.assertRaisesRegex(release.ReleaseError, release.TOKEN_VARIABLE):
                ReleaseFixtures.release(root, shell, web, token="").publish(root / "x.zip", "notes")
            self.assertEqual(shell.commands, [])
            self.assertEqual(web.uploads, [])

    def test_no_pages_token_stops_before_the_tag(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ReleaseFixtures.root(Path(folder))
            shell = FakeShell({})
            web = FakeWeb(listed="1.1.0")
            with self.assertRaisesRegex(release.ReleaseError, release.PAGES_TOKEN_VARIABLE):
                ReleaseFixtures.release(root, shell, web, pages_token="").publish(root / "x.zip", "notes")
            self.assertEqual(shell.commands, [])
            self.assertEqual(web.pages, [])


class Checks(unittest.TestCase):
    """The checks refuse a dirty tree, a HEAD that is not main, a missing dated changelog section, missing or too
    long notes, an existing tag and a version not above the platform's; they pass a good release."""

    def checked(self, answers: dict[str, str], listed: str = "1.1.0", notes: str = "Notes.") -> None:
        """Run the tree, changelog, notes and novelty checks of a fixture release."""
        with tempfile.TemporaryDirectory() as folder:
            root = ReleaseFixtures.root(Path(folder), notes)
            subject = ReleaseFixtures.release(root, FakeShell(answers), FakeWeb(listed))
            subject.check_tree()
            subject.check_changelog()
            subject.notes()
            subject.check_new()

    def test_a_good_release_passes(self):
        self.checked(ReleaseFixtures.CLEAN)

    def test_a_dirty_tree_is_refused(self):
        answers = dict(ReleaseFixtures.CLEAN)
        answers["git status"] = " M README.md\n"
        with self.assertRaisesRegex(release.ReleaseError, "changes"):
            self.checked(answers)

    def test_head_not_main_is_refused(self):
        answers = dict(ReleaseFixtures.CLEAN)
        answers["git rev-parse HEAD"] = "def456\n"
        with self.assertRaisesRegex(release.ReleaseError, "origin/main"):
            self.checked(answers)

    def test_an_existing_tag_is_refused(self):
        answers = dict(ReleaseFixtures.CLEAN)
        answers["git tag --list"] = "v1.2.0\n"
        with self.assertRaisesRegex(release.ReleaseError, "v1.2.0 exists"):
            self.checked(answers)

    def test_a_tag_on_the_remote_is_refused(self):
        answers = dict(ReleaseFixtures.CLEAN)
        answers["git ls-remote"] = "abc123\trefs/tags/v1.2.0\n"
        with self.assertRaisesRegex(release.ReleaseError, "exists on origin"):
            self.checked(answers)

    def test_a_version_not_above_the_platform_is_refused(self):
        with self.assertRaisesRegex(release.ReleaseError, "not above"):
            self.checked(ReleaseFixtures.CLEAN, listed="1.2.0")

    def test_notes_over_the_limit_are_refused(self):
        with self.assertRaisesRegex(release.ReleaseError, "1025 characters"):
            self.checked(ReleaseFixtures.CLEAN, notes="x" * (release.NOTES_LIMIT + 1))

    def test_an_undated_changelog_section_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = ReleaseFixtures.root(Path(folder))
            (root / "CHANGELOG.md").write_text("## 1.2.0 (unreleased)\n", encoding="utf-8")
            subject = ReleaseFixtures.release(root, FakeShell(ReleaseFixtures.CLEAN), FakeWeb("1.1.0"))
            with self.assertRaisesRegex(release.ReleaseError, "YYYY-MM-DD"):
                subject.check_changelog()


class Versions(unittest.TestCase):
    """Versions compare by their numbers, and a malformed one is refused."""

    def test_numbers_compare(self):
        self.assertLess(release.Version.parse("0.3.7"), release.Version.parse("1.0.0"))
        self.assertLess(release.Version.parse("1.9.0"), release.Version.parse("1.10.0"))

    def test_a_malformed_version_is_refused(self):
        with self.assertRaisesRegex(release.ReleaseError, "major.minor.patch"):
            release.Version.parse("1.0")
