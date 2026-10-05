"""Cibles génériques : point de surface, flotte en orbite, astéroïde.

Chaque cible expose ``point(system, t) -> TargetPoint`` (position/vitesse héliocentriques) et
``centers(system, ts)`` (positions approchées pour le balayage grossier des fenêtres).
"""
from dataclasses import dataclass
from typing import Optional

import numpy as np

from .ballistics.kepler2b import propagate
from .constants import GM_SUN
from .solarsystem.rotation import surface_unit_vector


@dataclass
class TargetPoint:
    pos: np.ndarray
    vel: np.ndarray
    normal: Optional[np.ndarray] = None


@dataclass
class SurfaceTarget:
    body: str
    lat: float
    lon: float
    kind: str = "surface"

    def point(self, system, t):
        i = system.index(self.body)
        b = system.bodies[i]
        P, V = system.states(t)
        n = surface_unit_vector(b, t, self.lat, self.lon)
        n2 = surface_unit_vector(b, t + 1.0, self.lat, self.lon)
        return TargetPoint(P[i] + b.radius * n, V[i] + b.radius * (n2 - n), n)

    def centers(self, system, ts):
        return system.planet_states(ts)[0][..., system.index(self.body) - 1, :]

    @property
    def planet(self):
        return self.body


@dataclass
class FleetTarget:
    """Barycentre d'une flotte sur une orbite circulaire autour d'une planète."""
    planet: str
    radius_km: float
    inc_deg: float
    node_deg: float
    phase_deg: float
    kind: str = "fleet"

    def _basis(self):
        i, o = np.radians(self.inc_deg), np.radians(self.node_deg)
        e1 = np.array([np.cos(o), np.sin(o), 0.0])
        e2 = np.array([-np.sin(o) * np.cos(i), np.cos(o) * np.cos(i), np.sin(i)])
        return e1, e2

    def local_state(self, system, t):
        """(position, vitesse) par rapport à la planète."""
        gm = system.get(self.planet).gm
        n = np.sqrt(gm / self.radius_km ** 3)
        th = np.radians(self.phase_deg) + n * t
        e1, e2 = self._basis()
        r = self.radius_km * (np.cos(th) * e1 + np.sin(th) * e2)
        v = self.radius_km * n * (-np.sin(th) * e1 + np.cos(th) * e2)
        return r, v

    def point(self, system, t):
        i = system.index(self.planet)
        P, V = system.states(t)
        r, v = self.local_state(system, t)
        return TargetPoint(P[i] + r, V[i] + v, None)

    def centers(self, system, ts):
        return system.planet_states(ts)[0][..., system.index(self.planet) - 1, :]


@dataclass
class AsteroidTarget:
    t0: float
    r0: np.ndarray
    v0: np.ndarray
    radius_km: float = 0.1
    mass_kg: float = 1e9
    kind: str = "asteroid"

    def point(self, system, t):
        r, v = propagate(self.r0, self.v0, t - self.t0, GM_SUN)
        return TargetPoint(r, v, None)

    def centers(self, system, ts):
        ts = np.asarray(ts, float)
        out = np.empty(ts.shape + (3,))
        for idx in np.ndindex(ts.shape):
            out[idx] = propagate(self.r0, self.v0, ts[idx] - self.t0, GM_SUN)[0]
        return out
