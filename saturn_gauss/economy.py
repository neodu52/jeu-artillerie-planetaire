"""Crédits, coûts de tir, améliorations."""
from dataclasses import dataclass

ENERGY_PRICE = 2e-15        # crédits par joule consommé
START_CREDITS = 60_000.0

ASSIST_COSTS = {"window": 400.0, "refine": 800.0, "solve": 150.0}


@dataclass(frozen=True)
class Upgrade:
    key: str
    name: str
    desc: str
    max_level: int
    base_cost: float
    growth: float


UPGRADES = {u.key: u for u in [
    Upgrade("vmax", "Accélérateurs orbitaux", "+1 % de c de vitesse max (Gauss et railgun)", 4, 40_000, 1.8),
    Upgrade("masse", "Chambres de tir renforcées", "+50 % de masse max par projectile (stations)", 4, 35_000, 1.7),
    Upgrade("cadence", "Cadence de tir", "-20 % de temps de rechargement (tous lanceurs)", 4, 30_000, 1.8),
    Upgrade("blindage", "Blindage des stations", "+50 % de structure pour les stations", 4, 25_000, 1.7),
    Upgrade("boucliers", "Boucliers de station", "+50 % de bouclier pour les stations", 4, 30_000, 1.7),
    Upgrade("canon_energie", "Alimentation du canon interplanétaire", "énergie max x4, masse max x2", 3, 80_000, 2.5),
    Upgrade("ordinateur", "Ordinateur de bord", "-25 % sur les frais de calcul (window, refine, solve)", 3, 20_000, 2.0),
]}


def upgrade_cost(key: str, level: int) -> float:
    u = UPGRADES[key]
    return round(u.base_cost * u.growth ** level, -2)


def assist_cost(kind: str, upgrades: dict) -> float:
    return ASSIST_COSTS[kind] * 0.75 ** int(upgrades.get("ordinateur", 0))


def shot_cost(ammo, launcher, mass_kg: float, kinetic_j: float) -> dict:
    """Détail du coût d'un tir : munition + énergie consommée."""
    energy_in = kinetic_j / launcher.efficiency
    ammo_cost = 0.0 if launcher.kind == "beam" else ammo.cost_per_kg * mass_kg
    energy_cost = energy_in * ENERGY_PRICE
    return {"munition": ammo_cost, "energie": energy_cost, "energie_j": energy_in,
            "total": ammo_cost + energy_cost}
