# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind animation: procedural F-curve modifiers on the rotation of branch and leaf bones."""

from math import radians

import bpy
from bpy.types import FCurve, FModifierFunctionGenerator, FModifierNoise, Object, SplineBezierPoints

from ..model.geometry import Angles
from ..model.params import TreeParams


class WindModel:
    """The wind's numbers for one tree: sway frequencies and amplitudes, leaf flutter."""

    # Each branch sways with two waves; the second is slower and weaker
    SECOND_WAVE_FREQUENCY = 0.7
    SECOND_WAVE_AMPLITUDE = 0.65
    # Leaf flutter strength per unit of Overall Wind Strength
    LEAF_STRENGTH = 0.25

    def __init__(self, params: TreeParams, fps: float) -> None:
        self.params = params
        self.anim_speed = (24 / fps) * params.frame_rate
        if params.loop_frames == 0:
            self.gust_frequency = params.gust_f * (Angles.TAU / fps) * params.frame_rate
        else:
            self.gust_frequency = 1 / (params.loop_frames / Angles.TAU)

    def branch_frequencies(self, spline_length: float) -> tuple[float, float]:
        """The two wind frequencies of a branch: slower for long branches, whole cycles when looping."""
        p = self.params
        multiplier = (1 / max(spline_length**0.5, 1e-6)) * (1 / 4)
        freq1 = multiplier * self.anim_speed
        freq2 = self.SECOND_WAVE_FREQUENCY * multiplier * self.anim_speed
        if p.loop_frames != 0:
            loop = 1 / (p.loop_frames / Angles.TAU)
            freq1 = max(1, round(freq1 / loop)) * loop
            freq2 = max(1, round(freq2 / loop)) * loop
        return freq1, freq2

    def branch_amplitudes(
        self, points: SplineBezierPoints, n: int, tail: int, step: int, spline_length: float
    ) -> tuple[float, float, float, float]:
        """Sway amplitudes (radians) of the bone from point n to point tail: stronger for thin bones far up."""
        p = self.params
        segments = len(points) - 1
        a0 = 2 * (spline_length / segments) * (1 - n / (segments + 1)) / max(points[n].radius, 1e-6)
        a0 = a0 * min(step, segments)
        a1 = (p.wind / 50) * a0
        a2 = a1 * self.SECOND_WAVE_AMPLITUDE
        direction = points[tail].co - points[n].co
        direction.normalize()
        gust = (p.wind * p.gust / 50) * a0
        a3 = -direction[0] * gust
        a4 = direction[2] * gust
        return (radians(a1), radians(a2), radians(a3), radians(a4))

    def leaf_flutter(self) -> tuple[float, float]:
        """(strength, noise scale) of the leaves' flutter."""
        p = self.params
        strength, speed, _randomness = p.leaf_wind
        return p.wind * self.LEAF_STRENGTH * strength, (1 / self.anim_speed) * 6 * (1 / max(speed, 0.001))


class BranchSway:
    """Sway of one branch bone: two wind frequencies plus a slow gust bend, per axis."""

    def __init__(
        self,
        amplitudes: tuple[float, float, float, float],
        offsets: tuple[float, float],
        frequencies: tuple[float, float],
        gust_frequency: float,
    ) -> None:
        self.amplitudes = amplitudes  # (wind 1, wind 2, gust bend on Z, gust bend on X), radians
        self.offsets = offsets  # random phase of the X and Z curves
        self.frequencies = frequencies  # (wind 1, wind 2)
        self.gust_frequency = gust_frequency


class WindAnimator:
    """Adds the sway F-curves to the armature's action."""

    # The second wave's phase trails the first by this fraction of the random offset
    SECOND_WAVE_PHASE = 0.7
    # The gust bend oscillates around this fraction of its amplitude (it leans with the wind)
    BEND_LEAN = 0.6

    def __init__(self, armature_ob: Object, model: WindModel) -> None:
        self.armature_ob = armature_ob
        self.model = model
        self.loop_frames = model.params.loop_frames
        action = bpy.data.actions.new(name="windAction")
        armature_ob.animation_data_create()
        armature_ob.animation_data.action = action  # type: ignore[union-attr]  # created on the line above
        self.action = action

    def _rotation_curves(self, bone: str) -> tuple[FCurve, FCurve]:
        """The X and Z rotation curves of a bone.

        Not grouped per bone (as keyframing does): Blender 5.2 takes about 4 times as long to create a grouped
        F-curve, and both costs grow with the number of curves (measured at 16,000 bones: 450 against 100 µs).
        """
        path = 'pose.bones["' + bone + '"].rotation_euler'
        ensure = self.action.fcurve_ensure_for_datablock
        return ensure(self.armature_ob, path, index=0), ensure(self.armature_ob, path, index=2)

    def add_branch_sway(self, bone: str, sway: BranchSway) -> None:
        """Sine waves: X and Z each get wind 1 + wind 2 (+ offset phase) and a gust bend."""
        a1, a2, a3, a4 = sway.amplitudes
        x_offset, z_offset = sway.offsets
        freq1, freq2 = sway.frequencies
        sway_x, sway_z = self._rotation_curves(bone)
        for fcurve, offset in ((sway_x, x_offset), (sway_z, z_offset)):
            first: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
            first.amplitude = a1
            first.phase_offset = offset
            first.phase_multiplier = freq1
            second: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
            second.amplitude = a2
            second.phase_offset = self.SECOND_WAVE_PHASE * offset
            second.phase_multiplier = freq2
            second.use_additive = True
        for fcurve, amplitude in ((sway_z, a3), (sway_x, a4)):
            bend: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
            bend.amplitude = amplitude
            bend.phase_multiplier = sway.gust_frequency
            bend.value_offset = self.BEND_LEAN * amplitude
            bend.use_additive = True

    def add_leaf_flutter(self, bone: str, strength: float, scale: float, offsets: tuple[float, float]) -> None:
        """Noise on X and Z; a keyframe at 0 gives the noise a curve to modify."""
        for fcurve, offset in zip(self._rotation_curves(bone), offsets, strict=True):
            fcurve.keyframe_points.add(1)
            fcurve.keyframe_points[0].co = (0, 0)
            noise: FModifierNoise = fcurve.modifiers.new(type="NOISE")  # type: ignore[assignment]  # stub: new() returns the base class
            if self.loop_frames != 0:
                noise.use_restricted_range = True
                noise.frame_end = self.loop_frames
                noise.blend_in = 4
                noise.blend_out = 4
            noise.scale = scale
            noise.strength = strength
            noise.offset = offset
