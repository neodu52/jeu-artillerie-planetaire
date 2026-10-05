"""Géométrie de rayons : boîtes orientées (composants de vaisseaux) et sphères (planètes)."""
import numpy as np


def ray_box(origin, direction, center, axes, half):
    """Intersection rayon / boîte orientée. ``axes`` : colonnes = axes de la boîte (monde).

    Retourne (t_entrée, t_sortie) en km le long de ``direction`` (unitaire) ou None.
    """
    o = axes.T @ (np.asarray(origin) - center)
    d = axes.T @ np.asarray(direction)
    tmin, tmax = -np.inf, np.inf
    for k in range(3):
        if abs(d[k]) < 1e-18:
            if abs(o[k]) > half[k]:
                return None
            continue
        t1, t2 = (-half[k] - o[k]) / d[k], (half[k] - o[k]) / d[k]
        if t1 > t2:
            t1, t2 = t2, t1
        tmin, tmax = max(tmin, t1), min(tmax, t2)
        if tmin > tmax:
            return None
    if tmax < 0:
        return None
    return float(tmin), float(tmax)


def segment_hits_sphere(a, b, center, radius) -> bool:
    """Le segment [a, b] traverse-t-il la sphère ?"""
    a, b, c = np.asarray(a), np.asarray(b), np.asarray(center)
    ab = b - a
    t = np.clip(((c - a) @ ab) / (ab @ ab), 0.0, 1.0)
    return bool(np.linalg.norm(a + t * ab - c) < radius)
