# SPDX-License-Identifier: GPL-3.0-or-later

"""The golden option matrix: (case name, built-in preset, settings overrides).

Each recorded case stores its fully resolved settings, so the comparison exercises generation only
and does not depend on how presets are loaded.
"""

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
)

CASES = [(f"preset_{name}", name, {}) for name in PRESETS] + [
    # Leaf shapes and placement.
    ("leaf_rect", "callistemon", {"showLeaves": True, "leafShape": "rect"}),
    ("leaf_instance_faces", "callistemon", {"showLeaves": True, "leafShape": "dFace"}),
    ("leaf_instance_points", "callistemon", {"showLeaves": True, "leafShape": "dVert"}),
    ("leaf_palmate", "quaking_aspen", {"showLeaves": True, "leaves": -5}),
    ("leaf_not_horizontal", "quaking_aspen", {"showLeaves": True, "horzLeaves": False, "leafangle": 30.0}),
    ("leaf_bend", "quaking_aspen", {"showLeaves": True, "bend": 0.5}),
    # Branching options.
    ("rings", "quaking_aspen", {"nrings": 5}),
    ("rmode_original", "quaking_aspen", {"rMode": "original"}),
    ("rmode_random", "quaking_aspen", {"rMode": "random"}),
    ("new_down_angle", "quaking_aspen", {"useOldDownAngle": False, "useParentAngle": False}),
    ("vector_handles", "quaking_aspen", {"handleType": "1"}),
    ("levels_1", "quaking_aspen", {"levels": 1}),
    ("levels_4", "quaking_aspen", {"levels": 4, "branches": (0, 20, 5, 3)}),
    ("no_split_by_len", "callistemon", {"splitByLen": False}),
    ("custom_shape", "quaking_aspen", {"shape": "8", "customShape": (0.3, 1.0, 0.4, 0.6)}),
    ("no_bevel", "quaking_aspen", {"bevel": False}),
    # Pruning, armature, animation, skin mesh.
    ("prune", "callistemon", {"prune": True}),
    ("prune_armature", "callistemon", {"prune": True, "useArm": True, "showLeaves": True}),
    ("armature", "callistemon", {"showLeaves": True, "useArm": True}),
    ("armature_step", "quaking_aspen", {"showLeaves": True, "useArm": True, "boneStep": (2, 2, 1, 1)}),
    ("wind", "quaking_aspen", {"showLeaves": True, "useArm": True, "armAnim": True}),
    ("wind_leaves", "quaking_aspen", {"showLeaves": True, "useArm": True, "armAnim": True, "leafAnim": True}),
    ("wind_loop", "quaking_aspen", {"useArm": True, "armAnim": True, "loopFrames": 48}),
    ("skin_mesh", "quaking_aspen", {"showLeaves": True, "useArm": True, "makeMesh": True}),
    (
        "prune_armature_wind",
        "quaking_aspen",
        {"prune": True, "showLeaves": True, "useArm": True, "armAnim": True, "leafAnim": True},
    ),
]
