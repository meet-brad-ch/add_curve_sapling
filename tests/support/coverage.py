# SPDX-License-Identifier: GPL-3.0-or-later

"""The gate's coverage measurement, paused where it would distort a timing."""

from collections.abc import Iterator
from contextlib import contextmanager


class Coverage:
    """The gate's coverage measurement, paused where it would distort a timing."""

    @staticmethod
    @contextmanager
    def untraced() -> Iterator[None]:
        """Pause coverage measurement inside: its line tracer slows a build several times over, and unevenly with
        the tree's size (measured: exponent 1.34 traced, 0.98 untraced), so timing tests run without it. The lines
        they run are covered by the other tests. Without the gate's coverage run, nothing is paused."""
        try:
            import coverage
        except ImportError:  # the tests run without the gate's coverage package
            measure = None
        else:
            measure = coverage.Coverage.current()
        if measure is not None:
            measure.stop()
        try:
            yield
        finally:
            if measure is not None:
                measure.start()
