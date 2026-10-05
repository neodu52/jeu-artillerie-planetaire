"""Tireurs en orbite autour de Saturne : stations de défense et canon interplanétaire."""
from dataclasses import dataclass
from typing import Optional

import numpy as np


@dataclass
class Shooter:
    id: int
    name: str
    launcher: str
    hp_max: float
    shield_max: float
    value: float
    hp: float = -1.0
    shield: float = -1.0
    ready_at: float = 0.0

    def __post_init__(self):
        if self.hp < 0:
            self.hp = self.hp_max
        if self.shield < 0:
            self.shield = self.shield_max

    @property
    def online(self) -> bool:
        return self.hp > 0

    def take_damage(self, energy_j: float) -> float:
        """Applique des dégâts (bouclier puis structure). Retourne l'énergie qui a atteint la structure."""
        absorbed = min(self.shield, energy_j)
        self.shield -= absorbed
        rest = energy_j - absorbed
        self.hp = max(0.0, self.hp - rest)
        return rest

    def regen(self, dt: float):
        if self.online:
            self.shield = min(self.shield_max, self.shield + self.shield_max * 0.002 * dt)

    @property
    def damage_fraction(self) -> float:
        return 1.0 - self.hp / self.hp_max

    @property
    def repair_cost(self) -> float:
        return self.value * self.damage_fraction

    def rel_state(self, t):             # pragma: no cover - surchargé
        raise NotImplementedError


@dataclass
class Station(Shooter):
    radius_km: float = 3e5
    inc_deg: float = 0.0
    node_deg: float = 0.0
    phase_deg: float = 0.0
    mu: float = 3.79e7

    def rel_state(self, t):
        n = np.sqrt(self.mu / self.radius_km ** 3)
        i, o = np.radians(self.inc_deg), np.radians(self.node_deg)
        e1 = np.array([np.cos(o), np.sin(o), 0.0])
        e2 = np.array([-np.sin(o) * np.cos(i), np.cos(o) * np.cos(i), np.sin(i)])
        th = np.radians(self.phase_deg) + n * t
        r = self.radius_km * (np.cos(th) * e1 + np.sin(th) * e2)
        v = self.radius_km * n * (-np.sin(th) * e1 + np.cos(th) * e2)
        return r, v


@dataclass
class CannonShooter(Shooter):
    cannon: Optional[object] = None

    def rel_state(self, t):
        cs = self.cannon.state(t)
        return cs.r_rel, cs.v_rel


def default_stations(mu: float):
    """Six stations dispersées sur des orbites variées autour de Saturne."""
    spec = [("Sentinelle", 180e3, 0, 0, 0), ("Vigie", 230e3, 35, 60, 120), ("Bastion", 290e3, 70, 120, 240),
            ("Rempart", 360e3, 110, 180, 40), ("Égide", 430e3, 150, 240, 160), ("Aurore", 500e3, 90, 300, 280)]
    out = []
    for k, (nm, r, inc, node, ph) in enumerate(spec, start=1):
        out.append(Station(k, f"{nm}-{k}", "gauss", 4e17, 1.5e17, 150_000, radius_km=r, inc_deg=inc,
                           node_deg=node, phase_deg=ph, mu=mu))
    return out
