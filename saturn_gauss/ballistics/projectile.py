"""Barre de tungstène : géométrie, masse, énergie, pénétration."""
import math
from dataclasses import dataclass

from ..constants import MT_TNT_J, TUNGSTEN_DENSITY

LENGTH_RANGE_M = (1.0, 100.0)
RADIUS_RANGE_M = (0.02, 2.0)


@dataclass
class Rod:
    length_m: float = 10.0
    radius_m: float = 0.30

    def validate(self):
        lo, hi = LENGTH_RANGE_M
        if not lo <= self.length_m <= hi:
            raise ValueError(f"longueur hors limites ({lo}-{hi} m)")
        lo, hi = RADIUS_RANGE_M
        if not lo <= self.radius_m <= hi:
            raise ValueError(f"rayon hors limites ({lo}-{hi} m)")

    @property
    def volume_m3(self) -> float:
        return math.pi * self.radius_m ** 2 * self.length_m

    @property
    def mass_kg(self) -> float:
        return TUNGSTEN_DENSITY * self.volume_m3

    def energy_j(self, speed_kms: float) -> float:
        return 0.5 * self.mass_kg * (speed_kms * 1e3) ** 2

    def penetration_m(self, target_density: float) -> float:
        """Pénétration hypervitesse (limite hydrodynamique) : L * sqrt(rho_p / rho_c)."""
        return self.length_m * math.sqrt(TUNGSTEN_DENSITY / target_density)

    @staticmethod
    def energy_mt(energy_j: float) -> float:
        return energy_j / MT_TNT_J


def radius_for_mass(mass_kg: float, length_m: float) -> float:
    """Rayon donnant la masse voulue pour une longueur donnée."""
    return math.sqrt(mass_kg / (TUNGSTEN_DENSITY * math.pi * length_m))
