"""Tir en ligne droite sur un vaisseau : prise en compte du déplacement de la cible,
détection du composant touché, calcul de visée et retour d'information sur les écarts."""
import numpy as np

from ..ballistics.cannon import direction_angles
from .geometry import ray_box, segment_hits_sphere
from .ships import Ship

SATURN_RADIUS_KM = 58_232.0


def _arrival(ship: Ship, origin, t, vp):
    """Durée de vol vers le centre du vaisseau (la cible bouge pendant ce temps)."""
    pos, _ = ship.state(t)
    tau = np.linalg.norm(pos - origin) / vp
    for _ in range(4):
        pos, v = ship.state(t + tau)
        tau = np.linalg.norm(pos - origin) / vp
    pos, v = ship.state(t + tau)
    return tau, pos, v


def locate_hit(origin, direction, vp, ships, t):
    """Premier composant touché par le rayon : (distance km, vaisseau, indice, durée de vol) ou None."""
    best = None
    for ship in ships:
        if ship.destroyed:
            continue
        tau, pos, v = _arrival(ship, origin, t, vp)
        A = Ship.axes(v)
        for i, c in enumerate(ship.comps):
            if not c.alive:
                continue
            cen, AA, half = ship.comp_pose(i, pos, A)
            r = ray_box(origin, direction, cen, AA, half)
            if r is not None and r[0] >= 0 and (best is None or r[0] < best[0]):
                best = (r[0], ship, i, tau)
    if best is not None and segment_hits_sphere(origin, origin + direction * best[0], np.zeros(3), SATURN_RADIUS_KM):
        return ("saturne", None, None, None)
    return best


def component_world(ship: Ship, idx: int, origin, t, vp):
    """Position du composant à l'instant d'arrivée du projectile : (centre, vitesse, tau, axes)."""
    tau, _, _ = _arrival(ship, origin, t, vp)
    pos, v = ship.state(t + tau)
    A = Ship.axes(v)
    cen, _, _ = ship.comp_pose(idx, pos, A)
    return cen, v, tau, A


def solve_aim(origin, ship: Ship, idx: int, t, vp):
    """Direction exacte (lon, lat en degrés) qui touche le centre du composant, durée de vol, distance."""
    tau = np.linalg.norm(ship.state(t)[0] - origin) / vp
    for _ in range(6):
        pos, v = ship.state(t + tau)
        cen, _, _ = ship.comp_pose(idx, pos, Ship.axes(v))
        tau = np.linalg.norm(cen - origin) / vp
    pos, v = ship.state(t + tau)
    cen, _, _ = ship.comp_pose(idx, pos, Ship.axes(v))
    d = cen - origin
    dist = float(np.linalg.norm(d))
    lon, lat = direction_angles(d)
    return lon, lat, tau, dist


def visibility(origin, ship: Ship, idx: int, t, vp):
    """(visible, raison) : le composant est-il atteignable en ligne droite depuis `origin` ?"""
    lon, lat, tau, dist = solve_aim(origin, ship, idx, t, vp)
    from ..ballistics.cannon import direction_vector
    d = direction_vector(lon, lat)
    hit = locate_hit(origin, d, vp, [ship], t)
    if hit is None:
        return False, "hors portée géométrique"
    if hit[0] == "saturne":
        return False, "masqué par Saturne"
    if hit[2] != idx:
        return False, f"masqué par : {ship.comps[hit[2]].name}"
    return True, "dégagé"


def miss_report(origin, direction, ship: Ship, idx: int, t, vp):
    """Écart entre le rayon et le centre du composant visé, exprimé dans le repère du vaisseau (m)."""
    cen, v, tau, A = component_world(ship, idx, origin, t, vp)
    s = (cen - origin) @ direction
    closest = origin + s * direction
    off = (closest - cen) * 1000.0                  # m
    local = A.T @ off                               # x avant, y gauche, z haut
    return {"distance_m": float(np.linalg.norm(off)), "avant_m": float(local[0]),
            "gauche_m": float(local[1]), "haut_m": float(local[2]), "tau_s": float(tau)}
