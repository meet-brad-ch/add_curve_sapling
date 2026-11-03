# SPDX-License-Identifier: GPL-3.0-or-later

"""The add-on's model alone, without Blender objects: parameters, growth, joints, bone names."""

import random
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from support.addon import Addon


@dataclass(frozen=True)
class BoneIndex:
    """Where a branch bone starts: its spline and point."""

    spline: int
    point: int

    @staticmethod
    def of(name: str) -> "BoneIndex | None":
        """The spline and point a branch bone's name gives (None for a name that is no branch bone's)."""
        if not re.match(r"bone\d{3}\.\d{3}$", name):
            return None
        bone_name = Addon.module("model.stem").BoneName
        return BoneIndex(bone_name.spline(name), bone_name.point(name))


@dataclass(frozen=True)
class GrownModel:
    """A tree grown in the model: its parameters, its curve and what the growth left (bone map, level ends,
    sprouts)."""

    params: Any
    curve: Any
    grown: Any


class Model:
    """The add-on's model alone, without Blender objects: parameters, growth, joints."""

    @staticmethod
    def params(settings: dict) -> Any:
        """The model's TreeParams of these settings (no Blender objects)."""
        return Addon.module("model.params").TreeParams(SimpleNamespace(**settings, leafDupliObj=""))

    @staticmethod
    def wind_params(settings: dict, params: Any) -> Any:
        """The joints' and the wind's WindParams of these settings."""
        return Addon.module("model.params").WindParams(SimpleNamespace(**settings, leafDupliObj=""), params)

    @classmethod
    def grow(cls, settings: dict) -> GrownModel:
        """Grow a tree in the model alone (no Blender objects)."""
        params = cls.params(settings)
        curve = Addon.module("model.curve_data").CurveData()
        grower = Addon.module("model.tree").TreeGrower(params, random.Random(params.seed))
        grown = grower.grow(curve, params.scale)
        return GrownModel(params, curve, grown)

    @classmethod
    def joints(cls, settings: dict, model: GrownModel) -> Any:
        """The Joints of a tree grown in the model alone."""
        wind = cls.wind_params(settings, model.params)
        return Addon.module("model.joints").Joints(wind, model.curve, model.grown)

    @staticmethod
    def record_growth(test: Any) -> list[GrownModel]:
        """Record every tree the generator grows while the test runs (the record is filled as trees grow)."""
        captured: list[GrownModel] = []
        grower = Addon.module("model.tree").TreeGrower
        original = grower.grow

        def recording(grower_self: Any, curve: Any, scale: float) -> Any:
            grown = original(grower_self, curve, scale)
            captured.append(GrownModel(grower_self.params, curve, grown))
            return grown

        grower.grow = recording
        test.addCleanup(setattr, grower, "grow", original)
        return captured
