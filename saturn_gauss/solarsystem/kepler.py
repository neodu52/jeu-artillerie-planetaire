"""Éphémérides képlériennes 3D vectorisées (position + vitesse héliocentriques)."""
import numpy as np

from ..constants import AU_KM, CENTURY_S

_DEG = np.pi / 180.0


class Ephemeris:
    """Position/vitesse de N planètes sur orbites képlériennes inclinées.

    ``t`` : secondes depuis J2000 (scalaire ou tableau).
    Sortie : tableaux de forme (..., N, 3), repère écliptique J2000, Soleil à l'origine.
    """

    def __init__(self, elements):
        el = np.array(elements, dtype=float)
        self.a0, self.a1 = el[:, 0] * AU_KM, el[:, 1] * AU_KM
        self.e0, self.e1 = el[:, 2], el[:, 3]
        self.i0, self.i1 = el[:, 4] * _DEG, el[:, 5] * _DEG
        self.L0, self.L1 = el[:, 6] * _DEG, el[:, 7] * _DEG
        self.w0, self.w1 = el[:, 8] * _DEG, el[:, 9] * _DEG
        self.n0, self.n1 = el[:, 10] * _DEG, el[:, 11] * _DEG
        self.Mdot = (self.L1 - self.w1) / CENTURY_S        # rad/s

    def states(self, t, velocity=True):
        T = np.asarray(t, dtype=float)[..., None] / CENTURY_S
        a = self.a0 + self.a1 * T
        e = self.e0 + self.e1 * T
        inc = self.i0 + self.i1 * T
        varpi = self.w0 + self.w1 * T
        node = self.n0 + self.n1 * T
        M = self.L0 + self.L1 * T - varpi
        M = (M + np.pi) % (2 * np.pi) - np.pi

        E = M + e * np.sin(M)
        for _ in range(7):
            E = E - (E - e * np.sin(E) - M) / (1.0 - e * np.cos(E))
        cE, sE = np.cos(E), np.sin(E)
        b = np.sqrt(1.0 - e * e)
        xp = a * (cE - e)
        yp = a * b * sE

        om = varpi - node
        co, so = np.cos(om), np.sin(om)
        cn, sn = np.cos(node), np.sin(node)
        ci, si = np.cos(inc), np.sin(inc)
        r11 = co * cn - so * sn * ci
        r12 = -so * cn - co * sn * ci
        r21 = co * sn + so * cn * ci
        r22 = -so * sn + co * cn * ci
        r31 = so * si
        r32 = co * si

        pos = np.stack([r11 * xp + r12 * yp, r21 * xp + r22 * yp, r31 * xp + r32 * yp], axis=-1)
        if not velocity:
            return pos, None
        Edot = self.Mdot / (1.0 - e * cE)
        vxp = -a * sE * Edot
        vyp = a * b * cE * Edot
        vel = np.stack([r11 * vxp + r12 * vyp, r21 * vxp + r22 * vyp, r31 * vxp + r32 * vyp], axis=-1)
        return pos, vel
