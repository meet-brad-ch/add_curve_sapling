# SPDX-License-Identifier: GPL-3.0-or-later

"""A mesh's element counts."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MeshCounts:
    """How many vertices, edges and faces a mesh has."""

    vertices: int
    edges: int
    polygons: int

    @classmethod
    def of(cls, mesh: Any) -> "MeshCounts":
        """The counts of a Blender mesh."""
        return cls(vertices=len(mesh.vertices), edges=len(mesh.edges), polygons=len(mesh.polygons))
