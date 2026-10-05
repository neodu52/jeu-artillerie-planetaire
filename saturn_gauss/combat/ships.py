"""Vaisseaux : classes, composants (boîtes), boucliers."""
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np

from ..ballistics.kepler2b import propagate


@dataclass
class Component:
    key: str
    name: str
    center: np.ndarray         # m, repère du vaisseau (x avant, y gauche, z haut)
    size: np.ndarray           # m
    hp_max: float              # J
    armor_m: float
    role: str                  # hull | bridge | reactor | shield | engine | weapon | cargo | crew | workshop
    critical: bool = False
    weapon_j: float = 0.0
    hp: float = -1.0

    def __post_init__(self):
        if self.hp < 0:
            self.hp = self.hp_max

    @property
    def alive(self) -> bool:
        return self.hp > 0

    @property
    def volume(self) -> float:
        return float(np.prod(self.size))


@dataclass(frozen=True)
class ShipClass:
    key: str
    name: str
    length: float
    width: float
    height: float
    shield_j: float
    hp_unit: float
    armor_m: float
    value: float               # prime de destruction (crédits)
    penalty: float             # coût si le vaisseau atteint son objectif
    n_weapons: int
    weapon_j: float
    n_engines: int
    extra: Optional[Tuple[str, str, int]]    # (nom, rôle, nombre)
    range_km: float
    reload_s: float
    speed_kms: float
    regen: float = 0.004       # fraction du bouclier regagnée par seconde


CLASSES = {c.key: c for c in [
    ShipClass("capitale", "Capitale", 2400, 560, 330, 6e17, 6e16, 2.0, 150_000, 120_000, 4, 1.2e17, 3,
              ("Hangar", "cargo", 1), 8e5, 40, 25.0),
    ShipClass("destroyer", "Destroyer", 720, 160, 100, 1.5e17, 1.5e16, 1.0, 45_000, 40_000, 2, 6e16, 2,
              None, 5e5, 30, 35.0),
    ShipClass("fregate", "Frégate", 320, 80, 55, 6e16, 6e15, 0.6, 20_000, 18_000, 1, 4e16, 1,
              None, 4e5, 30, 40.0),
    ShipClass("corvette", "Corvette", 160, 40, 28, 2.5e16, 2.5e15, 0.4, 9_000, 8_000, 1, 2e16, 1,
              None, 3e5, 25, 50.0),
    ShipClass("patrouilleur", "Patrouilleur", 90, 24, 16, 1e16, 1e15, 0.25, 5_000, 4_000, 1, 1e16, 1,
              None, 2e5, 25, 55.0),
    ShipClass("transport", "Transport de troupes", 520, 140, 90, 8e16, 8e15, 0.8, 30_000, 60_000, 1, 1.5e16, 2,
              ("Baie de troupes", "crew", 2), 1e5, 40, 30.0),
    ShipClass("minier", "Minier", 380, 110, 80, 3e16, 3e15, 0.5, 6_000, 5_000, 1, 1e16, 1,
              ("Cale à minerai", "cargo", 1), 5e4, 40, 30.0),
    ShipClass("soutien", "Soutien", 410, 100, 70, 6e16, 6e15, 0.6, 18_000, 15_000, 0, 0.0, 1,
              ("Atelier de réparation", "workshop", 1), 1.5e5, 40, 30.0, regen=0.012),
]}

_WEAPON_SLOTS = [(.18, .27, .40), (.18, -.27, .40), (-.10, .27, .40), (-.10, -.27, .40),
                 (.10, .27, -.38), (.10, -.27, -.38)]
_EXTRA_SLOTS = [((-.18, 0, .38), (.22, .34, .24)), ((0, .40, 0), (.30, .18, .30)), ((0, -.40, 0), (.30, .18, .30))]


def build_components(c: ShipClass) -> List[Component]:
    L, W, H = c.length, c.width, c.height
    mk = lambda key, name, pos, size, hp, armor, role, crit=False, wj=0.0: Component(
        key, name, np.array([pos[0] * L, pos[1] * W, pos[2] * H]),
        np.array([size[0] * L, size[1] * W, size[2] * H]), c.hp_unit * hp, c.armor_m * armor, role, crit, wj)
    comps = [
        mk("hull", "Coque centrale", (0, 0, 0), (.62, .55, .50), 3.0, 1.2, "hull"),
        mk("bridge", "Pont de commandement", (.34, 0, .42), (.10, .30, .40), 1.0, .9, "bridge"),
        mk("reactor", "Réacteur", (-.04, 0, -.40), (.20, .40, .34), 1.5, 1.0, "reactor", True),
        mk("shield", "Générateur de bouclier", (.36, 0, -.32), (.10, .28, .26), .8, .6, "shield"),
    ]
    ys = {1: [0.0], 2: [-.25, .25], 3: [-.28, 0.0, .28]}[min(c.n_engines, 3)]
    for i, y in enumerate(ys):
        comps.append(mk(f"engine{i + 1}", f"Moteur {i + 1}", (-.43, y, 0), (.16, .20, .30), 1.0, .7, "engine"))
    for i in range(c.n_weapons):
        x, y, z = _WEAPON_SLOTS[i]
        comps.append(mk(f"weapon{i + 1}", f"Batterie {i + 1}", (x, y, z), (.10, .14, .22), .8, .6, "weapon",
                        False, c.weapon_j))
    if c.extra:
        name, role, n = c.extra
        slots = _EXTRA_SLOTS[1:3] if role == "crew" else _EXTRA_SLOTS[:1]
        for i in range(n):
            pos, size = slots[i]
            nm = f"{name} {i + 1}" if n > 1 else name
            comps.append(mk(f"extra{i + 1}", nm, pos, size, 1.0, .6, role))
    return comps


@dataclass
class Ship:
    id: int
    name: str
    cls: str
    comps: List[Component]
    shield: float
    shield_max: float
    regen: float
    r0: np.ndarray                  # état initial par rapport à Saturne (km, km/s)
    v0: np.ndarray
    t0: float
    mu: float
    crew: float = 1.0
    next_fire: float = 0.0
    last_attacker: Optional[int] = None
    offset_km: np.ndarray = field(default_factory=lambda: np.zeros(3))   # pour les flottes statiques

    # -- mouvement
    def state(self, t):
        return propagate(self.r0, self.v0, t - self.t0, self.mu)

    @staticmethod
    def axes(v, r=None):
        f = v / np.linalg.norm(v)
        up = np.array([0.0, 0.0, 1.0]) - f[2] * f
        if np.linalg.norm(up) < 1e-6:
            up = np.array([1.0, 0.0, 0.0]) - f[0] * f
        up /= np.linalg.norm(up)
        left = np.cross(up, f)
        return np.column_stack([f, left, up])

    def comp_pose(self, i, pos, A):
        c = self.comps[i]
        return pos + A @ (c.center / 1000.0), A, c.size / 2000.0

    # -- état
    @property
    def spec(self) -> ShipClass:
        return CLASSES[self.cls]

    def comp(self, role):
        return [c for c in self.comps if c.role == role]

    @property
    def destroyed(self) -> bool:
        return not all(c.alive for c in self.comp("reactor")) or not self.comps[0].alive

    @property
    def disabled(self) -> bool:
        return (not self.destroyed) and (not all(c.alive for c in self.comp("bridge")) or self.crew < 0.2)

    @property
    def neutralized(self) -> bool:
        return self.destroyed or self.disabled

    @property
    def status(self) -> str:
        return "détruit" if self.destroyed else ("neutralisé" if self.neutralized else "actif")

    @property
    def shield_online(self) -> bool:
        return all(c.alive for c in self.comp("shield"))

    @property
    def firepower_j(self) -> float:
        if self.neutralized:
            return 0.0
        return sum(c.weapon_j for c in self.comps if c.role == "weapon" and c.alive)

    def regen_shield(self, dt):
        if self.shield_online and not self.destroyed:
            self.shield = min(self.shield_max, self.shield + self.shield_max * self.regen * dt)

    @property
    def hp_fraction(self) -> float:
        tot = sum(c.hp_max for c in self.comps)
        return sum(max(c.hp, 0) for c in self.comps) / tot

    @property
    def bounty(self) -> float:
        v = self.spec.value
        if self.destroyed:
            return v
        if self.crew < 0.2:
            return 1.5 * v          # capture
        return 0.7 * v if self.disabled else 0.0


def make_ship(cls_key: str, ship_id: int, name: str, r0, v0, t0, mu) -> Ship:
    c = CLASSES[cls_key]
    return Ship(ship_id, name, cls_key, build_components(c), c.shield_j, c.shield_j, c.regen,
                np.asarray(r0, float), np.asarray(v0, float), t0, mu)
