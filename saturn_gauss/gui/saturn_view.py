"""Vue 3D de l'espace de Saturne : stations, canon, vaisseaux ennemis, trajectoires, tirs."""
import math
import time

import numpy as np
from PySide6.QtCore import QPointF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QRadialGradient

from ..contracts import DefenseOp
from ..solarsystem.rotation import pole_vector
from . import theme
from .view3d import View3D

SATURN_R = 58_232.0


class SaturnView(View3D):
    station_picked = Signal(int)
    ship_picked = Signal(int)

    def __init__(self, career, parent=None):
        super().__init__(perspective=False, parent=parent)
        self.k = career
        self.extent_km = 7e5
        self.flashes = []                  # (a, b, couleur, expiration)
        self._auto = True
        pole = pole_vector(career.system.get("Saturne"))
        self.e1 = career.cannon.e1
        self.e2 = career.cannon.e2
        self.pole = pole
        self.reset_view()

    def reset_view(self):
        self.az, self.el = 0.6, 0.65
        self.set_extent(self.extent_km)

    def set_extent(self, km):
        self.extent_km = km
        self._auto = True
        self._fit()
        self.update()

    def _fit(self):
        self.scale = max(min(self.width(), self.height()) / 2 * 0.9, 50) / self.extent_km

    def resizeEvent(self, e):
        if self._auto:
            self._fit()

    def wheelEvent(self, e):
        self._auto = False
        super().wheelEvent(e)

    def flash(self, a, b, color="#ffb703", seconds=1.5):
        self.flashes.append((np.asarray(a), np.asarray(b), color, time.time() + seconds))
        QTimer.singleShot(int(seconds * 1000) + 50, self.update)
        self.update()

    def battle(self):
        f = self.k.focus
        return f.op.battle if f is not None and isinstance(f.op, DefenseOp) else None

    def _ships(self):
        out = []
        for c in self.k.board:
            if c.kind == "defense" and c.state == "active":
                out += c.op.battle.ships
        return out

    # ---- dessin
    def _circle(self, radius, n=120):
        th = np.linspace(0, 2 * math.pi, n)
        return radius * (np.outer(np.cos(th), self.e1) + np.outer(np.sin(th), self.e2))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor(theme.BG))
        k, t = self.k, self.k.t
        self.target = np.zeros(3)
        # anneaux
        for r, a in ((75e3, 70), (90e3, 110), (105e3, 90), (120e3, 120), (136e3, 70)):
            self.draw_path(p, self._circle(r), "#d8c28a", 1.6, Qt.SolidLine, a)
        # sphère de Saturne
        cx, cy, _, _ = self.project(np.zeros(3))
        rad = SATURN_R * self.scale
        g = QRadialGradient(QPointF(cx[0] - rad * 0.3, cy[0] - rad * 0.3), rad * 1.3)
        g.setColorAt(0, QColor("#f3e3b0"))
        g.setColorAt(1, QColor("#7d6a3a"))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawEllipse(QPointF(cx[0], cy[0]), rad, rad)
        # objectif ennemi
        self.draw_path(p, self._circle(1.5e5), theme.BAD, 1.0, Qt.DashLine, 160)
        font = QFont(p.font())
        font.setPointSize(8)
        p.setFont(font)
        # orbites et tireurs
        sel = k.use_idx
        for s in k.shooters:
            r0, _ = s.rel_state(t)
            rr = float(np.linalg.norm(r0))
            period = 2 * math.pi * math.sqrt(rr ** 3 / k.mu)
            path = np.array([s.rel_state(t + period * j / 90.0)[0] for j in range(91)])
            self.draw_path(p, path, theme.ACCENT if s.id == sel else "#35507a", 1.4 if s.id == sel else 0.8, Qt.SolidLine, 160)
        for s in k.shooters:
            r0, _ = s.rel_state(t)
            sx, sy, _, _ = self.project(r0)
            col = QColor(theme.GOOD if s.hp > 0.6 * s.hp_max else theme.WARN if s.online else theme.BAD)
            if s.id == 0:
                p.setPen(QPen(QColor("#ffffff"), 1.5))
                p.setBrush(col)
                p.drawRect(int(sx[0]) - 5, int(sy[0]) - 5, 10, 10)
            else:
                p.setPen(QPen(QColor("#ffffff"), 1.2))
                p.setBrush(col)
                p.save()
                p.translate(sx[0], sy[0])
                p.rotate(45)
                p.drawRect(-4, -4, 8, 8)
                p.restore()
            if s.id == sel:
                p.setPen(QPen(QColor(theme.ACCENT), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(sx[0], sy[0]), 11, 11)
            self.draw_label(p, sx[0], sy[0], "Canon" if s.id == 0 else s.name.split("-")[0], theme.TEXT, 9, -8)
        # vaisseaux
        tsel = k.target_sel[0] if k.target_sel else None
        for ship in self._ships():
            pos, vel = ship.state(t)
            trail = np.array([ship.state(t - j * 120.0)[0] for j in range(0, 40)])
            fut = np.array([ship.state(t + j * 400.0)[0] for j in range(0, 60)])
            self.draw_path(p, trail, "#ff8fa3", 1.4, Qt.SolidLine, 190)
            self.draw_path(p, fut, "#ff8fa3", 1.0, Qt.DotLine, 140)
            sx, sy, _, _ = self.project(pos)
            m = 22
            if not (m < sx[0] < self.width() - m and m < sy[0] < self.height() - m):      # hors cadre : flèche au bord
                cxx, cyy = self.width() / 2, self.height() / 2
                dx, dy = sx[0] - cxx, sy[0] - cyy
                kk = min((self.width() / 2 - m) / max(abs(dx), 1e-9), (self.height() / 2 - m) / max(abs(dy), 1e-9))
                ex, ey = cxx + dx * kk, cyy + dy * kk
                ang = math.degrees(math.atan2(dy, dx))
                p.save()
                p.translate(ex, ey)
                p.rotate(ang)
                p.setPen(QPen(QColor("#ffffff"), 1.2))
                p.setBrush(QColor(theme.BAD))
                from PySide6.QtGui import QPolygonF as _QP
                p.drawPolygon(_QP([QPointF(10, 0), QPointF(-6, 6), QPointF(-6, -6)]))
                p.restore()
                self.draw_label(p, ex - 70 if ex > cxx else ex + 8, ey + (14 if ey < cyy else -8),
                                f"{ship.name} · {np.linalg.norm(pos):,.0f} km".replace(",", " "), "#ffb3c1", 0, 0)
                continue
            col = QColor(theme.BAD if ship.status == "actif" else "#888888")
            p.setPen(QPen(QColor("#ffffff"), 1.2))
            p.setBrush(col)
            vx, vy, _, _ = self.project(pos + vel * 400.0)
            ang = math.degrees(math.atan2(vy[0] - sy[0], vx[0] - sx[0]))
            p.save()
            p.translate(sx[0], sy[0])
            p.rotate(ang)
            from PySide6.QtGui import QPolygonF
            p.drawPolygon(QPolygonF([QPointF(9, 0), QPointF(-6, 5), QPointF(-6, -5)]))
            p.restore()
            if ship.id == tsel:
                p.setPen(QPen(QColor(theme.WARN), 2))
                p.setBrush(Qt.NoBrush)
                p.drawEllipse(QPointF(sx[0], sy[0]), 13, 13)
            self.draw_label(p, sx[0], sy[0], f"{ship.name} ({100 * ship.shield / ship.shield_max:.0f}%)", "#ffb3c1", 11, 4)
        # tirs
        now = time.time()
        self.flashes = [f for f in self.flashes if f[3] > now]
        for a, b, col, _ in self.flashes:
            self.draw_path(p, np.array([a, b]), col, 3.0)
            self.draw_path(p, np.array([a, b]), "#ffffff", 1.0)
        p.setPen(QColor(theme.DIM))
        p.drawText(10, 18, "Saturne  ·  ◆ stations  ■ canon  ▶ vaisseaux  ·  cercle rouge = objectif ennemi (150 000 km)")
        p.drawText(10, self.height() - 10, "clic : sélectionner une station / un vaisseau · glisser : tourner · molette : zoom")

    # ---- sélection
    def mouseReleaseEvent(self, e):
        super().mouseReleaseEvent(e)

    def pick(self, x, y):
        t = self.k.t
        best = None
        for s in self.k.shooters:
            sx, sy, _, _ = self.project(s.rel_state(t)[0])
            d = math.hypot(sx[0] - x, sy[0] - y)
            if d < 14 and (best is None or d < best[0]):
                best = (d, "station", s.id)
        for sh in self._ships():
            sx, sy, _, _ = self.project(sh.state(t)[0])
            d = math.hypot(sx[0] - x, sy[0] - y)
            if d < 16 and (best is None or d < best[0]):
                best = (d, "ship", sh.id)
        return best
