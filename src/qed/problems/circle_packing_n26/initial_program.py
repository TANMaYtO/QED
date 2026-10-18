"""Initial program for circle packing (n=26).

Adapted from OpenEvolve circle packing example:
https://github.com/algorithmicsuperintelligence/openevolve
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
"""

import numpy as np

# EVOLVE-BLOCK-START
"""Constructor-based circle packing for n=26 circles."""


def compute_max_radii(centers: np.ndarray) -> np.ndarray:
    """Compute maximum valid radii for circles inside unit square without overlap."""
    n: int = centers.shape[0]
    radii: np.ndarray = np.ones(n, dtype=float)

    # First, limit by distance to unit square boundaries [0, 1]^2
    for i in range(n):
        x, y = float(centers[i, 0]), float(centers[i, 1])
        radii[i] = min(x, y, 1.0 - x, 1.0 - y)

    # Limit by distance to other circles to prevent overlap
    for i in range(n):
        for j in range(i + 1, n):
            dist: float = float(np.sqrt(np.sum((centers[i] - centers[j]) ** 2)))
            if radii[i] + radii[j] > dist:
                if radii[i] + radii[j] > 0.0:
                    scale: float = dist / (radii[i] + radii[j])
                    radii[i] *= scale
                    radii[j] *= scale
                else:
                    radii[i] = 0.0
                    radii[j] = 0.0

    return radii


def construct_packing() -> tuple[np.ndarray, np.ndarray, float]:
    """Construct a ring-based geometric arrangement of 26 circles in a unit square."""
    n: int = 26
    centers: np.ndarray = np.zeros((n, 2), dtype=float)

    # Place center circle
    centers[0] = [0.5, 0.5]

    # Inner ring of 8 circles
    for i in range(8):
        angle: float = 2.0 * np.pi * float(i) / 8.0
        centers[i + 1] = [
            0.5 + 0.3 * np.cos(angle),
            0.5 + 0.3 * np.sin(angle),
        ]

    # Outer ring of 16 circles
    for i in range(16):
        angle: float = 2.0 * np.pi * float(i) / 16.0
        centers[i + 9] = [
            0.5 + 0.7 * np.cos(angle),
            0.5 + 0.7 * np.sin(angle),
        ]

    # Ensure all circle centers fall strictly inside unit square
    centers = np.clip(centers, 0.01, 0.99)
    radii: np.ndarray = compute_max_radii(centers)
    sum_radii: float = float(np.sum(radii))

    return centers, radii, sum_radii


# EVOLVE-BLOCK-END


def run_packing() -> tuple[np.ndarray, np.ndarray, float]:
    """Execute the circle packing constructor and return centers, radii, and score."""
    centers, radii, sum_radii = construct_packing()
    return centers, radii, sum_radii


if __name__ == "__main__":
    centers_out, radii_out, total_radius = run_packing()
    print(f"Sum of radii: {total_radius:.6f}")
