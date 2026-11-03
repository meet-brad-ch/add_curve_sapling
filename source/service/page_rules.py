# SPDX-License-Identifier: GPL-3.0-or-later

"""Which fields the settings pages show, from the current settings."""

from typing import Any

from ..model.geometry import CrownShape
from ..model.leaves import LeafShape


class PageRules:
    """The conditions of the settings pages: a field shows only where it has an effect."""

    @staticmethod
    def custom_shape(props: Any) -> bool:
        """The Custom Shape values: only for the Custom crown shape."""
        return props.shape == str(CrownShape.CUSTOM)

    @staticmethod
    def leaf_object(props: Any) -> bool:
        """The Leaf Object: only for instanced leaf shapes."""
        return props.leafShape in LeafShape.INSTANCED

    @staticmethod
    def blossom_options(props: Any) -> bool:
        """Blossom Shape and Scale: only when some leaf positions are blossoms."""
        return props.blossomRate > 0

    @staticmethod
    def leaf_material(props: Any) -> bool:
        """Leaf Material: for mesh leaves, or when there are blossoms (they always are meshes)."""
        return props.leafShape in LeafShape.MESH or props.blossomRate > 0
