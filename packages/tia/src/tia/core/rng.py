"""Randomness.

All randomness is explicit and seeded. There is no module-level ``random`` use anywhere
in the package: an experiment that cannot be reproduced from its recorded seed is not
evidence of anything.

Each consumer derives its own stream from the run seed via a stable name, so adding a new
consumer never perturbs the draws of existing ones — a subtle but important property when
comparing two runs that differ by one component.
"""

from __future__ import annotations

import hashlib

import numpy as np


def derive_seed(root_seed: int, stream_name: str) -> int:
    """Derive a stable 63-bit sub-seed for a named stream."""
    payload = f"{root_seed}:{stream_name}".encode()
    digest = hashlib.blake2s(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") & ((1 << 63) - 1)


class RngRegistry:
    """Hands out independent, reproducible generators keyed by stream name."""

    __slots__ = ("_root_seed", "_streams")

    def __init__(self, root_seed: int) -> None:
        self._root_seed = int(root_seed)
        self._streams: dict[str, np.random.Generator] = {}

    @property
    def root_seed(self) -> int:
        return self._root_seed

    def get(self, stream_name: str) -> np.random.Generator:
        rng = self._streams.get(stream_name)
        if rng is None:
            rng = np.random.default_rng(derive_seed(self._root_seed, stream_name))
            self._streams[stream_name] = rng
        return rng

    def reset(self) -> None:
        """Drop all derived streams so the registry replays identically."""
        self._streams.clear()

    def describe(self) -> dict[str, int]:
        """Seeds actually used, for the experiment record."""
        return {name: derive_seed(self._root_seed, name) for name in sorted(self._streams)}


__all__ = ["RngRegistry", "derive_seed"]
