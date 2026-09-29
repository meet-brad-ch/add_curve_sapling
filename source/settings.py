# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree settings as plain data: read from and written to the operator, presets and trees."""

import json


class SettingsError(Exception):
    """Settings the user can fix (bad preset, missing leaf object, ...); shown in the UI as an error."""


class TreeSettings:
    """A dict of generation settings keyed by operator property name.

    Values are plain Python (vectors become lists), so they fit presets and JSON.
    """

    # Presets older than these keys get them derived (see migrate()).
    LEAF_ROTATION_KEYS = ("leafDownAngle", "leafDownAngleV", "leafRotate", "leafRotateV")

    def __init__(self, values=None):
        self.values = dict(values or {})

    @classmethod
    def from_properties(cls, props, names):
        return cls({name: cls._plain(getattr(props, name)) for name in names})

    def apply_to(self, props, names):
        """Set every known setting on props; unknown keys (from old presets) are ignored."""
        for name in names:
            if name in self.values:
                setattr(props, name, self.values[name])

    def to_json(self):
        return json.dumps(self.values, sort_keys=True)

    @classmethod
    def from_json(cls, text):
        return cls(json.loads(text))

    def migrate(self):
        """Bring settings from presets of older add-on versions up to date."""
        v = self.values
        # attractUp was a single value before it became per level
        if isinstance(v.get("attractUp"), int | float):
            v["attractUp"] = [0, 0, v["attractUp"], v["attractUp"]]
        # leaf angles used to be the last branch level's angles
        if "leafDownAngle" not in v and "levels" in v:
            last = min(v["levels"], 3)
            v["leafDownAngle"] = v["downAngle"][last]
            v["leafDownAngleV"] = v["downAngleV"][last]
            v["leafRotate"] = v["rotate"][last]
            v["leafRotateV"] = v["rotateV"][last]
        # Leaf Bend has no control in the panel; a preset never bends the leaves
        v["bend"] = 0
        return self

    @staticmethod
    def _plain(value):
        if isinstance(value, str | bool | int | float):
            return value
        return [TreeSettings._plain(v) for v in value]
