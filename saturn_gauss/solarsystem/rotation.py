"""Rotation propre des corps (orientation du repère lié à la surface)."""
import numpy as np

from ..constants import DAY_S, OBLIQUITY
from .bodies import Body

_c, _s = np.cos(OBLIQUITY), np.sin(OBLIQUITY)
ICRF_TO_ECLIPTIC = np.array([[1, 0, 0], [0, _c, _s], [0, -_s, _c]])


def pole_vector(body: Body) -> np.ndarray:
    """Axe de rotation (pôle nord) dans le repère écliptique."""
    a, d = np.radians(body.pole_ra), np.radians(body.pole_dec)
    p = np.array([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)])
    return ICRF_TO_ECLIPTIC @ p


def body_to_ecliptic(body: Body, t: float) -> np.ndarray:
    """Matrice 3x3 : repère fixé au corps -> repère écliptique, à l'instant t."""
    a = np.radians(body.pole_ra)
    d = np.radians(body.pole_dec)
    W = np.radians(body.w0 + body.w_rate * t / DAY_S)
    p = np.array([np.cos(d) * np.cos(a), np.cos(d) * np.sin(a), np.sin(d)])
    q = np.array([-np.sin(a), np.cos(a), 0.0])
    x = q * np.cos(W) + np.cross(p, q) * np.sin(W)
    y = np.cross(p, x)
    return ICRF_TO_ECLIPTIC @ np.column_stack([x, y, p])


def surface_unit_vector(body: Body, t: float, lat_deg: float, lon_deg: float) -> np.ndarray:
    """Normale à la surface (repère écliptique) du point (lat, lon) à l'instant t."""
    la, lo = np.radians(lat_deg), np.radians(lon_deg)
    nb = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    return body_to_ecliptic(body, t) @ nb


def latlon_from_vector(body: Body, t: float, vec: np.ndarray):
    """Latitude/longitude (deg, longitude Est) du point de surface dans la direction vec."""
    nb = body_to_ecliptic(body, t).T @ (np.asarray(vec) / np.linalg.norm(vec))
    return float(np.degrees(np.arcsin(np.clip(nb[2], -1, 1)))), float(np.degrees(np.arctan2(nb[1], nb[0])))


def great_circle_km(lat1, lon1, lat2, lon2, radius_km: float) -> float:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    c = np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl)
    return float(radius_km * np.arccos(np.clip(c, -1, 1)))
