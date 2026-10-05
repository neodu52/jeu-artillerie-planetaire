"""Le canon de Gauss en orbite circulaire autour de Saturne."""
from dataclasses import dataclass

import numpy as np

from ..constants import C_KMS
from ..solarsystem.rotation import pole_vector
from ..solarsystem.system import SolarSystem

V_MAX_KMS = C_KMS * (1.0 - 1e-9)   # vitesse de bouche max : tout juste sous c
E_MAX_J = 1.0e16           # énergie maximale par tir (~2,4 Mt TNT)
CANNON_MASS_KG = 2.0e9     # masse de la station (pour le recul)


def add_velocity(V, u):
    """Composition relativiste : u (vitesse mesurée dans le repère de la station, qui se déplace
    à V) vue du repère héliocentrique."""
    V, u = np.asarray(V, float), np.asarray(u, float)
    c2 = C_KMS ** 2
    g = 1.0 / np.sqrt(1.0 - (V @ V) / c2)
    vu = (V @ u) / c2
    return (u / g + V + (g / (1.0 + g)) * vu * V) / (1.0 + vu)


def direction_vector(lon_deg: float, lat_deg: float) -> np.ndarray:
    """Direction de tir dans le repère écliptique (longitude, latitude écliptiques)."""
    lo, la = np.radians(lon_deg), np.radians(lat_deg)
    return np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])


def direction_angles(vec: np.ndarray):
    v = vec / np.linalg.norm(vec)
    return float(np.degrees(np.arctan2(v[1], v[0])) % 360.0), float(np.degrees(np.arcsin(np.clip(v[2], -1, 1))))


@dataclass
class CannonState:
    r_rel: np.ndarray      # position relative à Saturne (km)
    v_rel: np.ndarray      # vitesse relative à Saturne (km/s)
    r_helio: np.ndarray
    v_helio: np.ndarray


class GaussCannon:
    """Station circulaire dans le plan équatorial de Saturne."""

    def __init__(self, system: SolarSystem, orbit_radius_km: float = 300_000.0, phase0_deg: float = 0.0):
        self.system = system
        self.saturn = system.get("Saturne")
        self.radius_km = orbit_radius_km
        self.phase0 = np.radians(phase0_deg)
        self.mu = self.saturn.gm
        self.n = np.sqrt(self.mu / orbit_radius_km ** 3)          # rad/s
        self.speed_kms = np.sqrt(self.mu / orbit_radius_km)
        pole = pole_vector(self.saturn)
        node = np.cross([0.0, 0.0, 1.0], pole)
        self.e1 = node / np.linalg.norm(node)
        self.e2 = np.cross(pole, self.e1)

    @property
    def period_s(self) -> float:
        return 2 * np.pi / self.n

    def state(self, t: float) -> CannonState:
        th = self.phase0 + self.n * t
        c, s = np.cos(th), np.sin(th)
        r_rel = self.radius_km * (c * self.e1 + s * self.e2)
        v_rel = self.speed_kms * (-s * self.e1 + c * self.e2)
        P, V = self.system.states(t)
        i = self.system.index("Saturne")
        return CannonState(r_rel, v_rel, P[i] + r_rel, V[i] + v_rel)

    def recoil_kms(self, momentum_kg_ms: float) -> float:
        """Recul de la station (km/s) pour une quantité de mouvement donnée."""
        return momentum_kg_ms / CANNON_MASS_KG / 1e3
