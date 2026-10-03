# SPDX-License-Identifier: GPL-3.0-or-later

"""Geometry Nodes groups that every tree in the file shares, and the modifiers that use them."""

from collections.abc import Callable

import bpy
from bpy.types import NodesModifier, NodeTree, Object

from ..settings import SettingsError


class SharedNodeGroup:
    """Finds or (re)builds a shared node group by name and version, and sets the inputs of its modifiers."""

    VERSION_KEY = "sapling_version"

    @classmethod
    def ensure(cls, name: str, version: int, build: Callable[[NodeTree], None]) -> NodeTree:
        """The node group `name`, rebuilt with `build` if it is missing or from another version.

        Raises SettingsError when a group of that name exists but is not a Geometry Nodes group.
        """
        group = bpy.data.node_groups.get(name)
        if group is not None and group.bl_idname != "GeometryNodeTree":
            raise SettingsError(f"Node group '{name}' exists but is not a Geometry Nodes group; rename it")
        if group is not None and group.get(cls.VERSION_KEY) == version:
            return group
        if group is None:
            group = bpy.data.node_groups.new(name, "GeometryNodeTree")
        group.nodes.clear()
        group.interface.clear()  # type: ignore[union-attr]  # a node group has an interface
        build(group)
        group[cls.VERSION_KEY] = version
        return group

    @staticmethod
    def add_modifier(ob: Object, name: str, group: NodeTree) -> NodesModifier:
        """A Geometry Nodes modifier on ob, running `group`."""
        modifier: NodesModifier = ob.modifiers.new(name, "NODES")  # type: ignore[assignment]  # stub: new() returns the base class
        modifier.node_group = group
        return modifier

    @staticmethod
    def set_input(modifier: NodesModifier, name: str, value: object) -> None:
        """Set the modifier's value for the group input called `name`."""
        group = modifier.node_group
        socket = next(i for i in group.interface.items_tree if getattr(i, "name", "") == name)  # type: ignore[union-attr]  # a modifier made by add_modifier has a group with an interface
        # Blender 5.2: modifier inputs are typed sockets, no longer ID properties
        getattr(modifier.properties.inputs, socket.identifier).value = value  # type: ignore[union-attr]  # stub: optional properties; socket items
