"""Contrats (optionnels) et événements prioritaires (non refusables)."""
from dataclasses import dataclass, field
from typing import Any, List, Optional

import numpy as np

from .ballistics.kepler2b import propagate
from .combat.battle import Battle, eta_to_objective, spawn_wave
from .combat.ships import CLASSES, Ship, make_ship
from .constants import AU_KM, DAY_S, GM_SUN
from .game.missions import CAMPAIGN
from .guidance import GuidanceSpec
from .targets import AsteroidTarget, FleetTarget, SurfaceTarget


@dataclass
class Contract:
    id: int
    kind: str                      # strike | fleet | protect | asteroid | defense
    title: str
    text: str
    priority: bool
    reward: float
    penalty: float
    t_created: float
    deadline: Optional[float]
    op: Any
    state: str = "offered"         # offered | active | done | failed | refused | expired
    offer_until: Optional[float] = None
    note: str = ""

    @property
    def open(self) -> bool:
        return self.state in ("offered", "active")


# --------------------------------------------------------------------------- opérations
@dataclass
class StrikeOp:
    target: SurfaceTarget
    energy_j: float
    energy_tol: float
    tolerance_km: float
    min_penetration_m: Optional[float] = None
    max_flight_days: Optional[float] = None

    def spec(self, system):
        return GuidanceSpec(self.target, self.energy_j, self.min_penetration_m,
                            system.get(self.target.body).surface_density, self.max_flight_days)


@dataclass
class FleetOp:
    target: FleetTarget
    ships: List[Ship]
    offsets: List[np.ndarray]
    protect: Optional[str] = None
    max_flight_days: float = 2.0
    resolved: bool = False

    def spec(self, system):
        return GuidanceSpec(self.target, None, None, 2800.0, self.max_flight_days)

    def ship_positions(self, system, t):
        c = self.target.point(system, t).pos
        return [c + o for o in self.offsets]


@dataclass
class AsteroidOp:
    asteroid: AsteroidTarget
    threatened: str
    t_impact: float
    b_crit_km: float
    v_inf: float
    miss_km: float
    shots: int = 0
    history: list = field(default_factory=list)

    def spec(self, system):
        return GuidanceSpec(self.asteroid, None, None, 2800.0, (self.t_impact - self.history[0][0]) / DAY_S
                            if self.history else None)


@dataclass
class DefenseOp:
    battle: Battle


# --------------------------------------------------------------------------- générateurs
STRIKE_REWARDS = [8_000, 9_000, 12_000, 15_000, 22_000, 18_000]


def initial_strikes(t0, next_id):
    out = []
    for k, m in enumerate(CAMPAIGN):
        op = StrikeOp(SurfaceTarget(m.target, m.lat, m.lon), m.energy_j, m.energy_tol, m.tolerance_km,
                      m.min_penetration_m, m.max_flight_days)
        txt = m.briefing
        out.append(Contract(next_id + k, "strike", m.title, txt, False, float(STRIKE_REWARDS[k]), 0.0,
                            t0, None, op, offer_until=None))
    return out


FLEET_PLANETS = ["Mercure", "Vénus", "Mars", "Jupiter", "Uranus", "Neptune"]


def new_fleet_contract(system, t, rank, rng, cid, protect=False) -> Contract:
    planet = FLEET_PLANETS[int(rng.integers(len(FLEET_PLANETS)))]
    body = system.get(planet)
    r_orb = body.radius * float(rng.uniform(1.6, 3.2))
    target = FleetTarget(planet, r_orb, float(rng.uniform(0, 100)), float(rng.uniform(0, 360)),
                         float(rng.uniform(0, 360)))
    n = int(min(5, 2 + rank // 2))
    pool = ["corvette", "fregate", "transport", "minier", "soutien", "patrouilleur"]
    if rank >= 4:
        pool += ["destroyer"]
    if rank >= 7:
        pool += ["capitale"]
    ships, offsets = [], []
    for k in range(n):
        cls = pool[int(rng.integers(len(pool)))]
        ships.append(make_ship(cls, k + 1, f"{cls.capitalize()}-{k + 1}", [1, 0, 0], [0, 1, 0], t, 1.0))
        offsets.append(rng.normal(size=3) * 6.0)
    value = sum(s.spec.value for s in ships)
    days = float(rng.uniform(3, 8))
    reward = round(value * (1.6 if protect else 1.3) + 15_000, -2)
    if protect:
        title = f"Protection de {planet}"
        text = (f"Une flotte hostile ({n} vaisseaux) se rassemble en orbite de {planet} et fonce sur une "
                f"colonie. L'assaut aura lieu dans {days:.1f} jours. Détruisez-la avant (bombes : nuke / antimatter).")
    else:
        title = f"Élimination : flotte autour de {planet}"
        text = (f"Une flotte de {n} vaisseaux est stationnée en orbite de {planet}. Hors de portée des "
                f"stations : utilisez le canon interplanétaire avec une bombe à détonation de proximité.")
    op = FleetOp(target, ships, offsets, protect=planet if protect else None, max_flight_days=min(days, 2.0))
    return Contract(cid, "protect" if protect else "fleet", title, text, False, reward, value * 0.5 if protect else 0.0,
                    t, t + days * DAY_S, op, offer_until=t + 6 * DAY_S)


def _min_distance(ast: AsteroidTarget, system, planet, t_ref, half_window=4 * DAY_S, n=3000):
    ts = t_ref + np.linspace(-half_window, half_window, n)
    ip = system.index(planet) - 1
    pp = system.planet_states(ts)[0][:, ip, :]
    ap = np.array([propagate(ast.r0, ast.v0, t - ast.t0, GM_SUN)[0] for t in ts])
    d = np.linalg.norm(ap - pp, axis=1)
    k = int(np.argmin(d))
    lo, hi = max(k - 1, 0), min(k + 1, n - 1)
    ts2 = np.linspace(ts[lo], ts[hi], 400)
    pp2 = system.planet_states(ts2)[0][:, ip, :]
    ap2 = np.array([propagate(ast.r0, ast.v0, t - ast.t0, GM_SUN) for t in ts2], dtype=object)
    d2 = np.array([np.linalg.norm(a[0] - p) for a, p in zip(ap2, pp2)])
    j = int(np.argmin(d2))
    vrel = np.linalg.norm(ap2[j][1] - system.planet_states(ts2[j])[1][ip])
    return float(d2[j]), float(ts2[j]), float(vrel)


def asteroid_miss(ast: AsteroidTarget, system, planet, t_impact):
    return _min_distance(ast, system, planet, t_impact)


ASTEROID_PLANETS = ["Mercure", "Vénus", "Mars", "Jupiter"]


def new_asteroid(system, t, rng, cid, planet=None, priority=True) -> Contract:
    """Astéroïde en collision avec une colonie alliée.

    Physique : un tir depuis Saturne qui part le long de la trajectoire relative de l'astéroïde ne
    peut pas le dévier (un simple retard ne change pas son point de passage). On impose donc une
    géométrie où la ligne de visée depuis Saturne est franchement latérale à sa vitesse d'approche.
    """
    planet = planet or ASTEROID_PLANETS[int(rng.integers(len(ASTEROID_PLANETS)))]
    body = system.get(planet)
    i = system.index(planet)
    isat = system.index("Saturne")
    for _ in range(400):
        lead = float(rng.uniform(150, 320)) * DAY_S
        T = t + lead
        P, V = system.states(T)
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        vinf = float(rng.uniform(8, 18))
        r0, v0 = propagate(P[i], V[i] + vinf * u, -lead, GM_SUN)
        los = r0 - system.positions(t)[isat]
        if np.linalg.norm(np.cross(los / np.linalg.norm(los), u)) < 0.5:
            continue
        ts = np.linspace(t, T, 200)
        rmin = min(np.linalg.norm(propagate(r0, v0, x - t, GM_SUN)[0]) for x in ts)
        if rmin > 0.15 * AU_KM:
            break
    radius_km = float(rng.uniform(0.06, 0.12))
    mass = 4.0 / 3.0 * np.pi * (radius_km * 1000) ** 3 * 1500.0
    ast = AsteroidTarget(t, r0, v0, radius_km, mass)
    b_crit = body.radius * np.sqrt(1.0 + 2 * body.gm / (body.radius * vinf ** 2))
    miss, tmin, _ = asteroid_miss(ast, system, planet, T)
    op = AsteroidOp(ast, planet, T, float(b_crit), vinf, miss, history=[(t, miss)])
    reward = round(40_000 + 0.5 * b_crit + mass / 1e6, -2)
    text = (f"Astéroïde de {2 * radius_km * 1000:.0f} m ({mass:.1e} kg) en collision avec la colonie de {planet} "
            f"dans {lead / DAY_S:.0f} jours (v_inf = {vinf:.1f} km/s). Déviez-le d'au moins "
            f"{1.3 * b_crit:,.0f} km : un impact cinétique lui transmet de la quantité de mouvement.").replace(",", " ")
    return Contract(cid, "asteroid", f"Astéroïde vers {planet}", text, priority, reward, reward, t, T, op,
                    state="active" if priority else "offered", offer_until=None if priority else t + 8 * DAY_S)


def new_attack(system, t, rank, rng, cid, mu_saturn) -> Contract:
    b = spawn_wave(rank, t, rng, mu_saturn)
    eta = eta_to_objective(b.ships, t, b.objective_km)
    value = sum(s.spec.value for s in b.ships)
    pen = sum(s.spec.penalty for s in b.ships)
    names = ", ".join(f"{s.name} ({s.spec.name})" for s in b.ships)
    text = (f"Attaque ennemie sur Saturne : {names}. Arrivée à l'objectif dans {(eta - t) / 3600:.1f} h. "
            "Choisissez une station bien placée, visez un composant, calculez l'orientation et tirez.")
    return Contract(cid, "defense", "ATTAQUE SUR SATURNE", text, True, value, pen, t, eta, DefenseOp(b), state="active")
