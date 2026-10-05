"""Barre de tungstène : géométrie, masse, énergie (relativiste), pénétration."""
import math
from dataclasses import dataclass

from ..constants import C_KMS, C_MS, MT_TNT_J, TUNGSTEN_DENSITY

LENGTH_RANGE_M = (1e-3, 100.0)
RADIUS_RANGE_M = (1e-4, 2.0)


def gamma_minus_1(v_kms: float) -> float:
    """gamma - 1, numériquement stable (tend vers v^2/2c^2 à basse vitesse)."""
    b2 = (v_kms / C_KMS) ** 2
    if b2 >= 1.0:
        raise ValueError("la vitesse doit rester strictement inférieure à c")
    s = math.sqrt(1.0 - b2)
    return b2 / (s * (1.0 + s))


def speed_for_gamma_minus_1(x: float) -> float:
    """Vitesse (km/s) pour gamma - 1 = x."""
    return C_KMS * math.sqrt(x * (x + 2.0)) / (1.0 + x)


def mass_for_energy(energy_j: float, v_kms: float) -> float:
    """Masse (kg) donnant l'énergie cinétique relativiste voulue à cette vitesse."""
    return energy_j / (gamma_minus_1(v_kms) * C_MS ** 2)


def speed_for_energy(energy_j: float, mass_kg: float) -> float:
    return speed_for_gamma_minus_1(energy_j / (mass_kg * C_MS ** 2))


@dataclass
class Rod:
    length_m: float = 10.0
    radius_m: float = 0.30
    density: float = TUNGSTEN_DENSITY

    def validate(self):
        lo, hi = LENGTH_RANGE_M
        if not lo <= self.length_m <= hi:
            raise ValueError(f"longueur hors limites ({lo:g}-{hi:g} m)")
        lo, hi = RADIUS_RANGE_M
        if not lo <= self.radius_m <= hi:
            raise ValueError(f"rayon hors limites ({lo:g}-{hi:g} m)")

    @property
    def volume_m3(self) -> float:
        return math.pi * self.radius_m ** 2 * self.length_m

    @property
    def mass_kg(self) -> float:
        return self.density * self.volume_m3

    def energy_j(self, speed_kms: float) -> float:
        """Énergie cinétique relativiste (gamma - 1) m c^2."""
        return self.mass_kg * gamma_minus_1(speed_kms) * C_MS ** 2

    def momentum(self, speed_kms: float) -> float:
        """Quantité de mouvement relativiste, kg.m/s."""
        g = 1.0 + gamma_minus_1(speed_kms)
        return g * self.mass_kg * speed_kms * 1e3

    def penetration_m(self, target_density: float) -> float:
        """Pénétration hypervitesse (limite hydrodynamique) : L * sqrt(rho_p / rho_c)."""
        return self.length_m * math.sqrt(self.density / target_density)

    @staticmethod
    def energy_mt(energy_j: float) -> float:
        return energy_j / MT_TNT_J


def radius_for_mass(mass_kg: float, length_m: float) -> float:
    """Rayon donnant la masse voulue pour une longueur donnée."""
    return math.sqrt(mass_kg / (TUNGSTEN_DENSITY * math.pi * length_m))
