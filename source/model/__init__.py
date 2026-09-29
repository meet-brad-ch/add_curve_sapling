# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree growth model: stems, branching, pruning and leaf geometry.

Stems grow on real Blender curve splines: Blender recalculates bezier handles in C on every point
write and stores values as float32, and the generated trees depend on both.
"""
