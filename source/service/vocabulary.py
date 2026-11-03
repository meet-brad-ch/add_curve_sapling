# SPDX-License-Identifier: GPL-3.0-or-later

"""The model's vocabularies and errors that the panel declares or reports, passed through to the UI.

The `X as X` imports are explicit re-exports (the UI imports them from here, not from the model).
"""

from ..model.blossoms import BlossomShape as BlossomShape
from ..model.geometry import CrownShape as CrownShape
from ..model.leaves import LeafShape as LeafShape
from ..model.params import BranchingMode as BranchingMode
from ..model.params import InvalidSettingError
from ..settings import SettingsError


class SettingErrors:
    """The errors of bad settings: an operator reports them and cancels."""

    TYPES = (SettingsError, InvalidSettingError)
