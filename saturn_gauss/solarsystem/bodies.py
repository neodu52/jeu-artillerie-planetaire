"""Données physiques des corps du système solaire.

Éléments orbitaux : approximation de Standish (JPL), référence écliptique J2000.
Ordre : a, a', e, e', I, I', L, L', varpi, varpi', Omega, Omega'
(UA et degrés ; dérivées par siècle julien).
Rotation : IAU (pôle nord RA/Dec ICRF, méridien W0 et vitesse en deg/jour).
"""
from dataclasses import dataclass
from typing import Optional, Tuple
import unicodedata


def normalize(name: str) -> str:
    s = unicodedata.normalize("NFD", name)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


@dataclass(frozen=True)
class Body:
    name: str
    gm: float                      # km^3/s^2
    radius: float                  # km
    color: str
    pole_ra: float                 # deg
    pole_dec: float                # deg
    w0: float                      # deg
    w_rate: float                  # deg/jour (négatif = rotation rétrograde)
    elements: Optional[Tuple[float, ...]] = None
    solid: bool = True             # surface solide (pénétration possible)
    surface_density: float = 2800.0  # kg/m^3

    @property
    def key(self) -> str:
        return normalize(self.name)

    @property
    def rotation_period_h(self) -> float:
        return 360.0 / self.w_rate * 24.0


SUN = Body("Soleil", 1.32712440018e11, 695_700.0, "gold", 286.13, 63.87, 84.176, 14.1844)

PLANETS = [
    Body("Mercure", 22_031.78, 2_439.7, "gray", 281.0103, 61.4155, 329.5988, 6.1385025,
         (0.38709927, 0.00000037, 0.20563593, 0.00001906, 7.00497902, -0.00594749,
          252.25032350, 149472.67411175, 77.45779628, 0.16047689, 48.33076593, -0.12534081)),
    Body("Vénus", 324_858.59, 6_051.8, "goldenrod", 272.76, 67.16, 160.20, -1.4813688,
         (0.72333566, 0.00000390, 0.00677672, -0.00004107, 3.39467605, -0.00078890,
          181.97909950, 58517.81538729, 131.60246718, 0.00268329, 76.67984255, -0.27769418)),
    Body("Terre", 403_503.2, 6_371.0, "royalblue", 0.0, 90.0, 190.147, 360.9856235,
         (1.00000261, 0.00000562, 0.01671123, -0.00004392, -0.00001531, -0.01294668,
          100.46457166, 35999.37244981, 102.93768193, 0.32327364, 0.0, 0.0)),
    Body("Mars", 42_828.37, 3_389.5, "orangered", 317.68143, 52.8865, 176.630, 350.89198226,
         (1.52371034, 0.00001847, 0.09339410, 0.00007882, 1.84969142, -0.00813131,
          -4.55343205, 19140.30268499, -23.94362959, 0.44441088, 49.55953891, -0.29257343)),
    Body("Jupiter", 126_712_764.1, 69_911.0, "peru", 268.056595, 64.495303, 284.95, 870.5366420,
         (5.20288700, -0.00011607, 0.04838624, -0.00013253, 1.30439695, -0.00183714,
          34.39644051, 3034.74612775, 14.72847983, 0.21252668, 100.47390909, 0.20469106),
         solid=False),
    Body("Saturne", 37_940_584.8, 58_232.0, "khaki", 40.589, 83.537, 38.90, 810.7939024,
         (9.53667594, -0.00125060, 0.05386179, -0.00050991, 2.48599187, 0.00193609,
          49.95424423, 1222.49362201, 92.59887831, -0.41897216, 113.66242448, -0.28867794),
         solid=False),
    Body("Uranus", 5_794_556.4, 25_362.0, "lightseagreen", 257.311, -15.175, 203.81, -501.1600928,
         (19.18916464, -0.00196176, 0.04725744, -0.00004397, 0.77263783, -0.00242939,
          313.23810451, 428.48202785, 170.95427630, 0.40805281, 74.01692503, 0.04240589),
         solid=False),
    Body("Neptune", 6_836_527.1, 24_622.0, "slateblue", 299.36, 43.46, 253.18, 536.3128492,
         (30.06992276, 0.00026291, 0.00859048, 0.00005105, 1.77004347, 0.00035372,
          -55.12002969, 218.45945325, 44.96476227, -0.32241464, 131.78422574, -0.00508664),
         solid=False),
]
