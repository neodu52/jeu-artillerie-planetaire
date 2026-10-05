"""Propagation képlérienne à deux corps (variables universelles, Curtis alg. 3.3)."""
import math

import numpy as np


def _cs(z):
    if z > 1e-8:
        s = math.sqrt(z)
        return (1 - math.cos(s)) / z, (s - math.sin(s)) / s ** 3
    if z < -1e-8:
        s = math.sqrt(-z)
        return (math.cosh(s) - 1) / (-z), (math.sinh(s) - s) / s ** 3
    return 0.5 - z / 24 + z * z / 720, 1 / 6 - z / 120 + z * z / 5040


def propagate(r0, v0, dt, mu):
    """État (r, v) après dt secondes (dt < 0 autorisé) sur l'orbite képlérienne de (r0, v0)."""
    r0 = np.asarray(r0, float)
    v0 = np.asarray(v0, float)
    if dt == 0:
        return r0.copy(), v0.copy()
    rn0 = float(np.linalg.norm(r0))
    sm = math.sqrt(mu)
    rv = float(r0 @ v0)
    alpha = 2.0 / rn0 - float(v0 @ v0) / mu
    if alpha > 1e-14:
        chi = sm * alpha * dt
    else:
        chi = math.copysign(1.0, dt) * min(abs(dt) * sm / rn0, 1e3 * rn0 ** 0.5 / (abs(alpha) ** 0.5 + 1e-30)) \
            if alpha == 0 else dt * sm / rn0
    chi = float(chi)
    for _ in range(200):
        z = alpha * chi * chi
        C, S = _cs(z)
        F = rv / sm * chi * chi * C + (1 - alpha * rn0) * chi ** 3 * S + rn0 * chi - sm * dt
        dF = rv / sm * chi * (1 - z * S) + (1 - alpha * rn0) * chi * chi * C + rn0
        step = F / dF
        # amortissement pour éviter les divergences sur les hyperboles très ouvertes
        if abs(step) > 0.5 * abs(chi) + 1e3:
            step = math.copysign(0.5 * abs(chi) + 1e3, step)
        chi -= step
        if abs(step) < 1e-10 * (1.0 + abs(chi)):
            break
    z = alpha * chi * chi
    C, S = _cs(z)
    f = 1 - chi * chi / rn0 * C
    g = dt - chi ** 3 * S / sm
    r = f * r0 + g * v0
    rn = float(np.linalg.norm(r))
    fd = sm / (rn * rn0) * (alpha * chi ** 3 * S - chi)
    gd = 1 - chi * chi / rn * C
    return r, fd * r0 + gd * v0
