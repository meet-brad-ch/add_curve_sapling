# SPDX-License-Identifier: GPL-3.0-or-later

"""The armature: one bone per curve segment (or per Bone Step segments), optional leaf bones."""

from contextlib import contextmanager

import bpy
from mathutils import Vector

from ..model.geometry import Angles
from ..model.stem import BoneName
from .wind import BranchSway, WindAnimator, WindModel


class ArmatureBuilder:
    """Builds the armature that deforms the tree curve, the leaves and the skin mesh."""

    ROLE = "treeArm"
    DATA_NAME = "tree"
    MODIFIER = "windSway"
    # Branch bones deform the curve through their envelopes, kept tight around the bone
    BRANCH_ENVELOPE = 0.001
    # Leaf bones (Leaf Animation): short, pointing up from the leaf's sprout
    LEAF_BONE_LENGTH = 0.02

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
        scene = self.context.scene
        fps = scene.render.fps / scene.render.fps_base
        wind = WindAnimator(armature_ob, WindModel(p, fps)) if p.armature_animation else None

        # Curves have no vertex groups: the bone envelopes deform them
        modifier = self.deform(tree, armature_ob, by_envelopes=True)
        modifier.use_apply_on_spline = True
        if p.preview_armature:
            modifier.show_viewport = False
            armature.display_type = "WIRE"
            tree.hide_viewport = True
        if leaves_ob:
            self.deform(leaves_ob, armature_ob, by_envelopes=False)

        with self._editing(armature_ob):
            self._branch_bones(armature, tree.data, grown, wind)
            if leaves_ob:
                self._leaf_bones(armature, grown, leaves, leaves_ob, wind)

        for pose_bone in armature_ob.pose.bones:
            pose_bone.rotation_mode = "XYZ"
        tree.parent = armature_ob
        return armature_ob

    @classmethod
    def deform(cls, ob, armature_ob, by_envelopes):
        """An Armature modifier on ob: by bone envelopes, or by the vertex groups named after the bones."""
        modifier = ob.modifiers.new(cls.MODIFIER, "ARMATURE")
        modifier.object = armature_ob
        modifier.use_bone_envelopes = by_envelopes
        modifier.use_vertex_groups = not by_envelopes
        return modifier

    @staticmethod
    def preview_with_skin_mesh(armature_ob):
        """Fast Preview with Make Mesh: the skin mesh shows the tree, so the armature is hidden."""
        armature_ob.hide_viewport = True
        armature_ob.data.display_type = "STICK"

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

    def _branch_bones(self, armature, curve, grown, wind):
        p = self.params
        rng = self.rng
        for i, link in enumerate(grown.bone_map):
            # Make Mesh simplifies the armature: deeper levels use their parent's bones
            if p.make_mesh and i >= grown.level_ends[p.bone_levels]:
                continue
            spline = curve.splines[i]
            points = spline.bezier_points
            segments = len(points) - 1
            step = p.bone_step[grown.level_of(i)]

            if wind:
                spline_length = segments * ((points[0].co - points[1].co).length)
                offsets = (rng.uniform(0, Angles.TAU), rng.uniform(0, Angles.TAU))
                frequencies = wind.model.branch_frequencies(spline_length)

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
                bone.envelope_distance = self.BRANCH_ENVELOPE
                if n == 0:
                    # the first bone hangs from the bone of the parent branch
                    if link.bone:
                        bone.parent = armature.edit_bones[link.bone]
                else:
                    bone.parent = previous
                    bone.use_connect = True

                if wind:
                    sway = wind.model.branch_amplitudes(points, n, tail, step, spline_length)
                    # the first two trunk bones hold the tree base still
                    if (i == 0) and (n <= step):
                        sway = (0, 0, 0, 0)
                    wind.add_branch_sway(name, BranchSway(sway, offsets, frequencies, wind.model.gust_frequency))

    def _leaf_bones(self, armature, grown, leaves, leaves_ob, wind):
        """Leaves follow the nearest existing branch bone; with Leaf Animation each gets its own bone."""
        p = self.params
        rng = self.rng
        bones = set(armature.edit_bones.keys())
        bone_names = grown.bone_map.bones()
        size = leaves.verts_per_leaf
        step = p.leaf_bone_step
        groups = {}
        for i, sprout in enumerate(leaves.sprouts):
            parent = BoneName.rounded(sprout.parent_bone, step)
            while parent not in bones:
                parent = bone_names[BoneName.spline(parent)]

            if p.leaf_animation:
                name = BoneName.leaf(i)
                bone = armature.edit_bones.new(name)
                bone.head = sprout.co
                bone.tail = sprout.co + Vector((0, 0, self.LEAF_BONE_LENGTH))
                bone.envelope_distance = 0.0
                bone.parent = armature.edit_bones[parent]
                groups[name] = list(range(size * i, size * i + size))

                if wind:
                    strength, scale = wind.model.leaf_flutter()
                    randomness = p.leaf_wind[2]
                    offsets = (rng.uniform(-randomness, randomness), rng.uniform(-randomness, randomness))
                    wind.add_leaf_flutter(name, strength, scale, offsets)
            else:
                groups.setdefault(parent, []).extend(range(size * i, size * i + size))

        for name, indices in groups.items():
            leaves_ob.vertex_groups.new(name=name).add(indices, 1.0, "ADD")
