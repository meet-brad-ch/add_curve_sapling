# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree presets: built-in (read-only, in the package) and the user's own (extension user folder)."""

import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Self

import bpy

from .settings import SettingsError, TreeSettings


class PresetError(SettingsError):
    """A preset cannot be read or written; the message is shown to the user."""


@dataclass(frozen=True, slots=True)
class PresetEntry:
    """A preset in the list; `problem` says why a user file cannot be loaded (None when it can)."""

    name: str
    builtin: bool
    problem: str | None


class PresetStore:
    """Lists, loads and saves presets. A preset file holds one Python dict literal of settings."""

    SUFFIX = ".py"
    NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
    NAME_RULE = "use letters, digits, space, '_', '-' and '.' (at most 64, starting with a letter or digit)"
    # File names Windows reserves for devices.
    RESERVED = frozenset(
        {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    )
    HEADER = "# Sapling Tree Gen preset\n"

    @classmethod
    def for_addon(cls) -> Self:
        """The store of this add-on (its extension package names the user folder)."""
        return cls(__package__)

    def __init__(self, package: str) -> None:
        self.builtin = Path(__file__).resolve().parent / "presets"
        self.package = package

    def user_folder(self, create: bool) -> Path:
        """The user's preset folder; only saving creates it."""
        return Path(bpy.utils.extension_path_user(self.package, path="presets", create=create))

    def entries(self) -> list[PresetEntry]:
        """Every preset, built-in first, each group sorted; user files that cannot be used carry a problem."""
        builtin = sorted(p.stem for p in self.builtin.glob("*" + self.SUFFIX))
        entries = [PresetEntry(name, True, None) for name in builtin]
        taken = {name.casefold() for name in builtin}
        for path in sorted(self.user_folder(create=False).glob("*" + self.SUFFIX)):
            entries.append(PresetEntry(path.stem, False, self.name_problem(path.stem, taken)))
        return entries

    def name_problem(self, name: str, builtin_names: set[str]) -> str | None:
        """Why `name` cannot be a user preset name, or None when it can."""
        if not self.NAME.match(name):
            return f"invalid name: {self.NAME_RULE}"
        if name.casefold() in self.RESERVED:
            return f"'{name}' is reserved by Windows"
        if name.casefold() in builtin_names:
            return f"'{name}' is the name of a built-in preset"
        return None

    def load(self, name: str) -> TreeSettings:
        """The preset's settings, migrated to this version; raises PresetError when it is missing or unreadable."""
        entry = next((e for e in self.entries() if e.name == name), None)
        if entry is None:
            raise PresetError(f"Preset '{name}' not found")
        if entry.problem:
            raise PresetError(f"Preset file '{name}': {entry.problem}. Rename the file")
        path = (self.builtin if entry.builtin else self.user_folder(create=False)) / (name + self.SUFFIX)
        values = self._read(path)
        if not isinstance(values, dict):
            raise PresetError(f"Preset {path.name} is not a settings dictionary")
        try:
            return TreeSettings(values).migrate()
        except SettingsError as error:
            raise PresetError(f"Preset {path.name}: {error}") from error

    @staticmethod
    def _read(path: Path) -> object:
        """The Python literal a preset file holds (comment lines skipped); raises PresetError when it cannot be read:
        the file (OSError), its text (ValueError: not UTF-8, or a literal Python cannot evaluate), its syntax
        (SyntaxError), an unhashable dictionary key (TypeError)."""
        try:
            text = path.read_text(encoding="utf-8")
            body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            return ast.literal_eval(body.strip())
        except OSError as error:
            raise PresetStore._unreadable(path, error) from error
        except ValueError as error:
            raise PresetStore._unreadable(path, error) from error
        except SyntaxError as error:
            raise PresetStore._unreadable(path, error) from error
        except TypeError as error:
            raise PresetStore._unreadable(path, error) from error

    @staticmethod
    def _unreadable(path: Path, error: Exception) -> "PresetError":
        """The error for a preset file that cannot be read."""
        return PresetError(f"Cannot read preset {path.name}: {error}")

    def save(self, name: str, settings: TreeSettings, overwrite: bool) -> Path:
        """Write settings as the user preset `name` and return its file.

        Raises PresetError for an invalid name or when the preset exists and overwrite is off; a
        preset that differs only in case is replaced under its existing file name.
        """
        builtin = {e.name.casefold() for e in self.entries() if e.builtin}
        problem = self.name_problem(name, builtin)
        if problem:
            raise PresetError(f"Cannot save preset: {problem}")
        folder = self.user_folder(create=True)
        same = [p for p in folder.glob("*" + self.SUFFIX) if p.stem.casefold() == name.casefold()]
        if same and not overwrite:
            raise PresetError(f"Preset '{same[0].stem}' exists. Enable Overwrite to replace it")
        path = same[0] if same else folder / (name + self.SUFFIX)
        path.write_text(self.HEADER + repr(settings.values) + "\n", encoding="utf-8")
        return path
