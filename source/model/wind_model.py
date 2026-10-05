# SPDX-License-Identifier: GPL-3.0-or-later

"""The wind's numbers for one tree: how fast the branches sway, how the gust bends them, how the leaves flutter.

The rig's F-curves and the node wind's attributes both take their numbers from here, through Joints.sway().
"""

from dataclasses import dataclass

from .geometry import Angles
from .params import WindParams


@dataclass(frozen=True, slots=True)
class Frequencies:
    """The two wind frequencies of a branch: the first wave, and the slower second one."""

    first: float
    second: float


@dataclass(frozen=True, slots=True)
class FlutterStrength:
    """How much the leaves flutter, and the time scale of their noise."""

    strength: float
    scale: float


class WindModel:
    """Sway frequencies and leaf flutter from the wind settings and the scene's frame rate."""

    # Each branch sways with two waves; the second is slower and weaker
    SECOND_WAVE_FREQUENCY = 0.7
    SECOND_WAVE_AMPLITUDE = 0.65
    # Leaf flutter strength per unit of Overall Wind Strength
    LEAF_STRENGTH = 0.25

    def __init__(self, params: WindParams, fps: float) -> None:
        self.params = params
        self.anim_speed = (24 / fps) * params.animation_speed
        if params.loop_frames == 0:
            self.gust_frequency = params.gust_f * (Angles.TAU / fps) * params.animation_speed
        else:
            self.gust_frequency = 1 / (params.loop_frames / Angles.TAU)

    def branch_frequencies(self, spline_length: float) -> Frequencies:
        """The two wind frequencies of a branch: slower for long branches, whole cycles when looping."""
        p = self.params
        multiplier = (1 / max(spline_length**0.5, 1e-6)) * (1 / 4)
        freq1 = multiplier * self.anim_speed
        freq2 = self.SECOND_WAVE_FREQUENCY * multiplier * self.anim_speed
        if p.loop_frames != 0:
            loop = 1 / (p.loop_frames / Angles.TAU)
            freq1 = max(1, round(freq1 / loop)) * loop
            freq2 = max(1, round(freq2 / loop)) * loop
        return Frequencies(freq1, freq2)

    def leaf_flutter(self) -> FlutterStrength:
        """The leaves' flutter strength and noise scale."""
        p = self.params
        flutter = p.flutter
        strength = p.wind * self.LEAF_STRENGTH * flutter.strength
        return FlutterStrength(strength, (1 / self.anim_speed) * 6 * (1 / max(flutter.speed, 0.001)))
