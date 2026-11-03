# SPDX-License-Identifier: GPL-3.0-or-later

"""Leaves grown in the model alone, with the tree they grew on."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GrownLeaves:
    """The grown tree (its curve's companion data: sprouts, level ends, bone map) and its generated foliage."""

    grown: Any
    foliage: Any
