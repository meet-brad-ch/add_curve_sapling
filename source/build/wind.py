# SPDX-License-Identifier: GPL-3.0-or-later

"""Wind animation: procedural F-curve modifiers on the rotation of branch bones, and leaf flutter in Geometry
Nodes."""

from collections.abc import Callable
from math import radians
from random import Random

import bpy
import numpy as np
from bpy.types import (
    FCurve,
    Float2Attribute,
    FloatVectorAttribute,
    FModifierFunctionGenerator,
    Node,
    NodeSocket,
    NodeTree,
    Object,
    SplineBezierPoints,
)

from ..model.curve_data import FlatPoints
from ..model.geometry import Angles
from ..model.leaves import LeafSet
from ..model.params import TreeParams
from .node_groups import SharedNodeGroup


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

    def branch_frequency_arrays(self, spline_lengths: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """branch_frequencies() for an array of spline lengths."""
        p = self.params
        multiplier = (1 / np.maximum(np.sqrt(np.maximum(spline_lengths, 0.0)), 1e-6)) * (1 / 4)
        freq1 = multiplier * self.anim_speed
        freq2 = self.SECOND_WAVE_FREQUENCY * multiplier * self.anim_speed
        if p.loop_frames != 0:
            loop = 1 / (p.loop_frames / Angles.TAU)
            freq1 = np.maximum(1, np.round(freq1 / loop)) * loop
            freq2 = np.maximum(1, np.round(freq2 / loop)) * loop
        return freq1, freq2

    def branch_amplitudes(
        self, points: SplineBezierPoints | FlatPoints, n: int, tail: int, step: int, spline_length: float
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

    def __init__(self, armature_ob: Object, model: WindModel) -> None:
        self.armature_ob = armature_ob
        self.model = model
        self.loop_frames = model.params.loop_frames
        self.sways: list[tuple[str, BranchSway]] = []

    def add_branch_sway(self, bone: str, sway: BranchSway) -> None:
        """The sway of one bone, written by finish()."""
        self.sways.append((bone, sway))

    def finish(self) -> None:
        """Write every bone's F-curves: one action, or one action per CHUNK bones in NLA strips."""
        ob = self.armature_ob
        ob.animation_data_create()
        if len(self.sways) <= self.CHUNK:
            action = bpy.data.actions.new(name=self.ACTION)
            ob.animation_data.action = action  # type: ignore[union-attr]  # created above
            for bone, sway in self.sways:
                self._write(bone, sway, lambda path, index: action.fcurve_ensure_for_datablock(ob, path, index=index))
            return
        for start in range(0, len(self.sways), self.CHUNK):
            self._chunk(self.sways[start : start + self.CHUNK], start // self.CHUNK)

    def _chunk(self, sways: list[tuple[str, BranchSway]], number: int) -> None:
        """One action with these bones' curves, played by its own NLA strip."""
        ob = self.armature_ob
        action = bpy.data.actions.new(name=f"{self.ACTION}.{number:03d}")
        slot = action.slots.new(id_type="OBJECT", name=ob.name)
        channelbag = action.layers.new("Wind").strips.new(type="KEYFRAME").channelbags.new(slot)  # type: ignore[attr-defined]  # stub: keyframe strips have channelbags
        for bone, sway in sways:
            self._write(bone, sway, lambda path, index: channelbag.fcurves.new(path, index=index))
        track = ob.animation_data.nla_tracks.new()  # type: ignore[union-attr]  # created by finish()
        track.name = action.name
        strip = track.strips.new(action.name, 1, action)
        strip.action_slot = slot

    def _write(self, bone: str, sway: BranchSway, new_curve: Callable[[str, int], FCurve]) -> None:
        """Sine waves: X and Z each get wind 1 + wind 2 (+ offset phase) and a gust bend.

        The curves are not grouped per bone (as keyframing does): Blender 5.2 takes about 4 times as long to
        create a grouped F-curve (measured at 16,000 bones: 450 against 100 µs).
        """
        path = 'pose.bones["' + bone + '"].rotation_euler'
        sway_x, sway_z = new_curve(path, 0), new_curve(path, 2)
        a1, a2, a3, a4 = sway.amplitudes
        x_offset, z_offset = sway.offsets
        freq1, freq2 = sway.frequencies
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
        strength, scale = model.leaf_flutter()
        LeafFlutterNodes.add_modifier(leaves_ob, strength, scale, model.params.loop_frames)

    @staticmethod
    def offsets(leaves: LeafSet, randomness: float, rng: Random) -> list[float]:
        """Two random noise offsets per leaf (X, then Z), drawn in leaf order."""
        values: list[float] = []
        for _ in range(leaves.count):
            values += (rng.uniform(-randomness, randomness), rng.uniform(-randomness, randomness))
        return values


class LeafFlutterNodes:
    """Geometry nodes that turn each leaf about its sprout point with noise over time (Leaf Animation).

    The turn reproduces the leaf bones this replaces: an upright bone (roll 0) turned by noise about its X and
    Z axes, which are the world X and -Y axes. As in Blender's Noise F-modifier, the angle is
    (noise((frame - offset) / scale) - 0.5) * strength. With Loop Frames it fades in and out over FADE_FRAMES
    after frame 0 and before the loop end, and is zero outside them.
    """

    GROUP = "Sapling Leaf Flutter"
    VERSION = 1
    PIVOT = "leaf_pivot"
    OFFSET = "leaf_flutter_offset"
    FADE_FRAMES = 4.0
    INPUTS = (
        ("Strength", "NodeSocketFloat"),
        ("Scale", "NodeSocketFloat"),
        ("Loop", "NodeSocketBool"),
        ("Loop End", "NodeSocketFloat"),
    )

    @classmethod
    def add_modifier(cls, leaves_ob: Object, strength: float, scale: float, loop_frames: int) -> None:
        """The flutter modifier, first on the leaves (before the Armature modifier)."""
        group = SharedNodeGroup.ensure(cls.GROUP, cls.VERSION, cls._build)
        modifier = SharedNodeGroup.add_modifier(leaves_ob, "Leaf Flutter", group)
        leaves_ob.modifiers.move(len(leaves_ob.modifiers) - 1, 0)
        values = (strength, scale, loop_frames != 0, float(loop_frames))
        for (name, _), value in zip(cls.INPUTS, values, strict=True):
            SharedNodeGroup.set_input(modifier, name, value)

    @classmethod
    def _build(cls, group: NodeTree) -> None:
        """Fill the empty group: Set Position turns each vertex about its leaf's pivot by the two noise angles."""
        interface = group.interface
        interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only
        for name, socket_type in cls.INPUTS:
            interface.new_socket(name, in_out="INPUT", socket_type=socket_type)  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only
        interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")  # type: ignore[union-attr, arg-type]  # stub: interface is optional; socket_type is typed as 'DEFAULT' only

        nodes = group.nodes
        links = group.links
        inputs = nodes.new("NodeGroupInput")
        frame = nodes.new("GeometryNodeInputSceneTime").outputs["Frame"]
        offsets = nodes.new("ShaderNodeSeparateXYZ")
        links.new(cls._attribute(group, cls.OFFSET), offsets.inputs[0])
        strength = cls._math(group, "MULTIPLY", inputs.outputs["Strength"], cls._fade(group, inputs, frame))
        scale = inputs.outputs["Scale"]
        turn = nodes.new("ShaderNodeCombineXYZ")
        links.new(cls._angle(group, frame, offsets.outputs["X"], scale, strength), turn.inputs["X"])
        z_angle = cls._angle(group, frame, offsets.outputs["Y"], scale, strength)
        links.new(cls._math(group, "MULTIPLY", z_angle, -1.0), turn.inputs["Y"])  # the bone's Z axis is world -Y

        rotate = nodes.new("ShaderNodeVectorRotate")
        rotate.rotation_type = "EULER_XYZ"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        links.new(nodes.new("GeometryNodeInputPosition").outputs[0], rotate.inputs["Vector"])
        links.new(cls._attribute(group, cls.PIVOT), rotate.inputs["Center"])
        links.new(turn.outputs[0], rotate.inputs["Rotation"])
        set_position = nodes.new("GeometryNodeSetPosition")
        links.new(inputs.outputs["Geometry"], set_position.inputs["Geometry"])
        links.new(rotate.outputs[0], set_position.inputs["Position"])
        links.new(set_position.outputs["Geometry"], nodes.new("NodeGroupOutput").inputs["Geometry"])

    @classmethod
    def _angle(
        cls, group: NodeTree, frame: NodeSocket, offset: NodeSocket, scale: NodeSocket, strength: NodeSocket
    ) -> NodeSocket:
        """(noise((frame - offset) / scale) - 0.5) * strength: the angle about one axis."""
        noise = group.nodes.new("ShaderNodeTexNoise")
        noise.noise_dimensions = "1D"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        noise.inputs["Detail"].default_value = 0.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
        group.links.new(cls._math(group, "SUBTRACT", frame, offset), noise.inputs["W"])
        group.links.new(cls._math(group, "DIVIDE", 1.0, scale), noise.inputs["Scale"])
        return cls._math(group, "MULTIPLY", cls._math(group, "SUBTRACT", noise.outputs["Fac"], 0.5), strength)

    @classmethod
    def _fade(cls, group: NodeTree, inputs: Node, frame: NodeSocket) -> NodeSocket:
        """1 without a loop; with one, min(frame, loop end - frame) / FADE_FRAMES, clamped to 0..1."""
        to_end = cls._math(group, "SUBTRACT", inputs.outputs["Loop End"], frame)
        fade = cls._math(group, "DIVIDE", cls._math(group, "MINIMUM", frame, to_end), cls.FADE_FRAMES, clamp=True)
        switch = group.nodes.new("GeometryNodeSwitch")
        switch.input_type = "FLOAT"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        group.links.new(inputs.outputs["Loop"], switch.inputs["Switch"])
        switch.inputs["False"].default_value = 1.0  # type: ignore[attr-defined]  # stub: NodeSocket base class
        group.links.new(fade, switch.inputs["True"])
        return switch.outputs[0]

    @staticmethod
    def _attribute(group: NodeTree, name: str) -> NodeSocket:
        """A named vector attribute of the geometry (a 2D vector reads as (x, y, 0))."""
        node = group.nodes.new("GeometryNodeInputNamedAttribute")
        node.data_type = "FLOAT_VECTOR"  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.inputs["Name"].default_value = name  # type: ignore[attr-defined]  # stub: NodeSocket base class
        return node.outputs["Attribute"]

    @staticmethod
    def _math(
        group: NodeTree, operation: str, a: NodeSocket | float, b: NodeSocket | float, clamp: bool = False
    ) -> NodeSocket:
        """A Math node of a and b (sockets are linked, numbers are set); returns its result."""
        node = group.nodes.new("ShaderNodeMath")
        node.operation = operation  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        node.use_clamp = clamp  # type: ignore[attr-defined]  # stub: new() returns the Node base class
        for socket, value in zip(node.inputs, (a, b), strict=False):
            if isinstance(value, float):
                socket.default_value = value  # type: ignore[attr-defined]  # stub: NodeSocket base class
            else:
                group.links.new(value, socket)
        return node.outputs[0]
