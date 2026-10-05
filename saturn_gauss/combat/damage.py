"""Modèle de dégâts : bouclier d'abord, puis coque composant par composant."""
import numpy as np

from .ammo import RHO_ARMOR, Ammo, penetration_m
from .ships import Ship


def apply_hit(ship: Ship, idx: int, ammo: Ammo, energy_j: float, length_m: float, mass_kg: float = 1.0) -> dict:
    """Applique l'impact d'un projectile (énergie `energy_j`) sur le composant `idx`."""
    rep = {"shield_absorbed": 0.0, "components": [], "penetrated": False, "text": ""}
    E = energy_j
    if ammo.bomb:
        E += ammo.specific_yield * mass_kg
    frac = 1.0
    shield_dmg = E * ammo.shield_mult
    if ship.shield_online and ship.shield > 0:
        if ship.shield >= shield_dmg:
            ship.shield -= shield_dmg
            rep["shield_absorbed"] = 1.0
            rep["text"] = f"Le bouclier absorbe tout ({shield_dmg:.2e} J ; reste {ship.shield:.2e} J)."
            _crew(ship, ammo, mass_kg, ammo.shield_mult if ammo.shield_mult < 1 else 0.0)
            return rep
        frac = 1.0 - ship.shield / shield_dmg
        rep["shield_absorbed"] = 1.0 - frac
        ship.shield = 0.0
    comp = ship.comps[idx]
    pen = penetration_m(ammo, length_m)
    if ammo.pen_mult <= 0:
        ratio, penetrated = 0.6, False        # faisceau : ablation de surface
    else:
        ratio = min(1.0, pen / comp.armor_m)
        penetrated = pen >= comp.armor_m
    dmg = E * frac * ammo.hull_mult * ratio ** 2
    if penetrated:
        dmg *= ammo.internal_mult
    rep["penetrated"] = penetrated
    _damage(comp, dmg, rep)
    if ammo.splash_m > 0 and (penetrated or ammo.blast_eff > 0 or ammo.key == "dirty"):
        for j, other in enumerate(ship.comps):
            if j == idx or not other.alive:
                continue
            d = np.linalg.norm(other.center - comp.center) - 0.5 * (np.linalg.norm(other.size) + np.linalg.norm(comp.size)) / 2
            if d <= ammo.splash_m:
                _damage(other, 0.4 * dmg, rep)
    _crew(ship, ammo, mass_kg, frac)
    rep["text"] = (f"Pénétration {pen:.2f} m / blindage {comp.armor_m:.2f} m "
                   f"({'perce' if penetrated else 'ne perce pas'}). "
                   + ("; ".join(f"{n} : -{d:.2e} J{' DÉTRUIT' if k else ''}" for n, d, k in rep["components"])))
    return rep


def _damage(comp, dmg, rep):
    before = comp.alive
    comp.hp -= dmg
    rep["components"].append((comp.name, dmg, before and not comp.alive))


def _crew(ship, ammo, mass_kg, frac):
    if ammo.crew_mult > 0:
        ship.crew = max(0.0, ship.crew - ammo.crew_mult * frac * min(1.0, mass_kg / 6.0) * 0.5)


def apply_blast(ship: Ship, energy_j: float) -> dict:
    """Explosion proche : l'énergie se répartit sur les composants selon leur volume."""
    rep = {"shield_absorbed": 0.0, "components": []}
    E = energy_j
    if ship.shield_online and ship.shield > 0:
        if ship.shield >= E:
            ship.shield -= E
            rep["shield_absorbed"] = 1.0
            return rep
        rep["shield_absorbed"] = ship.shield / E
        E -= ship.shield
        ship.shield = 0.0
    alive = [c for c in ship.comps if c.alive]
    tot = sum(c.volume for c in alive)
    for c in alive:
        _damage(c, E * c.volume / tot, rep)
    return rep
