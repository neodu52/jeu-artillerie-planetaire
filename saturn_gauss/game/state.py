"""Contrôleur de jeu : état du canon, tirs, évaluation des résultats."""
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np

from ..ballistics.cannon import (CANNON_MASS_KG, E_MAX_J, V_MAX_KMS, GaussCannon, direction_vector)
from ..ballistics.integrator import Propagator, ShotResult
from ..ballistics.projectile import RADIUS_RANGE_M, Rod, radius_for_mass
from ..constants import GAME_START, MT_TNT_J
from ..guidance import Guidance, Plan
from ..solarsystem.rotation import great_circle_km
from ..solarsystem.system import SolarSystem
from ..timeutils import from_datetime
from .missions import CAMPAIGN, Mission


@dataclass
class ShotReport:
    result: ShotResult
    mission: Mission
    rod: Rod
    speed_kms: float
    energy_j: float
    hit_target_body: bool
    miss_km: Optional[float]
    energy_ok: bool
    penetration_m: Optional[float]
    penetration_ok: bool
    flight_ok: bool
    recoil_ms: float
    success: bool
    score: int = 0


@dataclass
class Game:
    system: SolarSystem = field(default_factory=SolarSystem)
    assist_enabled: bool = True

    def __post_init__(self):
        self.cannon = GaussCannon(self.system)
        self.prop = Propagator(self.system)
        self.guidance = Guidance(self.system, self.cannon, self.prop)
        self.t = from_datetime(GAME_START)
        self.rod = Rod()
        self.speed = 15.0              # km/s
        self.lon = 180.0               # degrés, longitude écliptique de visée
        self.lat = 0.0
        self.mission_index = 0
        self.last: Optional[ShotReport] = None
        self.windows: List[Plan] = []
        self.penalty = 0
        self.total_score = 0
        self.completed = set()

    # -- mission
    @property
    def mission(self) -> Mission:
        return CAMPAIGN[self.mission_index]

    def select_mission(self, idx: int):
        if not 0 <= idx < len(CAMPAIGN):
            raise ValueError(f"mission inexistante (1-{len(CAMPAIGN)})")
        self.mission_index = idx
        self.penalty = 0
        self.windows = []
        self.last = None

    # -- paramètres
    def energy_j(self) -> float:
        return self.rod.energy_j(self.speed)

    def apply_plan(self, plan: Plan, keep_rod_length: bool = False):
        """Charge un plan de tir. Avec keep_rod_length, seul le rayon est ajusté pour l'énergie."""
        self.t = plan.t_launch
        self.speed = plan.speed
        self.lon, self.lat = plan.lon_lat
        if keep_rod_length:
            mass = 2 * self.mission.energy_j / (self.speed * 1e3) ** 2
            r = radius_for_mass(mass, self.rod.length_m)
            if RADIUS_RANGE_M[0] <= r <= RADIUS_RANGE_M[1]:
                self.rod = Rod(self.rod.length_m, round(float(r), 4))
                return
        if plan.rod is not None:
            self.rod = plan.rod

    # -- tir
    def check_limits(self):
        self.rod.validate()
        if not 0.1 <= self.speed <= V_MAX_KMS:
            raise ValueError(f"vitesse de bouche hors limites (0.1-{V_MAX_KMS} km/s)")
        if self.energy_j() > E_MAX_J:
            raise ValueError(f"énergie {self.energy_j():.2e} J > capacité du canon ({E_MAX_J:.0e} J)")
        if not -90 <= self.lat <= 90:
            raise ValueError("latitude de visée hors limites")

    def fire(self) -> ShotReport:
        self.check_limits()
        cs = self.cannon.state(self.t)
        v_init = cs.v_helio + self.speed * direction_vector(self.lon, self.lat)
        res = self.prop.run(self.t, cs.r_helio, v_init)
        rep = self.evaluate(res)
        self.last = rep
        if rep.success:
            self.total_score += rep.score
            self.completed.add(self.mission_index)
        return rep

    def evaluate(self, res: ShotResult) -> ShotReport:
        m = self.mission
        body = self.system.get(m.target)
        E = self.energy_j()
        hit = res.outcome == "impact" and res.body == body.name
        miss = None
        if hit:
            miss = great_circle_km(res.impact_lat, res.impact_lon, m.lat, m.lon, body.radius)
        energy_ok = abs(E - m.energy_j) <= m.energy_tol * m.energy_j
        pen = None
        pen_ok = True
        if m.min_penetration_m:
            pen = self.rod.penetration_m(body.surface_density)
            pen_ok = pen >= m.min_penetration_m
        flight_ok = True
        if m.max_flight_days and hit:
            flight_ok = (res.t_end - res.t_start) / 86400.0 <= m.max_flight_days
        success = bool(hit and miss <= m.tolerance_km and energy_ok and pen_ok and flight_ok)
        score = 0
        if success:
            score = max(int(500 + 500 * (1 - miss / m.tolerance_km)) - self.penalty, 100)
        return ShotReport(res, m, self.rod, self.speed, E, hit, miss, energy_ok, pen, pen_ok,
                          flight_ok,
                          self.rod.mass_kg * self.speed * 1e3 / CANNON_MASS_KG, success, score)

    # -- assistance
    def find_windows(self, progress=None, max_flight_days=None):
        self.windows = self.guidance.find_windows(self.mission, self.t, progress=progress,
                                                  max_flight_days=max_flight_days)
        self.penalty += 100
        return self.windows

    def refine(self, plan: Plan, progress=None) -> Plan:
        self.penalty += 150
        return self.guidance.refine(self.mission, plan, progress=progress)
