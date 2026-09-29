# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree presets: built-in (read-only, in the package) and the user's own (extension user folder)."""

import ast
import re
from dataclasses import dataclass
from pathlib import Path

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
    READ_ERRORS = (OSError, ValueError, SyntaxError, TypeError, RecursionError)

    @classmethod
    def for_addon(cls):
        """The store of this add-on (its extension package names the user folder)."""
        return cls(__package__)

    def __init__(self, package):
        self.builtin = Path(__file__).resolve().parent / "presets"
        self.package = package

    def user_folder(self, create):
        """The user's preset folder; only saving creates it."""
        return Path(bpy.utils.extension_path_user(self.package, path="presets", create=create))

    def entries(self):
        """Every preset, built-in first, each group sorted; user files that cannot be used carry a problem."""
        builtin = sorted(p.stem for p in self.builtin.glob("*" + self.SUFFIX))
        entries = [PresetEntry(name, True, None) for name in builtin]
        taken = {name.casefold() for name in builtin}
        for path in sorted(self.user_folder(create=False).glob("*" + self.SUFFIX)):
            entries.append(PresetEntry(path.stem, False, self.name_problem(path.stem, taken)))
        return entries

    def name_problem(self, name, builtin_names):
        """Why `name` cannot be a user preset name, or None when it can."""
        if not self.NAME.match(name):
            return f"invalid name: {self.NAME_RULE}"
        if name.casefold() in self.RESERVED:
            return f"'{name}' is reserved by Windows"
        if name.casefold() in builtin_names:
            return f"'{name}' is the name of a built-in preset"
        return None

    def load(self, name):
        entry = next((e for e in self.entries() if e.name == name), None)
        if entry is None:
            raise PresetError(f"Preset '{name}' not found")
        if entry.problem:
            raise PresetError(f"Preset file '{name}': {entry.problem}; rename the file")
        path = (self.builtin if entry.builtin else self.user_folder(create=False)) / (name + self.SUFFIX)
        try:
            text = path.read_text(encoding="utf-8")
            body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            values = ast.literal_eval(body.strip())
        except self.READ_ERRORS as error:
            raise PresetError(f"Cannot read preset {path.name}: {error}") from error
        if not isinstance(values, dict):
            raise PresetError(f"Preset {path.name} is not a settings dictionary")
        try:
            return TreeSettings(values).migrate()
        except (KeyError, IndexError, TypeError) as error:
            raise PresetError(f"Preset {path.name} is incomplete or malformed: {error!r}") from error

    def save(self, name, settings, overwrite):
        builtin = {e.name.casefold() for e in self.entries() if e.builtin}
        problem = self.name_problem(name, builtin)
        if problem:
            raise PresetError(f"Cannot save preset: {problem}")
        folder = self.user_folder(create=True)
        same = [p for p in folder.glob("*" + self.SUFFIX) if p.stem.casefold() == name.casefold()]
        if same and not overwrite:
            raise PresetError(f"Preset '{same[0].stem}' exists; enable Overwrite to replace it")
        path = same[0] if same else folder / (name + self.SUFFIX)
        path.write_text(self.HEADER + repr(settings.values) + "\n", encoding="utf-8")
        return path
