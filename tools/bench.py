# SPDX-License-Identifier: GPL-3.0-or-later

"""Generation time per built-in preset (leaves on), compared with tools/bench_baseline.json.

    python tools/bench.py                  # measure and compare; fails when a preset is >15 % slower
    python tools/bench.py --save-baseline  # measure and store as the new baseline

Run it alone (no other heavy processes): timings are medians of 5 runs on this machine.
"""

import argparse
import json
import sys

from blender_env import BUILD, ROOT, install_fresh, run_script

BASELINE = ROOT / "tools" / "bench_baseline.json"
RESULT = BUILD / "bench_result.json"
TOLERANCE = 0.15


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--save-baseline", action="store_true")
    args = parser.parse_args()

    install_fresh()
    code = run_script(ROOT / "tools" / "bench_in_blender.py", [str(RESULT)])
    if code != 0:
        return code
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    if args.save_baseline:
        BASELINE.write_text(json.dumps(result, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline saved: {BASELINE}")
        return 0

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    slower = []
    print(f"{'preset':16s} {'baseline ms':>12s} {'now ms':>9s} {'change':>8s}")
    for preset, ms in sorted(result.items()):
        base = baseline[preset]
        change = ms / base - 1
        print(f"{preset:16s} {base:12.1f} {ms:9.1f} {change:+8.1%}")
        if change > TOLERANCE:
            slower.append(preset)
    if slower:
        print(f"slower than the baseline by more than {TOLERANCE:.0%}: {', '.join(slower)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
