"""Le système solaire complet : Soleil + 8 planètes, orbites et rotations."""
import numpy as np

from .bodies import PLANETS, SUN, Body, normalize
from .kepler import Ephemeris


class SolarSystem:
    def __init__(self):
        self.bodies = [SUN] + PLANETS
        self.names = [b.name for b in self.bodies]
        self.gm = np.array([b.gm for b in self.bodies])
        self.radius = np.array([b.radius for b in self.bodies])
        self._eph = Ephemeris([b.elements for b in PLANETS])
        self._lookup = {b.key: i for i, b in enumerate(self.bodies)}

    def __len__(self):
        return len(self.bodies)

    def index(self, name: str) -> int:
        try:
            return self._lookup[normalize(name)]
        except KeyError:
            raise KeyError(f"corps inconnu : {name!r} ({', '.join(self.names)})") from None

    def get(self, name: str) -> Body:
        return self.bodies[self.index(name)]

    def states(self, t: float):
        """(positions, vitesses), forme (N, 3), héliocentriques écliptiques (km, km/s)."""
        p, v = self._eph.states(t)
        P = np.zeros((len(self.bodies), 3))
        V = np.zeros_like(P)
        P[1:], V[1:] = p, v
        return P, V

    def planet_states(self, ts):
        """États des 8 planètes (sans le Soleil) pour un tableau de dates : (..., 8, 3)."""
        return self._eph.states(ts)

    def positions(self, t: float):
        p, _ = self._eph.states(t, velocity=False)
        P = np.zeros((len(self.bodies), 3))
        P[1:] = p
        return P

    def position(self, name: str, t: float) -> np.ndarray:
        return self.positions(t)[self.index(name)]

    def velocity(self, name: str, t: float) -> np.ndarray:
        return self.states(t)[1][self.index(name)]

    def orbit_path(self, name: str, t: float, n: int = 400) -> np.ndarray:
        """Trace de l'orbite complète d'une planète autour de t (pour les graphes)."""
        i = self.index(name)
        k = i - 1
        period = 2 * np.pi / self._eph.Mdot[k]
        ts = t + np.linspace(0, period, n)
        p, _ = self._eph.states(ts, velocity=False)
        return p[:, k, :]
