# SPDX-License-Identifier: GPL-3.0-or-later

"""The link from a test to the requirements it verifies (docs/requirements.md)."""

import re
from typing import Any


class Verifies:
    """A decorator that names the requirements a test class or a test method verifies.

    @Verifies("SWR-0084")
    class Blossoms(unittest.TestCase): ...

    tools/requirements_check.py reads these names from the source for the trace; the IDs are also kept on the test
    (`__requirements__`) for the runner's report.
    """

    PATTERN = re.compile(r"SWR-\d{4}$")

    def __init__(self, *ids: str) -> None:
        """The requirement IDs; raises ValueError for none or for an ID that is not 'SWR-nnnn'."""
        if not ids:
            raise ValueError("Verifies needs at least one requirement ID")
        for ident in ids:
            if not self.PATTERN.match(ident):
                raise ValueError(f"'{ident}' is not a requirement ID (SWR-nnnn)")
        self.ids = ids

    def __call__(self, target: Any) -> Any:
        """The test class or method, with these IDs added to the ones it already names."""
        named = getattr(target, "__requirements__", ())
        target.__requirements__ = tuple(named) + self.ids
        return target
