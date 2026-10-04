"""Solveur du problème de Lambert (variables universelles, révolution < 1)."""
import math

import numpy as np


def _stumpff(z):
    z = np.asarray(z, dtype=float)
    C = np.empty_like(z)
    S = np.empty_like(z)
    pos, neg = z > 1e-8, z < -1e-8
    mid = ~(pos | neg)
    s = np.sqrt(z[pos])
    C[pos] = (1 - np.cos(s)) / z[pos]
    S[pos] = (s - np.sin(s)) / s ** 3
    s = np.sqrt(-z[neg])
    C[neg] = (np.cosh(s) - 1) / (-z[neg])
    S[neg] = (np.sinh(s) - s) / s ** 3
    C[mid] = 0.5 - z[mid] / 24.0
    S[mid] = 1.0 / 6.0 - z[mid] / 120.0
    return C, S


_GRID = np.concatenate([np.linspace(-120.0, -1.0, 60), np.linspace(-1.0, 4 * np.pi ** 2 - 1e-6, 120)])


def lambert(r1, r2, tof, mu, prograde=True):
    """Retourne (v1, v2) pour aller de r1 à r2 en ``tof`` secondes, ou None.

    Les vecteurs sont en km, km/s ; mu en km^3/s^2. Sens direct autour de +z.
    """
    r1 = np.asarray(r1, float)
    r2 = np.asarray(r2, float)
    n1, n2 = np.linalg.norm(r1), np.linalg.norm(r2)
    cosd = np.clip(np.dot(r1, r2) / (n1 * n2), -1, 1)
    dth = np.arccos(cosd)
    cz = np.cross(r1, r2)[2]
    if (prograde and cz < 0) or (not prograde and cz >= 0):
        dth = 2 * np.pi - dth
    A = np.sin(dth) * np.sqrt(n1 * n2 / (1 - np.cos(dth)))
    if abs(A) < 1e-9:
        return None
    sm = np.sqrt(mu)

    def tof_of(z):
        C, S = _stumpff(z)
        y = n1 + n2 + A * (z * S - 1) / np.sqrt(C)
        ok = y > 0
        yy = np.where(ok, y, 1.0)
        t = ((yy / C) ** 1.5 * S + A * np.sqrt(yy)) / sm
        return np.where(ok, t, np.nan), y

    tg, _ = tof_of(_GRID)
    f = tg - tof
    ok = np.isfinite(f[:-1]) & np.isfinite(f[1:]) & (f[:-1] * f[1:] <= 0)
    if not ok.any():
        return None
    idx = int(np.argmax(ok))
    def tof_scalar(z):
        if z > 1e-8:
            q = math.sqrt(z)
            C, S = (1 - math.cos(q)) / z, (q - math.sin(q)) / q ** 3
        elif z < -1e-8:
            q = math.sqrt(-z)
            C, S = (math.cosh(q) - 1) / (-z), (math.sinh(q) - q) / q ** 3
        else:
            C, S = 0.5 - z / 24.0, 1.0 / 6.0 - z / 120.0
        y = n1 + n2 + A * (z * S - 1) / math.sqrt(C)
        if y <= 0:
            return float("nan"), y
        return ((y / C) ** 1.5 * S + A * math.sqrt(y)) / sm, y

    lo, hi = float(_GRID[idx]), float(_GRID[idx + 1])
    flo = f[idx]
    for _ in range(50):
        mid = 0.5 * (lo + hi)
        fm = tof_scalar(mid)[0] - tof
        if (fm < 0) == (flo < 0):
            lo, flo = mid, fm
        else:
            hi = mid
    z = 0.5 * (lo + hi)
    y = tof_scalar(z)[1]
    fl = 1 - y / n1
    g = A * np.sqrt(y / mu)
    gd = 1 - y / n2
    v1 = (r2 - fl * r1) / g
    v2 = (gd * r2 - r1) / g
    return v1, v2
