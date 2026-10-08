"""Vue 3D du système solaire : orbites, planètes, rotation propre, trajectoires de tir."""
import math

import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen

from ..constants import AU_KM, YEAR_S
from ..solarsystem.rotation import body_to_ecliptic
from ..timeutils import format_date
from . import theme
from .view3d import View3D

PLANET_PX = {"Soleil": 8, "Mercure": 3, "Vénus": 4, "Terre": 4, "Mars": 3.5, "Jupiter": 7,
             "Saturne": 6.5, "Uranus": 5, "Neptune": 5}


class SolarSystemView(View3D):
    def __init__(self, career, parent=None):
        super().__init__(perspective=False, parent=parent)
        self.k = career
        self.show_orbits = self.show_labels = self.show_axes = self.show_grid = True
        self.follow = None
        self.extent_au = 32.0
        self.trajectories = []           # [(positions Nx3 héliocentriques, couleur)]
        self.markers = []                # [(position, étiquette, couleur)]
        self._orbits, self._orbit_t = {}, None
        self._auto = True
        self.reset_view()

    # ---- vues
    def reset_view(self):
        self.az, self.el = 0.7, 0.9
        self.set_extent(self.extent_au if self.extent_au else 32.0)

    def set_extent(self, au):
        self.extent_au = au
        self._auto = True
        self._fit()
        self.update()

    def _fit(self):
        self.scale = max(min(self.width(), self.height()) / 2 * 0.92, 50) / (self.extent_au * AU_KM)

    def resizeEvent(self, e):
        if self._auto:
            self._fit()

    def wheelEvent(self, e):
        self._auto = False
        super().wheelEvent(e)

    def preset(self, name):
        if name == "top":
            self.az, self.el = 0.0, 1.5
        elif name == "side":
            self.az, self.el = 0.0, 0.0
        elif name == "3d":
            self.az, self.el = 0.7, 0.55
        self.update()

    def set_trajectory(self, positions, color="#4cc9f0"):
        self.trajectories = [(np.asarray(positions), color)] if positions is not None and len(positions) else []
        self.update()

    # ---- dessin
    def _orbit_paths(self):
        t = self.k.t
        if self._orbit_t is None or abs(t - self._orbit_t) > 0.25 * YEAR_S:
            self._orbits = {b.name: self.k.system.orbit_path(b.name, t, 260) for b in self.k.system.bodies[1:]}
            self._orbit_t = t
        return self._orbits

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        sysm, t = self.k.system, self.k.t
        P = sysm.positions(t)
        self.target = sysm.position(self.follow, t) if self.follow else np.zeros(3)
        f, r, u = self.basis()
        # grille
        if self.show_grid:
            th = np.linspace(0, 2 * math.pi, 120)
            for au in (1, 5, 10, 20, 30):
                ring = np.column_stack([np.cos(th), np.sin(th), np.zeros_like(th)]) * au * AU_KM
                self.draw_path(p, ring, "#3a4668", 0.7, Qt.DotLine, 130)
            for ang in (0, 90, 180, 270):
                a = math.radians(ang)
                self.draw_path(p, np.array([[0, 0, 0], [math.cos(a), math.sin(a), 0]]) * 32 * AU_KM, "#2b3552", 0.6, Qt.DotLine, 120)
        if self.show_orbits:
            for b in sysm.bodies[1:]:
                self.draw_path(p, self._orbit_paths()[b.name], b.color, 1.0, Qt.SolidLine, 150)
        for pts, col in self.trajectories:
            self.draw_path(p, pts, col, 2.0)
        # corps
        sx, sy, depth, _ = self.project(P)
        font = QFont(p.font())
        font.setPointSize(9)
        p.setFont(font)
        for i, b in enumerate(sysm.bodies):
            px = PLANET_PX[b.name]
            col = QColor(b.color)
            p.setPen(QPen(col.lighter(150), 1))
            p.setBrush(col)
            p.drawEllipse(QPointF(sx[i], sy[i]), px, px)
            if i > 0 and self.show_axes:
                M = body_to_ecliptic(b, t)
                pole, pm = M[:, 2], M[:, 0]
                dpx = lambda v: np.array([v @ r, -(v @ u)])
                a = dpx(pole)
                a = a / (np.linalg.norm(a) + 1e-9) * px * 1.9 * max(np.linalg.norm(dpx(pole)), 0.35)
                p.setPen(QPen(QColor("#ffffff"), 1.2))
                p.drawLine(QPointF(sx[i] - a[0], sy[i] - a[1]), QPointF(sx[i] + a[0], sy[i] + a[1]))
                m = dpx(pm) * px
                front = (pm @ f) < 0
                p.setPen(Qt.NoPen)
                p.setBrush(QColor("#ffffff" if front else "#666e88"))
                p.drawEllipse(QPointF(sx[i] + m[0], sy[i] + m[1]), 1.8, 1.8)
            if self.show_labels:
                self.draw_label(p, sx[i], sy[i], b.name, theme.TEXT, dx=px + 4, dy=-px)
        for pos, label, col in self.markers:
            mx, my, _, _ = self.project(pos)
            p.setPen(QPen(QColor(col), 2))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(mx[0], my[0]), 6, 6)
            self.draw_label(p, mx[0], my[0], label, col, dx=9, dy=4)
        # légende
        p.setPen(QColor(theme.DIM))
        p.drawText(10, 20, f"{format_date(t)}   ·   {self.extent_au:g} UA" if self._auto else format_date(t))
        p.drawText(10, self.height() - 10, "glisser : tourner · molette : zoom · double-clic : réinit.  |  trait blanc = axe, point = méridien")
