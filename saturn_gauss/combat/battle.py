"""Attaque ennemie sur Saturne : vagues de vaisseaux sur trajectoire hyperbolique."""
from dataclasses import dataclass, field
from typing import List

import numpy as np

from .ships import CLASSES, Ship, make_ship

NAMES = ["Aquilon", "Vindicta", "Ombre-Noire", "Faucheur", "Tempête", "Obsidienne", "Corsaire", "Mantis",
         "Hydre", "Spectre", "Lame-Froide", "Cendre"]


@dataclass
class Battle:
    ships: List[Ship]
    t_start: float
    objective_km: float = 1.5e5
    state: str = "ongoing"          # ongoing | won | lost
    paid: float = 0.0
    log: list = field(default_factory=list)

    def active(self):
        return [s for s in self.ships if not s.neutralized]

    def step(self, t, dt, shooters, say):
        """Avance de dt secondes : régénération, tirs des vaisseaux sur les stations, objectif atteint ?"""
        if self.state != "ongoing":
            return
        t1 = t + dt
        for sh in shooters:
            sh.regen(dt)
        for ship in self.ships:
            if ship.destroyed:
                continue
            ship.regen_shield(dt)
            pos, _ = ship.state(t1)
            if ship.neutralized:
                continue
            if np.linalg.norm(pos) <= self.objective_km:
                self.state = "lost"
                say(f"!! {ship.name} ({ship.spec.name}) atteint Saturne !")
                return
            fp = ship.firepower_j
            if fp > 0 and t1 >= ship.next_fire:
                cands = [(np.linalg.norm(s.rel_state(t1)[0] - pos), s) for s in shooters if s.online]
                cands = [(d, s) for d, s in cands if d <= ship.spec.range_km]
                if cands:
                    prefer = [c for c in cands if c[1].id == ship.last_attacker]
                    d, tgt = prefer[0] if prefer else min(cands, key=lambda c: c[0])
                    rest = tgt.take_damage(fp)
                    ship.next_fire = t1 + ship.spec.reload_s
                    msg = f"{ship.name} tire sur {tgt.name} ({fp:.1e} J, {d:,.0f} km)".replace(",", " ")
                    if not tgt.online:
                        msg += f" — {tgt.name} HORS SERVICE"
                    say(msg)
        if not self.active():
            self.state = "won"


def eta_to_objective(ships, t0, objective_km, horizon=3e5):
    ts = np.linspace(t0, t0 + horizon, 3000)
    for t in ts:
        if np.linalg.norm(ships[0].state(t)[0]) <= objective_km:
            return float(t)
    return float(t0 + horizon)


def class_pool(rank: int):
    pool = ["patrouilleur", "corvette", "minier"]
    if rank >= 2:
        pool += ["fregate", "transport", "soutien"]
    if rank >= 4:
        pool += ["destroyer"]
    if rank >= 7:
        pool += ["capitale"]
    return pool


def approach_state(rng, mu):
    """État initial (r0, v0) d'une approche hyperbolique de Saturne dont le périapse est sous l'objectif."""
    q = float(rng.uniform(0.9e5, 1.4e5))
    vinf = float(rng.uniform(15.0, 45.0))
    D0 = float(rng.uniform(1.4e6, 2.2e6))
    h = np.sqrt(q * (2 * mu + q * vinf ** 2))
    vat = np.sqrt(vinf ** 2 + 2 * mu / D0)
    sinphi = h / (D0 * vat)
    u = rng.normal(size=3)
    u /= np.linalg.norm(u)
    w = rng.normal(size=3)
    w -= (w @ u) * u
    w /= np.linalg.norm(w)
    cosphi = np.sqrt(1 - sinphi ** 2)
    return D0 * u, vat * (-u * cosphi + w * sinphi)


def retaliation(ships, t, rng, mu) -> "Battle":
    """Les survivants d'une flotte repartent à l'attaque de Saturne."""
    r0, v0 = approach_state(rng, mu)
    for k, s in enumerate(ships):
        s.r0 = r0 + (rng.normal(size=3) * 40.0 if k else 0.0)
        s.v0, s.t0, s.mu, s.next_fire = v0.copy(), t, mu, 0.0
    return Battle(list(ships), t)


def spawn_wave(rank: int, t: float, rng, mu: float, classes=None) -> Battle:
    pool = class_pool(rank)
    n = int(min(4, 1 + rank // 3))
    n = int(rng.integers(1, n + 1))
    classes = classes or [pool[int(rng.integers(len(pool)))] for _ in range(n)]
    if rank >= 4 and "destroyer" not in classes and "capitale" not in classes and rng.random() < 0.5:
        classes[0] = "destroyer"
    r0, v0 = approach_state(rng, mu)
    ships = []
    for k, c in enumerate(classes, start=1):
        off = rng.normal(size=3) * 40.0 * (k > 1)
        name = f"{NAMES[int(rng.integers(len(NAMES)))]}-{k}"
        ships.append(make_ship(c, k, name, r0 + off, v0, t, mu))
    return Battle(ships, t)
