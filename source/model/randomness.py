# SPDX-License-Identifier: GPL-3.0-or-later

"""Random numbers from keys, so a whole level draws at once.

Every stem has a lineage key, derived from its parent's key and where it sprouted or split off. A draw is a
hash of (key, step, what is drawn): it depends on nothing else, so pruning or splitting one stem never changes
another stem's numbers, and all stems of a level draw in one array operation. The hash is murmur3's 64-bit
finalizer, bijective, so distinct keys never collide into the same stream.
"""

import numpy as np


class Draw:
    """What a stem draws at a step (the draw ids; a split's own draws go through its own derived key)."""

    SPLIT = 1
    CURVE_ANGLE = 2
    CURVE_VARIATION = 3
    SPLIT_SIGN = 4
    SPLIT_ANGLE = 5
    SPREAD_SIGN = 6
    SPREAD_ANGLE = 7
    ROTATION_START = 8
    ROTATION = 9
    LENGTH = 10  # a split's segment length, drawn with the split's key (which holds the step and the slot)
    BEND = 11
    HELIX_PITCH = 12
    HELIX_RADIUS = 13
    HELIX_SPIN = 14
    JITTER = 20
    DOWN = 21
    ROTATE = 22
    PICK = 23
    RING = 24


class Kind:
    """How a key derives from its parent's: the kind of relation."""

    TRUNK = 1
    CHILD = 2
    SPLIT = 3
    PICK = 4
    RING = 5


class KeyedRandom:
    """uint64 lineage keys and uniform draws from them."""

    M1 = np.uint64(0xFF51AFD7ED558CCD)
    M2 = np.uint64(0xC4CEB9FE1A85EC53)
    GOLDEN = np.uint64(0x9E3779B97F4A7C15)
    SHIFT = np.uint64(33)
    DROP = np.uint64(11)  # keep 53 bits, as random.random does
    SCALE = 2.0**-53
    MASK = (1 << 64) - 1

    @classmethod
    def mix(cls, x: np.ndarray) -> np.ndarray:
        """murmur3 fmix64 on uint64 arrays (multiplication wraps, as intended)."""
        with np.errstate(over="ignore"):
            x = x ^ (x >> cls.SHIFT)
            x = x * cls.M1
            x = x ^ (x >> cls.SHIFT)
            x = x * cls.M2
            return x ^ (x >> cls.SHIFT)

    @classmethod
    def root(cls, seed: int) -> np.ndarray:
        """The tree's key from the Seed setting: a one-element uint64 array."""
        return cls.mix(np.array([seed & cls.MASK], dtype=np.uint64) ^ cls.GOLDEN)

    @classmethod
    def derive(cls, parent: np.ndarray, kind: int, a: np.ndarray | int, b: np.ndarray | int) -> np.ndarray:
        """Keys of the rows related to `parent` by `kind` at (a, b): e.g. the child at (point, position)."""
        with np.errstate(over="ignore"):
            a64 = np.asarray(a, dtype=np.int64).astype(np.uint64) + np.uint64(1)
            b64 = np.asarray(b, dtype=np.int64).astype(np.uint64) + np.uint64(1)
            salted = cls.mix(parent ^ (np.uint64(kind) * cls.GOLDEN))
            return cls.mix(salted + a64 * cls.M1 + b64 * cls.M2)

    @classmethod
    def uniform(cls, keys: np.ndarray, step: int, draw: int) -> np.ndarray:
        """One number in [0, 1) per key for (step, draw), with 53 random bits like random.random()."""
        with np.errstate(over="ignore"):
            salt = cls.mix(np.array([(step << 16) | draw], dtype=np.uint64) * cls.GOLDEN)
            return (cls.mix(keys ^ salt) >> cls.DROP).astype(np.float64) * cls.SCALE

    @classmethod
    def between(
        cls, keys: np.ndarray, step: int, draw: int, low: np.ndarray | float, high: np.ndarray | float
    ) -> np.ndarray:
        """low + (high - low) * uniform, as random.uniform(low, high) computes it."""
        return low + (np.asarray(high) - low) * cls.uniform(keys, step, draw)

    @classmethod
    def sign(cls, keys: np.ndarray, step: int, draw: int) -> np.ndarray:
        """-1.0 or 1.0 per key, as random.choice([-1, 1])."""
        return np.where(cls.uniform(keys, step, draw) < 0.5, -1.0, 1.0)

    @classmethod
    def pick(cls, keys: np.ndarray, step: int, draw: int, counts: np.ndarray) -> np.ndarray:
        """An index in [0, counts) per key, as random.randint(0, counts - 1)."""
        return np.minimum(np.floor(cls.uniform(keys, step, draw) * counts).astype(np.int64), counts - 1)
