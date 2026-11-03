# SPDX-License-Identifier: GPL-3.0-or-later

"""The folders the tests read: the repository, the tests and the golden data."""

from pathlib import Path


class Paths:
    """Folders of the repository, independent of where a test module lies."""

    TESTS = Path(__file__).resolve().parent.parent
    ROOT = TESTS.parent
    SOURCE = ROOT / "source"
    GOLDEN = TESTS / "golden"
