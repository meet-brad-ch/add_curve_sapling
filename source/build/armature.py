# SPDX-License-Identifier: GPL-3.0-or-later

"""The armature: one bone per curve segment (or per Bone Step segments), optional leaf bones."""

from contextlib import contextmanager
from math import radians

import bpy
from mathutils import Vector

from ..model.geometry import Angles
from ..model.stem import BoneName
from .wind import BranchSway, WindAnimator


class ArmatureBuilder:
    """Builds the armature that deforms the tree curve, the leaves and the skin mesh."""

    ROLE = "treeArm"
    DATA_NAME = "tree"

    def __init__(self, params, rng, objects, context):
        self.params = params
        self.rng = rng
        self.objects = objects
        self.context = context

    def build(self, tree, grown, leaves, leaves_ob):
        p = self.params
        armature = bpy.data.armatures.new(self.DATA_NAME)
        armature_ob = self.objects.new(self.ROLE, armature)
        armature.display_type = "STICK"
        wind = WindAnimator(armature_ob, p.loop_frames) if p.armature_animation else None

        modifier = tree.modifiers.new("windSway", "ARMATURE")
        if p.preview_armature:
            modifier.show_viewport = False
            armature.display_type = "WIRE"
            tree.hide_viewport = True
        modifier.use_apply_on_spline = True
        modifier.object = armature_ob
        modifier.use_bone_envelopes = True
        modifier.use_vertex_groups = False  # curves have no vertex groups
        if leaves_ob:
            modifier = leaves_ob.modifiers.new("windSway", "ARMATURE")
            modifier.object = armature_ob
            modifier.use_bone_envelopes = False
            modifier.use_vertex_groups = True

        scene = self.context.scene
        fps = scene.render.fps / scene.render.fps_base
        with self._editing(armature_ob):
            self._branch_bones(armature, tree.data, grown, wind, fps)
            if leaves_ob:
                self._leaf_bones(armature, grown, leaves, leaves_ob, wind, fps)

        for pose_bone in armature_ob.pose.bones:
            pose_bone.rotation_mode = "XYZ"
        tree.parent = armature_ob
        if wind:
            wind.finish()
        return armature_ob

    @contextmanager
    def _editing(self, armature_ob):
        """Edit mode on the new armature alone; the selection and active object are restored after.

        mode_set works on the view layer's selection (a context override does not change that), so every
        other selected armature would enter edit mode too; the new armature is made the only selection.
        """
        objects = self.context.view_layer.objects
        previous_active = objects.active
        previous_selection = [ob for ob in objects if ob.select_get()]
        for ob in previous_selection:
            ob.select_set(False)
        armature_ob.select_set(True)
        objects.active = armature_ob
        try:
            self._switch_mode("EDIT")
            try:
                yield
            finally:
                self._switch_mode("OBJECT")
        finally:
            armature_ob.select_set(False)
            for ob in previous_selection:
                ob.select_set(True)
            objects.active = previous_active

    @staticmethod
    def _switch_mode(mode):
        if bpy.ops.object.mode_set(mode=mode) != {"FINISHED"}:
            raise RuntimeError(f"Could not switch the new armature to {mode} mode")

    def armature_level_end(self, grown):
        """Splines below this index get their own bones when the skin mesh simplifies the armature."""
        return grown.level_ends[self.bone_levels()]

    def bone_levels(self):
        """Index of the last level that gets its own bones; -1 when every level does (Armature Levels 0)."""
        return min(self.params.armature_levels, self.params.levels) - 1

    def leaf_bone_step(self):
        """Bone Step of the level whose bones the leaves hang from (at most the 4th parameter level)."""
        level = self.bone_levels()
        if level == -1:
            level = self.params.levels - 1
        return self.params.bone_step[min(level, 3)]

    def _branch_bones(self, armature, curve, grown, wind, fps):
        p = self.params
        rng = self.rng
        bone_levels = self.bone_levels()
        anim_speed = (24 / fps) * p.frame_rate
        for i, link in enumerate(grown.bone_map):
            if not ((i < grown.level_ends[bone_levels]) or (bone_levels == -1) or (not p.make_mesh)):
                continue
            spline = curve.splines[i]
            points = spline.bezier_points
            segments = len(points) - 1
            step = p.bone_step[grown.level_of(i)]

            if wind:
                spline_length = segments * ((points[0].co - points[1].co).length)
                x_offset = rng.uniform(0, Angles.TAU)
                y_offset = rng.uniform(0, Angles.TAU)
                multiplier = (1 / max(spline_length**0.5, 1e-6)) * (1 / 4)
                freq1 = multiplier * anim_speed
                freq2 = 0.7 * multiplier * anim_speed
                if p.loop_frames != 0:
                    loop = 1 / (p.loop_frames / Angles.TAU)
                    freq1 = max(1, round(freq1 / loop)) * loop
                    freq2 = max(1, round(freq2 / loop)) * loop

            bone = None
            tail = 0
            for n in range(0, segments, step):
                previous = bone
                name = BoneName.of(i, n)
                bone = armature.edit_bones.new(name)
                bone.head = points[n].co
                tail = min(tail + step, segments)
                bone.tail = points[tail].co
                bone.head_radius = points[n].radius
                bone.tail_radius = points[tail].radius
                bone.envelope_distance = 0.001
                if n == 0:
                    # the first bone hangs from the bone of the parent branch
                    if link.bone:
                        bone.parent = armature.edit_bones[link.bone]
                else:
                    bone.parent = previous
                    bone.use_connect = True

                if wind:
                    sway = self._branch_sway(points, segments, n, tail, step, spline_length, fps)
                    # the first two trunk bones hold the tree base still
                    if (i == 0) and (n <= step):
                        sway = (0, 0, 0, 0)
                    wind.add_branch_sway(
                        name, BranchSway(sway, (x_offset, y_offset), (freq1, freq2), self._gust_frequency(fps))
                    )

    def _branch_sway(self, points, segments, n, tail, step, spline_length, fps):
        """Sway amplitudes (radians) of one bone: stronger for thin bones far up the branch."""
        p = self.params
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

    def _gust_frequency(self, fps):
        p = self.params
        if p.loop_frames == 0:
            return p.gust_f * (Angles.TAU / fps) * p.frame_rate
        return 1 / (p.loop_frames / Angles.TAU)

    def _leaf_bones(self, armature, grown, leaves, leaves_ob, wind, fps):
        """Leaves follow the nearest existing branch bone; with Leaf Animation each gets its own bone."""
        p = self.params
        rng = self.rng
        bones = set(armature.edit_bones.keys())
        bone_names = grown.bone_map.bones()
        size = leaves.verts_per_leaf
        anim_speed = (24 / fps) * p.frame_rate
        groups = {}
        for i, sprout in enumerate(leaves.sprouts):
            parent = BoneName.rounded(sprout.parent_bone, self.leaf_bone_step())
            while parent not in bones:
                parent = bone_names[BoneName.spline(parent)]

            if p.leaf_animation:
                name = "leaf" + str(i)
                bone = armature.edit_bones.new(name)
                bone.head = sprout.co
                bone.tail = sprout.co + Vector((0, 0, 0.02))
                bone.envelope_distance = 0.0
                bone.parent = armature.edit_bones[parent]
                groups[name] = list(range(size * i, size * i + size))

                if wind:
                    strength, speed, offset = p.leaf_wind
                    scale = (1 / anim_speed) * 6 * (1 / max(speed, 0.001))
                    offsets = (rng.uniform(-offset, offset), rng.uniform(-offset, offset))
                    wind.add_leaf_flutter(name, p.wind * 0.25 * strength, scale, offsets)
            else:
                groups.setdefault(parent, []).extend(range(size * i, size * i + size))

        for name, indices in groups.items():
            leaves_ob.vertex_groups.new(name=name).add(indices, 1.0, "ADD")
