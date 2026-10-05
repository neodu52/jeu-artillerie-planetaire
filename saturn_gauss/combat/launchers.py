"""Lanceurs : canon interplanétaire, canons orbitaux de station, laser, poudre."""
from dataclasses import dataclass, replace
from typing import Tuple

from ..constants import C_KMS
from ..ballistics.cannon import V_MAX_KMS


@dataclass(frozen=True)
class Launcher:
    key: str
    name: str
    v_min_kms: float
    v_max_kms: float
    max_mass_kg: float
    max_length_m: float
    max_radius_m: float
    efficiency: float          # énergie cinétique utile / énergie consommée
    reload_s: float
    max_range_km: float
    kind: str                  # kinetic | beam
    ammo: Tuple[str, ...]
    unlock_cost: float = 0.0
    desc: str = ""


_STATION_AMMO = ("rod", "ferrite", "ap_he", "dirty", "gas")

LAUNCHERS = {l.key: l for l in [
    Launcher("canon", "Canon de Gauss interplanétaire", 0.1, V_MAX_KMS, 2e5, 100.0, 2.0, 0.6, 600.0,
             float("inf"), "kinetic", _STATION_AMMO + ("nuke", "antimatter"), 0.0,
             "Le grand canon : atteint les autres planètes, tire jusqu'à c."),
    Launcher("gauss", "Canon de Gauss orbital", 0.50 * C_KMS, 0.95 * C_KMS, 5.0, 1.5, 0.10, 0.6, 20.0,
             3e6, "kinetic", _STATION_AMMO, 0.0, "Station standard : 50 à 95 % de c, petits projectiles."),
    Launcher("rail", "Railgun orbital", 0.50 * C_KMS, 0.99 * C_KMS, 15.0, 2.0, 0.12, 0.35, 12.0,
             3e6, "kinetic", _STATION_AMMO, 120_000.0, "Plus rapide et plus lourd, très gourmand en énergie."),
    Launcher("laser", "Laser orbital", C_KMS, C_KMS, 6e16, 0.0, 0.0, 0.20, 8.0, 2e6, "beam", ("beam",),
             150_000.0, "Impulsion instantanée (énergie en J), sans munition."),
    Launcher("poudre", "Obusier à poudre", 2.0, 15.0, 2000.0, 3.0, 0.40, 0.30, 15.0, 3000.0, "kinetic",
             ("rod", "dirty", "gas", "ferrite"), 0.0, "Rustique, bon marché, portée très courte."),
]}


def effective(launcher: Launcher, upgrades: dict) -> Launcher:
    """Applique les améliorations achetées."""
    lv = lambda k: int(upgrades.get(k, 0))
    out = launcher
    if launcher.key in ("gauss", "rail"):
        out = replace(out, v_max_kms=min(0.999 * C_KMS, out.v_max_kms + 0.01 * C_KMS * lv("vmax")),
                      max_mass_kg=out.max_mass_kg * 1.5 ** lv("masse"),
                      reload_s=out.reload_s * 0.8 ** lv("cadence"))
    if launcher.key == "laser":
        out = replace(out, max_mass_kg=out.max_mass_kg * 1.5 ** lv("masse"),
                      reload_s=out.reload_s * 0.8 ** lv("cadence"))
    if launcher.key == "canon":
        out = replace(out, max_mass_kg=out.max_mass_kg * 2.0 ** lv("canon_energie"),
                      reload_s=out.reload_s * 0.8 ** lv("cadence"))
    return out


def energy_cap_j(upgrades: dict) -> float:
    """Énergie cinétique maximale par tir du canon interplanétaire."""
    return 2e18 * 4.0 ** int(upgrades.get("canon_energie", 0))
