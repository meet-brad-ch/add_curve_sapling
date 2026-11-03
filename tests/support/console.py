# SPDX-License-Identifier: GPL-3.0-or-later

"""The console output of operators, captured."""

import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager


class Console:
    """What the console showed while it was captured (without a window, Blender prints an operator's reports
    there: "Warning: ...", "Info: ...")."""

    def __init__(self) -> None:
        """An empty capture."""
        self.text = ""

    def lines(self, kind: str) -> list[str]:
        """The printed lines that contain `kind` (e.g. "Warning")."""
        return [line for line in self.text.splitlines() if kind in line]

    @staticmethod
    @contextmanager
    def capture() -> Iterator["Console"]:
        """Capture file descriptor 1 (Blender prints operator reports to it); the Console holds the text after."""
        console = Console()
        with tempfile.TemporaryFile(mode="w+") as captured:
            saved = os.dup(1)
            sys.stdout.flush()
            os.dup2(captured.fileno(), 1)
            try:
                yield console
            finally:
                sys.stdout.flush()
                os.dup2(saved, 1)
                os.close(saved)
                captured.seek(0)
                console.text = captured.read()
