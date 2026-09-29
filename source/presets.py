# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree presets: built-in (read-only, in the package) and the user's own (extension user folder)."""

import ast
import re
from pathlib import Path

import bpy

from .settings import TreeSettings


class PresetError(Exception):
    """A preset cannot be read or written; the message is shown to the user."""


class PresetStore:
    """Lists, loads and saves presets. A preset file holds one Python dict literal of settings."""

    SUFFIX = ".py"
    NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$")
    HEADER = "# Sapling Tree Gen preset\n"

    @classmethod
    def for_addon(cls):
        """The store of this add-on (its extension package names the user folder)."""
        return cls(__package__)

    def __init__(self, package):
        self.builtin = Path(__file__).resolve().parent / "presets"
        self.package = package

    @property
    def user(self):
        """The user's preset folder (created on first use)."""
        return Path(bpy.utils.extension_path_user(self.package, path="presets", create=True))

    def names(self):
        """(name, is_builtin) of every preset, built-in first, each group sorted."""
        builtin = sorted(p.stem for p in self.builtin.glob("*" + self.SUFFIX))
        user = sorted(p.stem for p in self.user.glob("*" + self.SUFFIX) if p.stem not in builtin)
        return [(n, True) for n in builtin] + [(n, False) for n in user]

    def load(self, name):
        path = self._existing(name)
        try:
            text = path.read_text(encoding="utf-8")
            body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
            values = ast.literal_eval(body.strip())
        except (OSError, ValueError, SyntaxError) as error:
            raise PresetError(f"Cannot read preset {path.name}: {error}") from error
        if not isinstance(values, dict):
            raise PresetError(f"Preset {path.name} is not a settings dictionary")
        return TreeSettings(values).migrate()

    def save(self, name, settings, overwrite=False):
        if not self.NAME.match(name):
            raise PresetError("Preset names use letters, digits, space, '_', '-' and '.' (at most 64)")
        if (self.builtin / (name + self.SUFFIX)).exists():
            raise PresetError(f"'{name}' is a built-in preset; choose another name")
        path = self.user / (name + self.SUFFIX)
        if path.exists() and not overwrite:
            raise PresetError(f"Preset '{name}' exists; enable Overwrite to replace it")
        path.write_text(self.HEADER + repr(settings.values) + "\n", encoding="utf-8")
        return path

    def _existing(self, name):
        if not self.NAME.match(name):
            raise PresetError(f"Invalid preset name '{name}'")
        for folder in (self.builtin, self.user):
            path = folder / (name + self.SUFFIX)
            if path.exists():
                return path
        raise PresetError(f"Preset '{name}' not found")
