# SPDX-License-Identifier: GPL-3.0-or-later

"""The time spent in chosen methods while a tree is built."""

import time
import unittest

from support.addon import Addon


class StageTimer:
    """Adds up the time spent in the given methods while a tree is built (patched for the test's duration)."""

    def __init__(self, test: unittest.TestCase, stages: tuple[tuple[str, str, str], ...]) -> None:
        self.total = 0.0
        for module_name, class_name, method_name in stages:
            owner = getattr(Addon.module(module_name), class_name)
            raw = owner.__dict__[method_name]
            function = raw.__func__ if isinstance(raw, staticmethod | classmethod) else raw
            timed = self._timed(function)
            setattr(owner, method_name, type(raw)(timed) if isinstance(raw, staticmethod | classmethod) else timed)
            test.addCleanup(setattr, owner, method_name, raw)

    def _timed(self, function):
        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.total += time.perf_counter() - started

        return timed
