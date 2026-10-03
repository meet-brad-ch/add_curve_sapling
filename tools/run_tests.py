# SPDX-License-Identifier: GPL-3.0-or-later

"""Build and install the extension into a throwaway profile, then run the test suite in Blender.

python tools/run_tests.py                 # all tests
python tools/run_tests.py -k golden       # tests whose id contains "golden"
python tools/run_tests.py --record-golden # rewrite tests/golden/*.json from the current code
python tools/run_tests.py --coverage 99 96   # with coverage; fails below 99 % lines or 96 % branches
"""

import argparse
import sys

from blender_env import ROOT, install_fresh, run_script, venv_site_packages


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-k", dest="pattern", action="append", default=[], help="run only tests matching")
    parser.add_argument("--record-golden", action="store_true", help="rewrite the golden fingerprints")
    parser.add_argument("--no-install", action="store_true", help="reuse the last installed build")
    parser.add_argument(
        "--coverage",
        type=float,
        nargs=2,
        metavar=("LINE_MIN", "BRANCH_MIN"),
        help="measure line and branch coverage; fail below either minimum (in %%)",
    )
    args = parser.parse_args()

    if not args.no_install:
        install_fresh()
    script_args = [f"-k={p}" for p in args.pattern]
    if args.record_golden:
        script_args.append("--record-golden")
    if args.coverage is not None:
        line_min, branch_min = args.coverage
        script_args += [f"--line-min={line_min}", f"--branch-min={branch_min}", f"--site={venv_site_packages()}"]
    return run_script(ROOT / "tests" / "run.py", script_args)


if __name__ == "__main__":
    sys.exit(main())
