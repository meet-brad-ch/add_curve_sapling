# SPDX-License-Identifier: GPL-3.0-or-later

"""The golden option matrix: (case name, built-in preset, settings overrides).

Each recorded case stores its fully resolved settings, so the comparison exercises generation only
and does not depend on how presets are loaded.
"""

from typing import Any

PRESETS = (
    "callistemon",
    "douglas_fir",
    "japanese_maple",
    "quaking_aspen",
    "small_maple",
    "small_pine",
    "weeping_willow",
    "white_birch",
    "willow",
    # Ported from tree-gen (friggog/tree-gen, GPL-3.0)
    "acer",
    "apple",
    "balsam_fir",
    "black_oak",
    "black_tupelo",
    "cambridge_oak",
    "european_larch",
    "hill_cherry",
    "lombardy_poplar",
    "quaking_aspen_treegen",
    "sassafras",
    "silver_birch",
    "sphere_tree",
)

# Cases on quaking_aspen pin its former 2 levels and leaves off, so they keep testing the trees they were recorded with
CASES: list[tuple[str, str, dict[str, Any]]] = [(f"preset_{name}", name, {}) for name in PRESETS] + [
    # Leaf shapes and placement.
    ("leaf_rect", "callistemon", {"showLeaves": True, "leafShape": "rect"}),
    ("leaf_instance_faces", "callistemon", {"showLeaves": True, "leafShape": "dFace"}),
    ("leaf_instance_points", "callistemon", {"showLeaves": True, "leafShape": "dVert"}),
    ("leaf_palmate", "quaking_aspen", {"levels": 2, "showLeaves": True, "leaves": -5}),
    ("leaf_alternate", "quaking_aspen", {"levels": 2, "showLeaves": True, "leafRotate": -137.5, "leafRotateV": 15.0}),
    ("leaf_not_horizontal", "quaking_aspen", {"levels": 2, "showLeaves": True, "horzLeaves": False, "leafangle": 30.0}),
    ("leaf_bend", "quaking_aspen", {"levels": 2, "showLeaves": True, "bend": 0.5}),
    # Branching options.
    ("trunks_3", "quaking_aspen", {"levels": 2, "showLeaves": False, "trunks": 3}),
    ("branch_bend", "quaking_aspen", {"levels": 2, "showLeaves": False, "bendV": (0.0, 60.0, 0.0, 0.0)}),
    ("branch_bend_prune", "callistemon", {"prune": True, "bendV": (20.0, 50.0, 0.0, 0.0)}),
    (
        "helix",
        "quaking_aspen",
        {"levels": 3, "showLeaves": True, "helix": (False, True, False, False), "curveV": (20.0, 40.0, 75.0, 0.0)},
    ),
    (
        "helix_trunk_prune",
        "callistemon",
        {"prune": True, "helix": (True, False, False, False), "curveV": (30.0, 50.0, 75.0, 0.0)},
    ),
    ("rings", "quaking_aspen", {"levels": 2, "showLeaves": False, "nrings": 5}),
    ("rmode_original", "quaking_aspen", {"levels": 2, "showLeaves": False, "rMode": "original"}),
    ("rmode_random", "quaking_aspen", {"levels": 2, "showLeaves": False, "rMode": "random"}),
    (
        "new_down_angle",
        "quaking_aspen",
        {"levels": 2, "showLeaves": False, "useOldDownAngle": False, "useParentAngle": False},
    ),
    ("vector_handles", "quaking_aspen", {"levels": 2, "showLeaves": False, "handleType": "1"}),
    ("levels_1", "quaking_aspen", {"showLeaves": False, "levels": 1}),
    ("levels_4", "quaking_aspen", {"showLeaves": False, "levels": 4, "branches": (0, 20, 5, 3)}),
    (
        "levels_5_close_tip",
        "quaking_aspen",
        {"showLeaves": False, "levels": 5, "branches": (0, 8, 3, 2), "closeTip": True},
    ),
    ("no_split_by_len", "callistemon", {"splitByLen": False}),
    (
        "custom_shape",
        "quaking_aspen",
        {"levels": 2, "showLeaves": False, "shape": "8", "customShape": (0.3, 1.0, 0.4, 0.6)},
    ),
    ("no_bevel", "quaking_aspen", {"levels": 2, "showLeaves": False, "bevel": False}),
    # Pruning, armature, animation, baked mesh.
    ("prune", "callistemon", {"prune": True}),
    ("prune_armature", "callistemon", {"prune": True, "useRig": True, "showLeaves": True}),
    ("armature", "callistemon", {"showLeaves": True, "useRig": True}),
    ("armature_step", "quaking_aspen", {"levels": 2, "showLeaves": True, "useRig": True, "jointStep": (2, 2, 1, 1)}),
    ("wind", "quaking_aspen", {"levels": 2, "showLeaves": True, "useRig": True, "windAnim": True}),
    (
        "wind_leaves",
        "quaking_aspen",
        {"levels": 2, "showLeaves": True, "useRig": True, "windAnim": True, "leafFlutter": True},
    ),
    (
        "wind_loop",
        "quaking_aspen",
        {"levels": 2, "showLeaves": False, "useRig": True, "windAnim": True, "loopFrames": 48},
    ),
    ("make_mesh", "quaking_aspen", {"levels": 2, "showLeaves": True, "useRig": True, "makeMesh": True}),
    (
        "armature_all_levels",
        "quaking_aspen",
        {
            "levels": 2,
            "showLeaves": True,
            "useRig": True,
            "makeMesh": True,
            "jointLevels": 0,
            "jointStep": (1, 2, 1, 1),
        },
    ),
    (
        "make_mesh_step",
        "quaking_aspen",
        {
            "levels": 2,
            "showLeaves": False,
            "useRig": True,
            "windAnim": True,
            "makeMesh": True,
            "jointStep": (2, 2, 1, 1),
        },
    ),
    (
        "prune_armature_wind",
        "quaking_aspen",
        {"levels": 2, "prune": True, "showLeaves": True, "useRig": True, "windAnim": True, "leafFlutter": True},
    ),
    # Wind without the rig: forward kinematics in Geometry Nodes.
    ("node_wind", "quaking_aspen", {"levels": 2, "showLeaves": True, "windAnim": True}),
    (
        "node_wind_leaves_mesh",
        "quaking_aspen",
        {"levels": 2, "showLeaves": True, "windAnim": True, "leafFlutter": True, "makeMesh": True, "loopFrames": 48},
    ),
    ("fast_preview", "quaking_aspen", {"levels": 2, "showLeaves": False, "fastPreview": True}),
]
