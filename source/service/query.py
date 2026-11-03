# SPDX-License-Identifier: GPL-3.0-or-later

"""What the panel and the menus show about a tree."""

from dataclasses import dataclass

from bpy.types import Object

from ..build.tree_record import TreeRecord
from ..settings import SettingsError


@dataclass(frozen=True)
class TreeSummary:
    """The panel's text about a tree: its levels and seed, or why its stored settings cannot be read."""

    root_name: str
    text: str
    readable: bool


class TreeQuery:
    """Questions about the objects of a tree."""

    @staticmethod
    def is_tree(ob: Object | None) -> bool:
        """Whether the object is part of a Sapling tree."""
        return TreeRecord.is_tree(ob)

    @staticmethod
    def root_of(ob: Object) -> Object:
        """The tree that the object is a part of."""
        return TreeRecord.root_of(ob)

    @staticmethod
    def summary(root: Object) -> TreeSummary:
        """The levels and seed of the tree, or the reason its stored settings cannot be read."""
        try:
            settings = TreeRecord.settings(root).values
        except SettingsError as error:
            return TreeSummary(root.name, str(error), False)
        text = f"Levels: {settings['levels']}   Seed: {settings['seed']}"
        return TreeSummary(root.name, text, True)
