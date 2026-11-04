# SPDX-License-Identifier: GPL-3.0-or-later

"""Runs inside Blender for tools/setting_effect_probe.py: for each setting of the Add Tree operator, does a change of
its value change the generated tree?

Argument after `--`: the JSON file to write. For each case (a built-in preset, or the Quaking Aspen with every feature
on), the tree is generated once as it is and once per setting with that setting changed (a boolean flipped, an enum
moved to its next item, an integer by one, a float by half its value or to 0.3 from zero, each element of an array).
Each result compares the scene's golden fingerprint (tests/support/fingerprint.py) with the case's own: "changed",
"same", or "refused" (the operator cancelled: the new value is not allowed there). Prints one line per setting.
"""

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import bpy

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS.parent / "tests"))
sys.path.insert(0, str(TOOLS))
from blender_env import MODULE  # noqa: E402  (needs the sys.path entries above)
from support.addon import Addon  # noqa: E402  (as above)
from support.fingerprint import Fingerprint  # noqa: E402  (as above)
from support.scene import Scene  # noqa: E402  (as above)


@dataclass(frozen=True, slots=True)
class Case:
    """A tree to change settings on: a built-in preset with some settings set."""

    name: str
    preset: str
    overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Effect:
    """What a change of one setting did in each case."""

    setting: str
    changed_to: dict[str, Any] = field(default_factory=dict)  # per case: the changed value
    result: dict[str, str] = field(default_factory=dict)  # per case: "changed", "same" or "refused"


class SettingEffects:
    """Generates the cases with each setting changed and compares the fingerprints."""

    # The operator's own controls and pointers, not tree settings
    SKIPPED = frozenset({"presetName", "overwrite", "leafDupliObj", "do_update", "chooseSet", "preset", "replace"})
    CASES = (
        Case("japanese_maple", "japanese_maple"),
        Case("small_pine", "small_pine"),
        Case("weeping_willow", "weeping_willow"),
        Case("monterey_pine", "monterey_pine"),
        Case("palm", "palm"),
        Case(
            "aspen_rig_all",
            "quaking_aspen",
            {"showLeaves": True, "useRig": True, "windAnim": True, "leafFlutter": True, "prune": True},
        ),
        Case(
            "aspen_nodes_all",
            "quaking_aspen",
            {
                "showLeaves": True,
                "useRig": False,
                "windAnim": True,
                "leafFlutter": True,
                "prune": True,
                "makeMesh": True,
            },
        ),
    )

    def __init__(self) -> None:
        """The operator's settings as Blender declares them, without the skipped ones and the hidden ones (the old
        names and the operator's internal flags)."""
        operator = bpy.ops.curve.tree_add.get_rna_type()
        self.properties = [
            prop
            for prop in operator.properties
            if prop.identifier != "rna_type" and prop.identifier not in self.SKIPPED and not prop.is_hidden
        ]

    @staticmethod
    def fingerprint(settings: dict[str, Any]) -> str | None:
        """The scene fingerprint of a tree made from `settings` in an empty scene; None when the operator refuses
        them (it reports an error, which bpy.ops raises as RuntimeError, or cancels)."""
        Scene.reset()
        try:
            result = bpy.ops.curve.tree_add(**settings, do_update=True)
        except RuntimeError as error:  # the operator's error report: the value is refused, the probe records it
            print(f"REFUSED {error}".splitlines()[0], flush=True)
            return None
        if result != {"FINISHED"}:
            return None
        return json.dumps(Fingerprint.scene(), sort_keys=True, default=str)

    @staticmethod
    def changed_number(value: float, low: float, high: float, integer: bool) -> float:
        """A different value in the range: an integer by one, a float by half its value (0.3 from zero)."""
        if integer:
            if value + 1 <= high:
                return value + 1
            return value - 1
        new = value * 1.5
        if value == 0:
            new = 0.3
        if new > high:
            new = value * 0.5
        if new < low:
            new = (low + high) / 2 if high < 1e30 else low + 1.0
        return new

    @staticmethod
    def changed_choice(prop: Any, value: Any) -> Any:
        """The enum's next item after `value` (an enum with dynamic items, such as the presets, stays)."""
        items = [item.identifier for item in prop.enum_items]
        if value not in items:
            return value
        index = items.index(value)
        return items[(index + 1) % len(items)]

    def changed(self, prop: Any, value: Any) -> Any:
        """The setting's value changed by the rules of the module docstring."""
        if prop.type == "BOOLEAN":
            if prop.is_array:
                return [not v for v in value]
            return not value
        if prop.type == "ENUM":
            return self.changed_choice(prop, value)
        if prop.type in {"INT", "FLOAT"}:
            integer = prop.type == "INT"
            low = float(prop.hard_min)
            high = float(prop.hard_max)
            if prop.is_array:
                return [self.changed_number(v, low, high, integer) for v in value]
            return self.changed_number(value, low, high, integer)
        return value

    def run(self, out: Path) -> None:
        """Probe every setting in every case and write the effects to `out`."""
        effects = {prop.identifier: Effect(setting=prop.identifier) for prop in self.properties}
        for case in self.CASES:
            settings = Addon.resolve_preset(f"{case.preset}.py")
            settings.update(case.overrides)
            base = self.fingerprint(settings)
            if base is None:
                raise SystemExit(f"FAILED: case {case.name} does not generate")
            started = time.perf_counter()
            for prop in self.properties:
                name = prop.identifier
                if name not in settings:
                    raise SystemExit(f"FAILED: case {case.name} has no setting {name}")
                new_value = self.changed(prop, settings[name])
                trial = dict(settings)
                trial[name] = new_value
                print_value = new_value
                effects[name].changed_to[case.name] = print_value
                if new_value == settings[name]:
                    effects[name].result[case.name] = "same"
                    continue
                fingerprint = self.fingerprint(trial)
                if fingerprint is None:
                    effects[name].result[case.name] = "refused"
                elif fingerprint == base:
                    effects[name].result[case.name] = "same"
                else:
                    effects[name].result[case.name] = "changed"
            print(
                f"CASE {case.name} {len(self.properties)} settings in {time.perf_counter() - started:.0f} s", flush=True
            )
        out.write_text(
            json.dumps([asdict(e) for e in effects.values()], indent=1, default=str) + "\n", encoding="utf-8"
        )
        print(f"WROTE {out}", flush=True)


def main() -> None:
    """Enable the add-on and probe the settings into the JSON file named after `--`."""
    out = Path(sys.argv[sys.argv.index("--") + 1])
    bpy.ops.preferences.addon_enable(module=MODULE)
    SettingEffects().run(out)


main()
