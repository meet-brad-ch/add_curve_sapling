# SPDX-License-Identifier: GPL-3.0-or-later

"""The test scene: reset, the generated objects, data-block counts, generation through the operator."""

from typing import Any

import bpy


class Scene:
    """The test scene: reset, the generated objects, data-block counts, generation through the operator."""

    LEAF_CARD = "leaf_card"
    DATA = ["objects", "curves", "hair_curves", "meshes", "armatures", "actions"]

    @staticmethod
    def reset() -> None:
        """Remove everything a tree generation creates, so data names never get .001 suffixes."""
        collections: tuple[Any, ...] = (
            bpy.data.objects,
            bpy.data.curves,
            bpy.data.hair_curves,
            bpy.data.meshes,
            bpy.data.armatures,
            bpy.data.actions,
            bpy.data.materials,
            bpy.data.node_groups,
        )
        for collection in collections:
            for block in list(collection):
                collection.remove(block)
        scene = bpy.context.scene
        scene.render.fps = 24  # wind animation speed depends on the scene frame rate
        scene.render.fps_base = 1.0
        scene.frame_set(1)

    @staticmethod
    def active_object() -> Any:
        """The active object, which a test expects to exist (the new tree root after an Add)."""
        ob = bpy.context.active_object
        if ob is None:
            raise AssertionError("no active object")
        return ob

    @classmethod
    def counts(cls, names: list[str] | None = None) -> dict[str, int]:
        """How many data-blocks of each kind the file holds (by default the kinds a tree creates)."""
        kinds = cls.DATA if names is None else names
        return {name: len(getattr(bpy.data, name)) for name in kinds}

    @staticmethod
    def armature() -> Any:
        """The scene's armature object (the rig of the one tree)."""
        return next(ob for ob in bpy.data.objects if ob.type == "ARMATURE")

    @classmethod
    def add_leaf_card(cls) -> Any:
        """A user's leaf object for instanced leaves (an empty mesh is enough to instance)."""
        card = bpy.data.objects.new(cls.LEAF_CARD, bpy.data.meshes.new(cls.LEAF_CARD))
        bpy.context.scene.collection.objects.link(card)
        return card

    @classmethod
    def generate(cls, settings: dict) -> set:
        """Run the operator with explicit settings on an empty scene; return the result set.

        Instanced leaf shapes get a leaf object, as they require.
        """
        cls.reset()
        extra = {}
        if settings.get("showLeaves") and settings.get("leafShape") in ("dFace", "dVert"):
            extra["leafDupliObj"] = cls.add_leaf_card().name
        # Blender applies operator keywords in property-definition order and runs their update callbacks;
        # the callbacks of UI-only properties (limitImport, chooseSet, ...) clear do_update, so only
        # generation settings are passed.
        return bpy.ops.curve.tree_add(**settings, **extra, do_update=True)
