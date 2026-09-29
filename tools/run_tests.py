# SPDX-License-Identifier: GPL-3.0-or-later

"""Build and install the extension into a throwaway profile, then run the test suite in Blender.

python tools/run_tests.py                 # all tests
python tools/run_tests.py -k golden       # tests whose id contains "golden"
python tools/run_tests.py --record-golden # rewrite tests/golden/*.json from the current code
"""

import argparse
import sys

from blender_env import ROOT, install_fresh, run_script


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", dest="pattern", action="append", default=[], help="run only tests matching")
    parser.add_argument("--record-golden", action="store_true", help="rewrite the golden fingerprints")
    parser.add_argument("--no-install", action="store_true", help="reuse the last installed build")
    args = parser.parse_args()

    if not args.no_install:
        install_fresh()
    script_args = [f"-k={p}" for p in args.pattern]
    if args.record_golden:
        script_args.append("--record-golden")
    return run_script(ROOT / "tests" / "run.py", script_args)


if __name__ == "__main__":
    sys.exit(main())
