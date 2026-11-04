# SPDX-License-Identifier: GPL-3.0-or-later

"""Release a version of the extension to the Extensions Platform (RELEASING.md gives the procedure).

    python tools/release.py --dry-run          # the checks, the gate, the build: nothing is tagged, pushed or uploaded
    python tools/release.py --notes-approved   # the same, then tag, push and upload

The version is the manifest's `version`. The release needs:
- a clean work tree whose HEAD is the release remote's main (`--remote`, default origin);
- a CHANGELOG section "## <version> (<YYYY-MM-DD>)";
- the release notes docs/release_notes/<version>.md, at most 1024 characters (the platform's limit);
- no tag v<version> yet, and a version above the platform's newest;
- the gate on every supported Blender (tools/check.py --all-blenders).
Then it builds and validates the zip and prints its SHA-256. With --notes-approved it also tags v<version> (the notes
are the tag message), pushes the tag, makes the tag's release page on projects.blender.org with the notes and the zip
(the token in PROJECTS_BLENDER_TOKEN), uploads the zip with the notes to the platform (the token in
BLENDER_EXTENSIONS_TOKEN) and asks the platform whether the version is listed. The tokens are environment variables,
never files. Each step prints a timestamped line; a failure prints
FAILED and stops.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from blender_env import BUILD, ROOT, SOURCE, BlenderEnv

EXTENSION_ID = "sapling_tree_gen"
PLATFORM = "https://extensions.blender.org"
NOTES_LIMIT = 1024  # characters: the platform's release_notes field
TOKEN_VARIABLE = "BLENDER_EXTENSIONS_TOKEN"  # an API token of the Extensions Platform
PAGES_TOKEN_VARIABLE = "PROJECTS_BLENDER_TOKEN"  # an access token of projects.blender.org (repository write)
REPOSITORY_API = "https://projects.blender.org/api/v1/repos/extensions/add_curve_sapling"


class ReleaseError(Exception):
    """A release step cannot continue; the message says why."""


@dataclass(frozen=True, slots=True)
class Upload:
    """What the platform's upload takes."""

    url: str
    token: str
    package: Path
    notes: str


@dataclass(frozen=True, slots=True)
class ReleasePage:
    """A release page on projects.blender.org (Gitea): the tag's page with the notes and the zip attached."""

    api: str  # the repository's API URL, e.g. https://projects.blender.org/api/v1/repos/extensions/add_curve_sapling
    token: str
    tag: str
    notes: str
    package: Path


@dataclass(frozen=True, slots=True)
class FormPart:
    """One field of a multipart form: a text value, or a file when `filename` is set."""

    name: str
    content: bytes
    filename: str = ""
    content_type: str = ""


class Commands(Protocol):
    """What the release needs to run commands (Shell, or a fake in the tests)."""

    def run(self, command: list[str]) -> str:
        """Run `command` and return its standard output; raise ReleaseError when it fails."""
        ...


class Servers(Protocol):
    """What the release needs from the web APIs (Web, or a fake in the tests)."""

    def get_json(self, url: str) -> dict:
        """GET `url` and return its JSON object."""
        ...

    def upload(self, upload: "Upload") -> dict:
        """Upload the zip and the notes to the platform."""
        ...

    def release_page(self, page: "ReleasePage") -> str:
        """Make the tag's release page with the zip; return its URL."""
        ...


class Shell:
    """Runs commands in the repository; a failed command raises ReleaseError with its output."""

    def run(self, command: list[str]) -> str:
        """Run `command` in the repository root and return its standard output."""
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise ReleaseError(f"{' '.join(command)} failed ({done.returncode}): {done.stdout}{done.stderr}".strip())
        return done.stdout


class Web:
    """The HTTP APIs of the Extensions Platform and of projects.blender.org."""

    def get_json(self, url: str) -> dict:
        """GET `url` and return its JSON object."""
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))

    def upload(self, upload: Upload) -> dict:
        """POST the zip and the notes to the platform as a multipart form; return its JSON answer."""
        parts = [
            FormPart(name="release_notes", content=upload.notes.encode("utf-8")),
            FormPart(
                name="version_file",
                content=upload.package.read_bytes(),
                filename=upload.package.name,
                content_type="application/zip",
            ),
        ]
        return self.post_form(upload.url, f"Bearer {upload.token}", parts, "the platform upload")

    def release_page(self, page: ReleasePage) -> str:
        """Make the tag's release page with the notes, attach the zip, and return the page's URL."""
        authorization = f"token {page.token}"
        fields = {"tag_name": page.tag, "name": page.tag, "body": page.notes}
        request = urllib.request.Request(f"{page.api}/releases", data=json.dumps(fields).encode(), method="POST")
        request.add_header("Authorization", authorization)
        request.add_header("Content-Type", "application/json")
        made = self.send(request, "the release page")
        attachment = FormPart(
            name="attachment",
            content=page.package.read_bytes(),
            filename=page.package.name,
            content_type="application/zip",
        )
        assets = f"{page.api}/releases/{made['id']}/assets?name={page.package.name}"
        self.post_form(assets, authorization, [attachment], "the zip on the release page")
        return str(made["html_url"])

    def post_form(self, url: str, authorization: str, parts: list[FormPart], what: str) -> dict:
        """POST `parts` as a multipart form with the Authorization header; return the JSON answer."""
        boundary = uuid.uuid4().hex
        chunks = []
        for part in parts:
            disposition = f'Content-Disposition: form-data; name="{part.name}"'
            if part.filename:
                disposition += f'; filename="{part.filename}"\r\nContent-Type: {part.content_type}'
            chunks.append(f"--{boundary}\r\n{disposition}\r\n\r\n".encode())
            chunks.append(part.content)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        request = urllib.request.Request(url, data=b"".join(chunks), method="POST")
        request.add_header("Authorization", authorization)
        request.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
        return self.send(request, what)

    @staticmethod
    def send(request: urllib.request.Request, what: str) -> dict:
        """Send `request` and return its JSON answer. Raises ReleaseError with the server's answer on an HTTP error."""
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:  # the server's refusal: its status and message stop the release
            answer = error.read().decode("utf-8", "replace")
            raise ReleaseError(f"{what} failed ({error.code}): {answer}") from error


@dataclass(frozen=True, slots=True, order=True)
class VersionNumber:
    """A version number "major.minor.patch"; numbers compare in that order."""

    major: int
    minor: int
    patch: int


class Version:
    """Version numbers of the manifest and the platform."""

    @staticmethod
    def parse(text: str) -> VersionNumber:
        """The numbers of `text`. Raises ReleaseError when it is not three dot-separated numbers."""
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", text)
        if match is None:
            raise ReleaseError(f"version {text!r} is not major.minor.patch")
        return VersionNumber(major=int(match[1]), minor=int(match[2]), patch=int(match[3]))

    @staticmethod
    def of_manifest(manifest: str) -> str:
        """The `version` of the manifest text. Raises ReleaseError when there is none."""
        match = re.search(r'^version = "([^"]+)"', manifest, re.MULTILINE)
        if match is None:
            raise ReleaseError("source/blender_manifest.toml has no version line")
        return match[1]


class Release:
    """The release steps. The shell, the web and the environment are injected, so tests use fakes."""

    def __init__(
        self,
        shell: Commands,
        web: Servers,
        environment: dict[str, str],
        remote: str,
        root: Path,
        log: Callable[[str], None],
    ) -> None:
        """A release of the repository at `root` through `shell` and `web`, pushing to `remote`, printing with
        `log`."""
        self.shell = shell
        self.web = web
        self.environment = environment
        self.remote = remote
        self.root = root
        self.log = log
        self.version = Version.of_manifest((root / "source" / "blender_manifest.toml").read_text(encoding="utf-8"))
        self.tag = f"v{self.version}"
        self.notes_path = root / "docs" / "release_notes" / f"{self.version}.md"

    def check_tree(self) -> None:
        """The work tree is clean and its HEAD is the remote's main."""
        if self.shell.run(["git", "status", "--porcelain"]).strip():
            raise ReleaseError("the work tree has changes: commit or remove them first")
        self.shell.run(["git", "fetch", self.remote])
        head = self.shell.run(["git", "rev-parse", "HEAD"]).strip()
        main = self.shell.run(["git", "rev-parse", f"{self.remote}/main"]).strip()
        if head != main:
            raise ReleaseError(f"HEAD {head[:9]} is not {self.remote}/main {main[:9]}: release from main")
        self.log(f"work tree clean, HEAD is {self.remote}/main ({head[:9]})")

    def check_changelog(self) -> None:
        """CHANGELOG.md has the dated section of the version."""
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        pattern = rf"^## {re.escape(self.version)} \(\d{{4}}-\d{{2}}-\d{{2}}\)$"
        if re.search(pattern, changelog, re.MULTILINE) is None:
            raise ReleaseError(f"CHANGELOG.md has no section '## {self.version} (YYYY-MM-DD)'")
        self.log(f"CHANGELOG.md has the section of {self.version}")

    def notes(self) -> str:
        """The release notes of the version. Raises ReleaseError when they are missing, empty or too long."""
        if not self.notes_path.is_file():
            raise ReleaseError(f"{self.notes_path.relative_to(self.root)} is missing: write the release notes")
        text = self.notes_path.read_text(encoding="utf-8").strip()
        if not text:
            raise ReleaseError(f"{self.notes_path.relative_to(self.root)} is empty")
        if len(text) > NOTES_LIMIT:
            raise ReleaseError(f"the release notes have {len(text)} characters; the platform takes {NOTES_LIMIT}")
        return text

    def check_new(self) -> None:
        """No tag of the version exists, here or on the remote, and the version is above the platform's newest."""
        if self.shell.run(["git", "tag", "--list", self.tag]).strip():
            raise ReleaseError(f"the tag {self.tag} exists")
        if self.shell.run(["git", "ls-remote", "--tags", self.remote, self.tag]).strip():
            raise ReleaseError(f"the tag {self.tag} exists on {self.remote}")
        newest = self.platform_version()
        if Version.parse(self.version) <= Version.parse(newest):
            raise ReleaseError(f"version {self.version} is not above the platform's {newest}")
        self.log(f"{self.version} is new (the platform has {newest})")

    def platform_version(self) -> str:
        """The newest version that the platform lists for the extension, over every Blender."""
        listing = self.web.get_json(f"{PLATFORM}/api/v1/extensions/")
        versions = [entry["version"] for entry in listing.get("data", []) if entry.get("id") == EXTENSION_ID]
        if not versions:
            raise ReleaseError(f"the platform does not list {EXTENSION_ID}")
        return max(versions, key=Version.parse)

    def gate(self) -> None:
        """The gate on every supported Blender."""
        self.log("gate on every supported Blender (tools/check.py --all-blenders) ...")
        self.shell.run([sys.executable, "tools/check.py", "--all-blenders"])
        self.log("gate passed")

    def build(self) -> Path:
        """Build and validate the zip; return its path."""
        for old in BUILD.glob(f"{EXTENSION_ID}-*.zip"):
            old.unlink()
        blender = str(BlenderEnv.blender_path())
        self.shell.run(
            [
                blender,
                "--factory-startup",
                "-c",
                "extension",
                "build",
                "--source-dir",
                str(SOURCE),
                "--output-dir",
                str(BUILD),
            ]
        )
        package = BUILD / f"{EXTENSION_ID}-{self.version}.zip"
        if not package.is_file():
            raise ReleaseError(f"the build wrote no {package.name}")
        self.shell.run([blender, "--factory-startup", "-c", "extension", "validate", str(package)])
        digest = hashlib.sha256(package.read_bytes()).hexdigest()
        self.log(f"built and validated {package.name}, sha256 {digest}")
        return package

    def token(self, variable: str, source: str) -> str:
        """The token in the environment variable. Raises ReleaseError, naming where to get one, when it is not set."""
        token = self.environment.get(variable, "")
        if not token:
            raise ReleaseError(f"set {variable} to a token from {source}")
        return token

    def publish(self, package: Path, notes: str) -> None:
        """Tag the version with the notes and push the tag, make its release page with the zip, upload the zip to the
        platform and ask whether the platform lists it. Both tokens are checked before the tag."""
        token = self.token(TOKEN_VARIABLE, f"{PLATFORM}/settings/tokens/")
        pages_token = self.token(PAGES_TOKEN_VARIABLE, "https://projects.blender.org/user/settings/applications")
        self.shell.run(["git", "tag", "-a", self.tag, "-F", str(self.notes_path)])
        self.shell.run(["git", "push", self.remote, self.tag])
        self.log(f"tagged {self.tag} and pushed it to {self.remote}")
        page = ReleasePage(api=REPOSITORY_API, token=pages_token, tag=self.tag, notes=notes, package=package)
        self.log(f"release page with {package.name}: {self.web.release_page(page)}")
        url = f"{PLATFORM}/api/v1/extensions/{EXTENSION_ID}/versions/upload/"
        answer = self.web.upload(Upload(url=url, token=token, package=package, notes=notes))
        self.log(f"uploaded: {answer.get('message', answer)}")
        listed = self.platform_version()
        if listed == self.version:
            self.log(f"the platform lists {self.version}")
        else:
            self.log(f"the platform still lists {listed}: {self.version} awaits review")

    def run(self, publish: bool) -> None:
        """The checks, the gate and the build; with `publish` also the tag, the push and the upload."""
        self.check_tree()
        self.check_changelog()
        notes = self.notes()
        self.log(f"release notes {self.notes_path.relative_to(self.root)}: {len(notes)} characters")
        self.check_new()
        self.gate()
        package = self.build()
        if not publish:
            self.log("dry run: nothing tagged, pushed or uploaded")
            return
        self.publish(package, notes)


class Console:
    """The release's output."""

    @staticmethod
    def log(text: str) -> None:
        """Print a timestamped line."""
        print(f"{time.strftime('%H:%M:%S')} {text}", flush=True)


def main() -> int:
    """Release, or check with --dry-run. Returns 0 on success, 1 on a failure."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="checks, gate and build only")
    mode.add_argument("--notes-approved", action="store_true", help="the owner approved the notes: also publish")
    parser.add_argument("--remote", default="origin", help="the git remote of the official repository")
    args = parser.parse_args()
    release = Release(Shell(), Web(), dict(os.environ), args.remote, ROOT, Console.log)
    try:
        release.run(publish=args.notes_approved)
    except ReleaseError as error:
        Console.log(f"FAILED: {error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
