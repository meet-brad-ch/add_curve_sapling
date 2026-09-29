# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind animation: procedural F-curve modifiers on the rotation of branch and leaf bones."""

from math import radians

import bpy

from ..model.geometry import Angles


class WindModel:
    """The wind's numbers for one tree: sway frequencies and amplitudes, leaf flutter."""

    def __init__(self, params, fps):
        self.params = params
        self.anim_speed = (24 / fps) * params.frame_rate
        if params.loop_frames == 0:
            self.gust_frequency = params.gust_f * (Angles.TAU / fps) * params.frame_rate
        else:
            self.gust_frequency = 1 / (params.loop_frames / Angles.TAU)

    def branch_frequencies(self, spline_length):
        """The two wind frequencies of a branch: slower for long branches, whole cycles when looping."""
        p = self.params
        multiplier = (1 / max(spline_length**0.5, 1e-6)) * (1 / 4)
        freq1 = multiplier * self.anim_speed
        freq2 = 0.7 * multiplier * self.anim_speed
        if p.loop_frames != 0:
            loop = 1 / (p.loop_frames / Angles.TAU)
            freq1 = max(1, round(freq1 / loop)) * loop
            freq2 = max(1, round(freq2 / loop)) * loop
        return freq1, freq2

    def branch_amplitudes(self, points, n, tail, step, spline_length):
        """Sway amplitudes (radians) of the bone from point n to point tail: stronger for thin bones far up."""
        p = self.params
        segments = len(points) - 1
        a0 = 2 * (spline_length / segments) * (1 - n / (segments + 1)) / max(points[n].radius, 1e-6)
        a0 = a0 * min(step, segments)
        a1 = (p.wind / 50) * a0
        a2 = a1 * 0.65
        direction = points[tail].co - points[n].co
        direction.normalize()
        gust = (p.wind * p.gust / 50) * a0
        a3 = -direction[0] * gust
        a4 = direction[2] * gust
        return (radians(a1), radians(a2), radians(a3), radians(a4))

    def leaf_flutter(self):
        """(strength, noise scale) of the leaves' flutter."""
        p = self.params
        strength, speed, _randomness = p.leaf_wind
        return p.wind * 0.25 * strength, (1 / self.anim_speed) * 6 * (1 / max(speed, 0.001))


class BranchSway:
    """Sway of one branch bone: two wind frequencies plus a slow gust bend, per axis."""

    def __init__(self, amplitudes, offsets, frequencies, gust_frequency):
        self.amplitudes = amplitudes  # (wind 1, wind 2, gust bend on Z, gust bend on X), radians
        self.offsets = offsets  # random phase of the X and Z curves
        self.frequencies = frequencies  # (wind 1, wind 2)
        self.gust_frequency = gust_frequency


class WindAnimator:
    """Adds the sway F-curves to the armature's action."""

    def __init__(self, armature_ob, model):
        self.armature_ob = armature_ob
        self.model = model
        self.loop_frames = model.params.loop_frames
        action = bpy.data.actions.new(name="windAction")
        armature_ob.animation_data_create()
        armature_ob.animation_data.action = action
        self.action = action

    def _rotation_curves(self, bone):
        """The X and Z rotation curves of a bone, grouped under the bone's name (as keyframing does)."""
        path = 'pose.bones["' + bone + '"].rotation_euler'
        ensure = self.action.fcurve_ensure_for_datablock
        return (
            ensure(self.armature_ob, path, index=0, group_name=bone),
            ensure(self.armature_ob, path, index=2, group_name=bone),
        )

    def add_branch_sway(self, bone, sway):
        """Sine waves: X and Z each get wind 1 + wind 2 (+ offset phase) and a gust bend."""
        a1, a2, a3, a4 = sway.amplitudes
        x_offset, z_offset = sway.offsets
        freq1, freq2 = sway.frequencies
        sway_x, sway_z = self._rotation_curves(bone)
        for fcurve, offset in ((sway_x, x_offset), (sway_z, z_offset)):
            first = fcurve.modifiers.new(type="FNGENERATOR")
            first.amplitude = a1
            first.phase_offset = offset
            first.phase_multiplier = freq1
            second = fcurve.modifiers.new(type="FNGENERATOR")
            second.amplitude = a2
            second.phase_offset = 0.7 * offset
            second.phase_multiplier = freq2
            second.use_additive = True
        for fcurve, amplitude in ((sway_z, a3), (sway_x, a4)):
            bend = fcurve.modifiers.new(type="FNGENERATOR")
            bend.amplitude = amplitude
            bend.phase_multiplier = sway.gust_frequency
            bend.value_offset = 0.6 * amplitude
            bend.use_additive = True

    def add_leaf_flutter(self, bone, strength, scale, offsets):
        """Noise on X and Z; a keyframe at 0 gives the noise a curve to modify."""
        for fcurve, offset in zip(self._rotation_curves(bone), offsets, strict=True):
            fcurve.keyframe_points.add(1)
            fcurve.keyframe_points[0].co = (0, 0)
            noise = fcurve.modifiers.new(type="NOISE")
            if self.loop_frames != 0:
                noise.use_restricted_range = True
                noise.frame_end = self.loop_frames
                noise.blend_in = 4
                noise.blend_out = 4
            noise.scale = scale
            noise.strength = strength
            noise.offset = offset
