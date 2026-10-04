"""Propagateur RK4 à pas adaptatif pour un projectile soumis à la gravité du système solaire.

Le projectile est une particule test attirée par le Soleil et les 8 planètes
(positions fournies par les éphémérides képlériennes). Le pas est borné par la
distance au corps le plus proche, ce qui garantit une détection fiable des impacts.
"""
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..constants import AU_KM, DAY_S, YEAR_S
from ..solarsystem.rotation import latlon_from_vector
from ..solarsystem.system import SolarSystem


@dataclass
class ShotResult:
    outcome: str                      # impact | time_reached | timeout | lost
    t_start: float
    t_end: float
    times: np.ndarray
    positions: np.ndarray             # (K, 3) héliocentriques
    body: Optional[str] = None        # corps touché
    impact_lat: float = 0.0
    impact_lon: float = 0.0
    impact_speed: float = 0.0         # km/s relatif au corps
    closest: dict = field(default_factory=dict)   # nom -> (distance centre km, t)
    steps: int = 0
    final_pos: Optional[np.ndarray] = None


class Propagator:
    def __init__(self, system: SolarSystem, eta=0.02, dt_max=DAY_S, dt_min=1.0):
        self.system = system
        self.eta, self.dt_max, self.dt_min = eta, dt_max, dt_min
        self._gm = system.gm
        self._rad2 = system.radius ** 2
        self._inv_r3 = 1.0 / system.radius ** 3

    def _acc(self, r, P):
        d = P - r
        d2 = np.einsum("ij,ij->i", d, d)
        k = np.where(d2 < self._rad2, self._inv_r3, np.maximum(d2, self._rad2) ** -1.5)  # sphère homogène à l'intérieur
        return (self._gm * k) @ d

    def run(self, t0, r0, v0, t_end=None, max_duration=40 * YEAR_S, stop_on_hit=True,
            max_steps=150_000) -> ShotResult:
        sys_, gm, rad = self.system, self._gm, self.system.radius
        t = float(t0)
        r = np.array(r0, float)
        v = np.array(v0, float)
        t_limit = t0 + max_duration
        P0, V0 = sys_.states(t)
        ts, rs = [t], [r.copy()]
        dmin = np.full(len(rad), np.inf)
        tmin = np.zeros(len(rad))
        steps = 0
        outcome = "timeout"
        hit = None

        while steps < max_steps:
            d = np.linalg.norm(r - P0, axis=1)
            upd = d < dmin
            dmin[upd], tmin[upd] = d[upd], t
            vrel = np.linalg.norm(v - V0, axis=1)
            tau = np.minimum(d / np.maximum(vrel, 1e-3), np.sqrt(d ** 3 / gm))
            dt = min(max(self.eta * tau.min(), self.dt_min), self.dt_max)
            last = False
            if t_end is not None and t + dt >= t_end:
                dt, last = t_end - t, True
            if dt <= 0:
                outcome = "time_reached"
                break

            Pm = sys_.positions(t + 0.5 * dt)
            P1, V1 = sys_.states(t + dt)
            a1 = self._acc(r, P0)
            k2r = v + 0.5 * dt * a1
            a2 = self._acc(r + 0.5 * dt * v, Pm)
            k3r = v + 0.5 * dt * a2
            a3 = self._acc(r + 0.5 * dt * k2r, Pm)
            k4r = v + dt * a3
            a4 = self._acc(r + dt * k3r, P1)
            r_new = r + dt / 6.0 * (v + 2 * k2r + 2 * k3r + k4r)
            v_new = v + dt / 6.0 * (a1 + 2 * a2 + 2 * a3 + a4)

            if stop_on_hit:
                rel1 = r_new - P1
                inside = np.linalg.norm(rel1, axis=1) < rad
                if inside.any():
                    hit = self._locate_hit(t, dt, r, v, r_new, v_new, P0, P1, inside)
                    outcome = "impact"
                    break

            t += dt
            r, v, P0, V0 = r_new, v_new, P1, V1
            steps += 1
            ts.append(t)
            rs.append(r.copy())
            if last:
                outcome = "time_reached"
                break
            if t >= t_limit:
                outcome = "timeout"
                break
            if np.linalg.norm(r) > 300 * AU_KM:
                outcome = "lost"
                break

        d = np.linalg.norm(r - P0, axis=1)
        upd = d < dmin
        dmin[upd], tmin[upd] = d[upd], t
        res = ShotResult(outcome, t0, t, np.array(ts), np.array(rs), steps=steps, final_pos=r.copy())
        res.closest = {n: (float(dmin[i]), float(tmin[i])) for i, n in enumerate(sys_.names)}
        if hit is not None:
            i, s, rel, vimp, t_hit = hit
            body = sys_.bodies[i]
            res.body = body.name
            res.t_end = t_hit
            lat, lon = latlon_from_vector(body, t_hit, rel)
            res.impact_lat, res.impact_lon = lat, lon
            res.impact_speed = float(np.linalg.norm(vimp - sys_.states(t_hit)[1][i]))
            res.final_pos = sys_.positions(t_hit)[i] + rel
            res.times = np.append(res.times, t_hit)
            res.positions = np.vstack([res.positions, res.final_pos])
        return res

    def _locate_hit(self, t, dt, r, v, r_new, v_new, P0, P1, inside):
        """Instant et point d'impact par interpolation linéaire dans le repère du corps."""
        best = None
        for i in np.nonzero(inside)[0]:
            rel0, rel1 = r - P0[i], r_new - P1[i]
            dlt = rel1 - rel0
            R = self.system.radius[i]
            a, b, c = dlt @ dlt, 2 * rel0 @ dlt, rel0 @ rel0 - R * R
            disc = max(b * b - 4 * a * c, 0.0)
            s = (-b - np.sqrt(disc)) / (2 * a) if a > 0 else 0.0
            s = min(max(s, 0.0), 1.0)
            if best is None or s < best[1]:
                rel = rel0 + s * dlt
                rel = rel / np.linalg.norm(rel) * R
                best = (i, s, rel, v + s * (v_new - v), t + s * dt)
        return best
