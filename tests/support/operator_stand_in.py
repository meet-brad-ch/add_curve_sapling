# SPDX-License-Identifier: GPL-3.0-or-later

"""A stand-in for the Add Tree operator in its redo panel."""

from dataclasses import dataclass, field
from types import SimpleNamespace

from support.addon import Addon


@dataclass
class OperatorStandIn:
    """A stand-in for the Add Tree operator (its settings as attributes) and the texts it reported."""

    operator: SimpleNamespace
    reports: list[str] = field(default_factory=list)

    @classmethod
    def make(cls, **values) -> "OperatorStandIn":
        """A stand-in in a redo (is_repeat) with the given settings; its ui_change_only is the operator's own."""
        reports: list[str] = []
        stand_in = SimpleNamespace(
            options=SimpleNamespace(is_repeat=True), report=lambda kind, text: reports.append(text), **values
        )
        operator = Addon.module("ui.operators").AddTreeOperator
        stand_in.ui_change_only = lambda: operator.ui_change_only(stand_in)
        return cls(operator=stand_in, reports=reports)
