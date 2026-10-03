# SPDX-License-Identifier: GPL-3.0-or-later

"""Tree growth model: stems, branching, pruning and leaf geometry.

Stems grow on an in-memory curve (CurveData) that reproduces Blender's bezier handle recalculation and
float32 storage to the bit: the generated trees depend on both. The model uses no Blender data (bpy).
"""
