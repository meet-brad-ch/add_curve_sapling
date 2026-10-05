# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree settings as plain data: read from and written to the operator, presets and trees."""

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Self


class SettingsError(Exception):
    """Settings the user can fix (bad preset, missing leaf object, ...); shown in the UI as an error."""


class TreeSettings:
    """Generation settings keyed by operator property name.

    Values are plain Python (vectors become lists), so they fit presets and JSON.
    """

    # Version of the settings stored on a generated tree (see to_json()).
    VERSION = 1
    # Keys of the oldest preset format that no longer exist.
    OBSOLETE_KEYS = ["startCurv", "windGust", "windSpeed"]
    # Presets older than the leaf angles used the last branch level's angles for the leaves.
    LEAF_ANGLE_SOURCES = {
        "leafDownAngle": "downAngle",
        "leafDownAngleV": "downAngleV",
        "leafRotate": "rotate",
        "leafRotateV": "rotateV",
    }
    # Limit Import: the levels a preset loads with, and no leaves
    LIMITED_LEVELS = 2

    # Setting ids renamed when the wind moved to Geometry Nodes; presets, stored trees and scripts may use the old
    # ids, which load under the new ones
    RENAMED = {
        "useArm": "useRig",
        "armAnim": "windAnim",
        "previewArm": "fastPreview",
        "armLevels": "jointLevels",
        "boneStep": "jointStep",
        "leafAnim": "leafFlutter",
        "wind": "windStrength",
        "gust": "gustStrength",
        "gustF": "gustFrequency",
        "frameRate": "animationSpeed",
        "af1": "flutterStrength",
        "af2": "flutterSpeed",
        "af3": "flutterRandomness",
    }

    def __init__(self, values: object) -> None:
        if not isinstance(values, dict):
            raise SettingsError(f"Settings must be a dictionary, not {type(values).__name__}")
        self.values = dict(values)

    @classmethod
    def from_properties(cls, props: Any, names: Iterable[str]) -> Self:
        """The named settings read from props (the operator, or anything with its property names)."""
        return cls({name: cls.plain(getattr(props, name)) for name in names})

    def missing(self, defaults: Mapping[str, Any]) -> list[str]:
        """The settings of `defaults` these settings do not have, sorted."""
        return sorted(name for name in defaults if name not in self.values)

    def complete(self, defaults: Mapping[str, Any]) -> Self:
        """Fill in the settings an older preset does not have, from the defaults."""
        for name, value in defaults.items():
            self.values.setdefault(name, value)
        return self

    def limit_import(self) -> Self:
        """Limit Import: at most LIMITED_LEVELS levels and no leaves, for a quick look at a preset."""
        self.values["levels"] = min(self.values["levels"], self.LIMITED_LEVELS)
        self.values["showLeaves"] = False
        return self

    def apply_to(self, props: Any, names: Sequence[str]) -> None:
        """Set exactly these settings on props: every name must be given, and nothing else."""
        missing = sorted(set(names) - set(self.values))
        unknown = sorted(set(self.values) - set(names))
        if missing or unknown:
            raise SettingsError(f"Settings do not fit this version: missing {missing}, unknown {unknown}")
        for name in names:
            setattr(props, name, self.values[name])

    def migrate(self) -> Self:
        """Bring settings from presets of older add-on versions up to date; raises SettingsError when the
        settings lack what the migration needs."""
        self.rename_keys()
        v = self.values
        for key in self.OBSOLETE_KEYS:
            v.pop(key, None)  # only the oldest presets have them
        self._check_migratable()
        # attractUp was a single value before it became per level
        if isinstance(v["attractUp"], int | float):
            v["attractUp"] = [0, 0, v["attractUp"], v["attractUp"]]
        if "leafDownAngle" not in v:
            last = min(v["levels"], 3)
            for leaf_key, branch_key in self.LEAF_ANGLE_SOURCES.items():
                v[leaf_key] = v[branch_key][last]
        return self

    def _check_migratable(self) -> None:
        """What migrate() reads must be there and have the right shape."""
        v = self.values
        needed = ["levels", "attractUp"]
        if "leafDownAngle" not in v:
            needed += list(self.LEAF_ANGLE_SOURCES.values())
        missing = [key for key in needed if key not in v]
        if missing:
            raise SettingsError(f"Settings do not have {missing}; this version needs them to load the settings")
        if not isinstance(v["levels"], int):
            raise SettingsError(f"levels must be an integer, not {type(v['levels']).__name__}")
        if "leafDownAngle" in v:
            return
        last = min(v["levels"], 3)
        for key in self.LEAF_ANGLE_SOURCES.values():
            if not isinstance(v[key], list | tuple) or len(v[key]) <= last:
                count = len(v[key]) if isinstance(v[key], list | tuple) else 0
                raise SettingsError(f"{key} has {count} values; {last + 1} are needed")

    def rename_keys(self) -> Self:
        """Settings under their old ids (RENAMED) move to the new ids; raises SettingsError when both are given
        with different values."""
        values = self.values
        still = self.old_wind_without_rig(values)
        for old, new in self.RENAMED.items():
            if old not in values:
                continue
            value = values.pop(old)
            if new in values and values[new] != value:
                raise SettingsError(
                    f"Settings give both {old} (the old name of {new}) and {new}, with different values"
                )
            values[new] = value
        if still:
            values["windAnim"] = False
        return self

    @staticmethod
    def old_wind_without_rig(values: Mapping[str, Any]) -> bool:
        """Old settings with armAnim but no armature: the old wind ran on the armature only, so they had none.

        windAnim without the rig now makes the node wind; these settings keep their still tree.
        """
        return bool(values.get("armAnim")) and not values.get("useArm", values.get("useRig", False))

    def to_json(self) -> str:
        """The settings as versioned JSON, the form a generated tree stores (read back with from_json())."""
        return json.dumps({"version": self.VERSION, "settings": self.values}, sort_keys=True)

    @classmethod
    def from_json(cls, text: str) -> Self:
        """Settings stored by to_json(); raises SettingsError on invalid JSON or another settings version."""
        try:
            data = json.loads(text)
        except ValueError as error:
            raise SettingsError(f"Invalid settings JSON: {error}") from error
        if not isinstance(data, dict) or data.get("version") != cls.VERSION or "settings" not in data:
            found = f"version {data.get('version')!r}" if isinstance(data, dict) else type(data).__name__
            raise SettingsError(f"Settings JSON must be a version {cls.VERSION} settings object; got {found}")
        return cls(data["settings"])

    @classmethod
    def defaults_from_rna(cls, properties: Any, names: Iterable[str]) -> Self:
        """The RNA default of each named property (bpy.types.Property collection)."""
        values = {}
        for name in names:
            prop = properties[name]
            # Only numeric and boolean properties can be arrays (enums and strings have no is_array)
            is_array = prop.type in {"BOOLEAN", "INT", "FLOAT"} and prop.is_array
            values[name] = cls.plain(prop.default_array if is_array else prop.default)
        return cls(values)

    @staticmethod
    def plain(value: Any) -> Any:
        """A property value as plain Python: vectors (bpy arrays) become lists."""
        if isinstance(value, str | bool | int | float):
            return value
        return [TreeSettings.plain(v) for v in value]
