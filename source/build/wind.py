# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig's wind animation (F-curve modifiers on the bones' rotation) and the leaf flutter in Geometry Nodes."""

from collections.abc import Callable
from dataclasses import dataclass
from random import Random

import bpy
import numpy as np
from bpy.types import FCurve, Float2Attribute, FloatVectorAttribute, FModifierFunctionGenerator, NodeTree, Object

from ..model.joints import JointSway
from ..model.leaves import LeafSet
from ..model.wind_model import WindModel
from .node_groups import SharedNodeGroup
from .node_math import NodeMath, SocketSpec


@dataclass(frozen=True, slots=True)
class BranchSway:
    """The sway of one bone: two waves and a gust bend on each of its X and Z axes (radians)."""

    bone: str
    wind1: float
    wind2: float
    gust_z: float  # the gust bend on the bone's Z axis
    gust_x: float  # the gust bend on the bone's X axis
    offset_x: float  # the random phase of the X curve
    offset_z: float  # the random phase of the Z curve
    frequency1: float
    frequency2: float
    gust_frequency: float


class WindAnimator:
    """The rig's wind: sway F-curves on the bones' X and Z rotation, written when the rig is complete.

    Up to CHUNK bones, one action "windAction" is the armature's action, as keyframing makes it. Larger rigs
    split the curves over several actions, each in its own NLA strip: creating an F-curve costs Blender time in
    proportion to the curves already in its action (measured at 30,000 bones: 6.8 s in one action, 0.2 s in 32;
    playback the same).
    """

    # The second wave's phase trails the first by this fraction of the random offset
    SECOND_WAVE_PHASE = 0.7
    # The gust bend oscillates around this fraction of its amplitude (it leans with the wind)
    BEND_LEAN = 0.6
    ACTION = "windAction"
    CHUNK = 1000
    LAST_FRAME = 1_048_574  # Blender's last frame: an NLA strip holds its end value beyond its range

    def __init__(self, armature_ob: Object) -> None:
        self.armature_ob = armature_ob
        self.sways: list[BranchSway] = []

    def add_joints(self, names: list[str], sway: JointSway) -> None:
        """The sway of every joint's bone, in joint order, written by finish()."""
        if len(names) != len(sway.wind1):
            raise RuntimeError(f"{len(names)} bones for the sway of {len(sway.wind1)} joints")
        wind1 = sway.wind1.tolist()
        wind2 = sway.wind2.tolist()
        gust_z = sway.gust_z.tolist()
        gust_x = sway.gust_x.tolist()
        offset_x = sway.offset_x.tolist()
        offset_z = sway.offset_z.tolist()
        frequency1 = sway.frequency1.tolist()
        frequency2 = sway.frequency2.tolist()
        for i, name in enumerate(names):
            self.sways.append(
                BranchSway(
                    bone=name,
                    wind1=wind1[i],
                    wind2=wind2[i],
                    gust_z=gust_z[i],
                    gust_x=gust_x[i],
                    offset_x=offset_x[i],
                    offset_z=offset_z[i],
                    frequency1=frequency1[i],
                    frequency2=frequency2[i],
                    gust_frequency=sway.gust_frequency,
                )
            )

    def finish(self) -> None:
        """Write every bone's F-curves: one action, or one action per CHUNK bones in NLA strips."""
        ob = self.armature_ob
        ob.animation_data_create()
        if len(self.sways) <= self.CHUNK:
            action = bpy.data.actions.new(name=self.ACTION)
            ob.animation_data.action = action  # type: ignore[union-attr]  # created above
            for sway in self.sways:
                self._write(sway, lambda path, index: action.fcurve_ensure_for_datablock(ob, path, index=index))
            return
        for start in range(0, len(self.sways), self.CHUNK):
            self._chunk(self.sways[start : start + self.CHUNK], start // self.CHUNK)

    def _chunk(self, sways: list[BranchSway], number: int) -> None:
        """One action with these bones' curves, played by its own NLA strip."""
        ob = self.armature_ob
        action = bpy.data.actions.new(name=f"{self.ACTION}.{number:03d}")
        slot = action.slots.new(id_type="OBJECT", name=ob.name)
        channelbag = action.layers.new("Wind").strips.new(type="KEYFRAME").channelbags.new(slot)  # type: ignore[attr-defined]  # stub: keyframe strips have channelbags
        for sway in sways:
            self._write(sway, lambda path, index: channelbag.fcurves.new(path, index=index))
        track = ob.animation_data.nla_tracks.new()  # type: ignore[union-attr]  # created by finish()
        track.name = action.name
        strip = track.strips.new(action.name, 0, action)
        strip.action_slot = slot
        # Curves of F-modifiers alone give the action a range of one frame, and the strip would hold its end value
        # from frame 2 on: the strip maps the whole timeline onto the action, frame for frame
        strip.action_frame_end = self.LAST_FRAME
        if strip.frame_start != 0.0 or strip.frame_end != float(self.LAST_FRAME):
            raise RuntimeError(f"the wind strip spans {strip.frame_start}..{strip.frame_end}, not the timeline")

    def _write(self, sway: BranchSway, new_curve: Callable[[str, int], FCurve]) -> None:
        """Sine waves: X and Z each get wind 1 + wind 2 (+ offset phase) and a gust bend.

        The curves are not grouped per bone (as keyframing does): Blender 5.2 takes about 4 times as long to
        create a grouped F-curve (measured at 16,000 bones: 450 against 100 µs).
        """
        path = 'pose.bones["' + sway.bone + '"].rotation_euler'
        sway_x = new_curve(path, 0)
        sway_z = new_curve(path, 2)
        self._waves(sway_x, sway, sway.offset_x)
        self._waves(sway_z, sway, sway.offset_z)
        self._bend(sway_z, sway, sway.gust_z)
        self._bend(sway_x, sway, sway.gust_x)

    def _waves(self, fcurve: FCurve, sway: BranchSway, offset: float) -> None:
        """The two wind waves on one rotation axis, the second trailing the first by SECOND_WAVE_PHASE."""
        first: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
        first.amplitude = sway.wind1
        first.phase_offset = offset
        first.phase_multiplier = sway.frequency1
        second: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
        second.amplitude = sway.wind2
        second.phase_offset = self.SECOND_WAVE_PHASE * offset
        second.phase_multiplier = sway.frequency2
        second.use_additive = True

    def _bend(self, fcurve: FCurve, sway: BranchSway, amplitude: float) -> None:
        """The gust bend on one rotation axis, leaning with the wind."""
        bend: FModifierFunctionGenerator = fcurve.modifiers.new(type="FNGENERATOR")  # type: ignore[assignment]  # stub: new() returns the base class
        bend.amplitude = amplitude
        bend.phase_multiplier = sway.gust_frequency
        bend.value_offset = self.BEND_LEAN * amplitude
        bend.use_additive = True


class LeafFlutter:
    """Leaf flutter on the leaves object, with the rig or with the node wind."""

    @staticmethod
    def add(leaves_ob: Object, leaves: LeafSet, offsets: list[float], model: WindModel) -> None:
        """Per leaf, its sprout point and its two noise offsets as attributes, and the flutter modifier.

        `offsets` holds two random offsets per leaf (X, then Z). The modifier comes first on the leaves: each
        leaf turns about its sprout at rest, then follows its branch (the rig or the node wind).
        """
        size = leaves.verts_per_leaf
        mesh = leaves_ob.data
        pivots = np.repeat(leaves.sprout_co, size, axis=0)
        per_vertex = np.repeat(np.array(offsets, dtype=np.float32).reshape(-1, 2), size, axis=0)
        pivot: FloatVectorAttribute = mesh.attributes.new(LeafFlutterNodes.PIVOT, "FLOAT_VECTOR", "POINT")  # type: ignore[union-attr, assignment]  # leaves are a mesh; stub: new() returns the base class
        pivot.data.foreach_set("vector", pivots.ravel())
        offset: Float2Attribute = mesh.attributes.new(LeafFlutterNodes.OFFSET, "FLOAT2", "POINT")  # type: ignore[union-attr, assignment]  # leaves are a mesh; stub: new() returns the base class
        offset.data.foreach_set("vector", per_vertex.ravel())
        flutter = model.leaf_flutter()
        LeafFlutterNodes.add_modifier(leaves_ob, flutter.strength, flutter.scale, model.params.loop_frames)

    @staticmethod
    def offsets(leaves: LeafSet, randomness: float, rng: Random) -> list[float]:
        """Two random noise offsets per leaf (X, then Z), drawn in leaf order."""
        values: list[float] = []
        for _ in range(leaves.count):
            values += [rng.uniform(-randomness, randomness), rng.uniform(-randomness, randomness)]
        return values


class LeafFlutterNodes:
    """Geometry nodes that turn each leaf about its sprout point with noise over time (Leaf Flutter).

    The turn is the one a leaf bone gave: an upright bone (roll 0) turned by noise about its X and Z axes, which
    are the world X and -Y axes. As in Blender's Noise F-modifier, the angle is (noise((frame - offset) / scale)
    - 0.5) * strength. With Loop Frames it fades in and out over FADE_FRAMES after frame 0 and before the loop
    end, and is zero outside them.
    """

    GROUP = "Sapling Leaf Flutter"
    VERSION = 1
    PIVOT = "leaf_pivot"
    OFFSET = "leaf_flutter_offset"
    FADE_FRAMES = 4.0
    INPUTS = [
        SocketSpec("Strength", "NodeSocketFloat"),
        SocketSpec("Scale", "NodeSocketFloat"),
        SocketSpec("Loop", "NodeSocketBool"),
        SocketSpec("Loop End", "NodeSocketFloat"),
    ]

    @classmethod
    def add_modifier(cls, leaves_ob: Object, strength: float, scale: float, loop_frames: int) -> None:
        """The flutter modifier, first on the leaves (before the Armature modifier)."""
        group = SharedNodeGroup.ensure(cls.GROUP, cls.VERSION, cls._build)
        modifier = SharedNodeGroup.add_modifier(leaves_ob, "Leaf Flutter", group)
        leaves_ob.modifiers.move(len(leaves_ob.modifiers) - 1, 0)
        values = [strength, scale, loop_frames != 0, float(loop_frames)]
        for spec, value in zip(cls.INPUTS, values, strict=True):
            SharedNodeGroup.set_input(modifier, spec.name, value)

    @classmethod
    def _build(cls, group: NodeTree) -> None:
        """Fill the empty group: Set Position turns each vertex about its leaf's pivot by the two noise angles."""
        m = NodeMath(group)
        inputs = m.interface(group, cls.INPUTS)
        frame = m.nodes.new("GeometryNodeInputSceneTime").outputs["Frame"]
        offsets = m.nodes.new("ShaderNodeSeparateXYZ")
        m.link(m.attr(cls.OFFSET, "FLOAT_VECTOR"), offsets.inputs[0])  # a 2D vector reads as (x, y, 0)
        strength = m.math("MULTIPLY", inputs["Strength"], cls._fade(m, inputs, frame))
        scale = inputs["Scale"]
        turn = m.nodes.new("ShaderNodeCombineXYZ")
        m.link(cls._angle(m, frame, offsets.outputs["X"], scale, strength), turn.inputs["X"])
        z_angle = cls._angle(m, frame, offsets.outputs["Y"], scale, strength)
        m.link(m.math("MULTIPLY", z_angle, -1.0), turn.inputs["Y"])  # the bone's Z axis is world -Y

        rotate = m.nodes.new("ShaderNodeVectorRotate")
        rotate.rotation_type = "EULER_XYZ"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(m.position(), rotate.inputs["Vector"])
        m.link(m.attr(cls.PIVOT, "FLOAT_VECTOR"), rotate.inputs["Center"])
        m.link(turn.outputs[0], rotate.inputs["Rotation"])
        moved = m.set_position(inputs["Geometry"], rotate.outputs[0])
        m.link(moved, m.nodes.new("NodeGroupOutput").inputs["Geometry"])

    @staticmethod
    def _angle(m: NodeMath, frame: object, offset: object, scale: object, strength: object) -> object:
        """(noise((frame - offset) / scale) - 0.5) * strength: the angle about one axis."""
        noise = m.nodes.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "1D"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        noise.inputs["Detail"].default_value = 0.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
        m.link(m.math("SUBTRACT", frame, offset), noise.inputs["W"])
        m.link(m.math("DIVIDE", 1.0, scale), noise.inputs["Scale"])
        return m.math("MULTIPLY", m.math("SUBTRACT", noise.outputs["Fac"], 0.5), strength)

    @classmethod
    def _fade(cls, m: NodeMath, inputs: object, frame: object) -> object:
        """1 without a loop; with one, min(frame, loop end - frame) / FADE_FRAMES, clamped to 0..1."""
        to_end = m.math("SUBTRACT", inputs["Loop End"], frame)  # type: ignore[index]  # the Group Input node's outputs
        fade = m.math("DIVIDE", m.math("MINIMUM", frame, to_end), cls.FADE_FRAMES, clamp=True)
        switch = m.nodes.new("GeometryNodeSwitch")
        switch.input_type = "FLOAT"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        m.link(inputs["Loop"], switch.inputs["Switch"])  # type: ignore[index]  # as above
        switch.inputs["False"].default_value = 1.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
        m.link(fade, switch.inputs["True"])
        return switch.outputs[0]
