# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind animation: procedural F-curve modifiers on the rotation of branch and leaf bones."""

import bpy


class BranchSway:
    """Sway of one branch bone: two wind frequencies plus a slow gust bend, per axis."""

    def __init__(self, amplitudes, offsets, frequencies, gust_frequency):
        self.amplitudes = amplitudes  # (wind 1, wind 2, gust bend x, gust bend y), radians
        self.offsets = offsets  # random phase per axis
        self.frequencies = frequencies  # (wind 1, wind 2)
        self.gust_frequency = gust_frequency


class WindAnimator:
    """Adds the sway F-curves to the armature's action."""

    def __init__(self, armature_ob, loop_frames):
        self.armature_ob = armature_ob
        self.loop_frames = loop_frames
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
        x_offset, y_offset = sway.offsets
        freq1, freq2 = sway.frequencies
        sway_x, sway_y = self._rotation_curves(bone)
        for fcurve, offset in ((sway_x, x_offset), (sway_y, y_offset)):
            first = fcurve.modifiers.new(type="FNGENERATOR")
            first.amplitude = a1
            first.phase_offset = offset
            first.phase_multiplier = freq1
            second = fcurve.modifiers.new(type="FNGENERATOR")
            second.amplitude = a2
            second.phase_offset = 0.7 * offset
            second.phase_multiplier = freq2
            second.use_additive = True
        for fcurve, amplitude in ((sway_y, a3), (sway_x, a4)):
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
