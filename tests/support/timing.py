# SPDX-License-Identifier: GPL-3.0-or-later

"""The time spent in chosen methods while a tree is built."""

import time
import unittest
from dataclasses import dataclass

from support.addon import Addon


@dataclass(frozen=True)
class TimedStage:
    """A method whose time a StageTimer adds up: its add-on module, its class and its name."""

    module: str
    owner: str
    method: str


class StageTimer:
    """Adds up the time spent in the given methods while a tree is built (patched for the test's duration)."""

    def __init__(self, test: unittest.TestCase, stages: tuple[TimedStage, ...]) -> None:
        """Patch each stage method to add its time in seconds to total, until the test cleans up."""
        self.total = 0.0
        for stage in stages:
            method_name = stage.method
            owner = getattr(Addon.module(stage.module), stage.owner)
            raw = owner.__dict__[method_name]
            bound_to_class = isinstance(raw, staticmethod | classmethod)
            if bound_to_class:
                timed = type(raw)(self._timed(raw.__func__))
            else:
                timed = self._timed(raw)
            setattr(owner, method_name, timed)
            test.addCleanup(setattr, owner, method_name, raw)

    def _timed(self, function):
        def timed(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                self.total += time.perf_counter() - started

        return timed
