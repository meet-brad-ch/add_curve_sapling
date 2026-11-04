# SPDX-License-Identifier: GPL-3.0-or-later

"""Measure which settings change the generated tree (docs/requirements.md Appendix B).

    python tools/setting_effect_probe.py

It builds and installs the extension in the test profile, runs tools/setting_effect_probe_in_blender.py (each
setting changed in each case, the scene fingerprints compared) and writes build/setting_effects.json. Then it prints
the settings that changed no case, the ones that changed only some, and, for each setting, how many built-in presets
move it off its default. The run takes several minutes.
"""

import ast
import json
import sys
from dataclasses import dataclass

from blender_env import BUILD, ROOT, SOURCE, BlenderEnv

SCRIPT = ROOT / "tools" / "setting_effect_probe_in_blender.py"
RESULT = BUILD / "setting_effects.json"


@dataclass(frozen=True, slots=True)
class Effect:
    """One setting's results per case, as the Blender script writes them."""

    setting: str
    changed_to: dict[str, object]
    result: dict[str, str]


class PresetUse:
    """How the built-in presets set each setting."""

    @staticmethod
    def values() -> dict[str, list[object]]:
        """Each setting's values over the built-in presets (a preset without the setting is not counted)."""
        out: dict[str, list[object]] = {}
        for path in sorted((SOURCE / "presets").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            settings = ast.literal_eval(text[text.index("{") :])
            for key, value in settings.items():
                out.setdefault(key, []).append(value)
        return out


def main() -> int:
    """Probe the settings and print the summary. Returns Blender's exit code, else 0."""
    BlenderEnv.install_fresh()
    code = BlenderEnv.run_script(SCRIPT, [str(RESULT)])
    if code != 0:
        return code
    effects = [Effect(**entry) for entry in json.loads(RESULT.read_text(encoding="utf-8"))]
    uses = PresetUse.values()
    print("setting | changed | same | refused | distinct preset values")
    for effect in effects:
        results = list(effect.result.values())
        changed = results.count("changed")
        same = [case for case, result in effect.result.items() if result == "same"]
        refused = [case for case, result in effect.result.items() if result == "refused"]
        distinct = len({repr(value) for value in uses.get(effect.setting, [])})
        print(
            f"{effect.setting} | {changed}/{len(results)} | {', '.join(same) or '-'} | {', '.join(refused) or '-'} | "
            f"{distinct}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
