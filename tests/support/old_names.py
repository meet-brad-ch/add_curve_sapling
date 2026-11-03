# SPDX-License-Identifier: GPL-3.0-or-later

"""The setting ids from before the rename."""

from support.addon import Addon


class OldNames:
    """The setting ids from before the rename."""

    @staticmethod
    def with_old_names(values):
        """The same settings under their old ids."""
        old_of = {new: old for old, new in Addon.module("settings").TreeSettings.RENAMED.items()}
        return {old_of.get(key, key): value for key, value in values.items()}
