"""Vue 3D d'un vaisseau : composants en boîtes ombrées (couleur = intégrité), bouclier, sélection."""
import numpy as np
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF

from ..combat.ships import Ship
from . import theme
from .view3d import View3D

_FACES = [((0, 1, 3, 2), (-1, 0, 0)), ((4, 6, 7, 5), (1, 0, 0)), ((0, 4, 5, 1), (0, -1, 0)),
          ((2, 3, 7, 6), (0, 1, 0)), ((0, 2, 6, 4), (0, 0, -1)), ((1, 5, 7, 3), (0, 0, 1))]
_CORNER = np.array([[(-1 if (i >> 2) & 1 == 0 else 1), (-1 if (i >> 1) & 1 == 0 else 1),
                     (-1 if i & 1 == 0 else 1)] for i in range(8)], float)


def hp_color(frac: float) -> QColor:
    frac = max(0.0, min(1.0, frac))
    a, b, c = np.array([255, 77, 109]), np.array([255, 183, 3]), np.array([46, 204, 113])
    v = a + (b - a) * (frac / 0.5) if frac < 0.5 else b + (c - b) * ((frac - 0.5) / 0.5)
    return QColor(int(v[0]), int(v[1]), int(v[2]))


class ShipView(View3D):
    def __init__(self, career, parent=None):
        super().__init__(perspective=True, parent=parent)
        self.k = career
        self.ship = None
        self.selected = None
        self.hit_comp = None
        self._polys = []
        self.extent = 100.0
        self.az, self.el = 2.6, 0.45
        self.setMinimumSize(380, 300)

    def set_ship(self, ship, selected=None):
        if ship is not self.ship:
            self.ship = ship
            L = np.max(np.abs([c.center for c in ship.comps]) + [c.size / 2 for c in ship.comps]) if ship else 100.0
            self.extent = float(L)
            self._fit()
        self.selected = selected
        self.update()

    def _fit(self):
        self.cam_dist = 3.2 * self.extent
        self.scale = min(self.width(), self.height()) / (2.1 * self.extent)

    def resizeEvent(self, e):
        self._fit()

    def reset_view(self):
        self.az, self.el = 2.6, 0.45
        self._fit()
        self.update()

    def view_from_shooter(self):
        """Regarde le vaisseau depuis le tireur courant."""
        if self.ship is None:
            return
        k = self.k
        origin, _ = k.shooter.rel_state(k.t)
        pos, vel = self.ship.state(k.t)
        A = Ship.axes(vel)
        d_world = pos - origin
        self.set_view_direction(A.T @ d_world)           # dans le repère du vaisseau
        self.update()

    def flash_hit(self, comp_index):
        from PySide6.QtCore import QTimer
        self.hit_comp = comp_index
        QTimer.singleShot(2500, self._clear_hit)
        self.update()

    def _clear_hit(self):
        self.hit_comp = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#080c16"))
        s = self.ship
        self._polys = []
        if s is None:
            p.setPen(QColor(theme.DIM))
            p.drawText(self.rect(), Qt.AlignCenter, "Aucun vaisseau ciblé")
            return
        f, r, u = self.basis()
        # bouclier
        cx, cy, _, k0 = self.project(np.zeros(3))
        frac = s.shield / s.shield_max if s.shield_max else 0.0
        if s.shield_online and frac > 0:
            rad = self.extent * 0.95 * k0[0]
            c = QColor(76, 201, 240, int(18 + 55 * frac))
            p.setPen(QPen(QColor(76, 201, 240, int(60 + 120 * frac)), 1.5))
            p.setBrush(c)
            p.drawEllipse(QPointF(cx[0], cy[0]), rad, rad * 0.8)
        faces = []
        for i, comp in enumerate(s.comps):
            corners = comp.center + _CORNER * (comp.size / 2)
            sx, sy, z, _ = self.project(corners)
            base = hp_color(comp.hp / comp.hp_max) if comp.alive else QColor(58, 62, 78)
            for idx, n in _FACES:
                n = np.array(n, float)
                ncz = n @ f
                if ncz >= 0:
                    continue                      # face arrière
                nc = np.array([n @ r, n @ u, ncz])
                shade = 0.42 + 0.58 * max(0.0, float(nc @ np.array([-0.4, 0.5, -0.75]) / 1.0))
                col = QColor(int(base.red() * shade), int(base.green() * shade), int(base.blue() * shade))
                faces.append((float(np.mean(z[list(idx)])), idx, sx, sy, col, i))
        faces.sort(key=lambda x: -x[0])
        for depth, idx, sx, sy, col, i in faces:
            poly = QPolygonF([QPointF(sx[j], sy[j]) for j in idx])
            outline = QPen(QColor("#10162a"), 1)
            if i == self.selected:
                outline = QPen(QColor("#ffffff"), 2.6)
            elif i == self.hit_comp:
                outline = QPen(QColor(theme.WARN), 2.6)
            p.setPen(outline)
            p.setBrush(col)
            p.drawPolygon(poly)
            self._polys.append((depth, poly, i))
        font = QFont(p.font())
        font.setPointSize(9)
        font.setBold(True)
        p.setFont(font)
        for i, comp in enumerate(s.comps):
            sx, sy, z, _ = self.project(comp.center)
            p.setPen(QColor("#000000"))
            p.drawText(QPointF(sx[0] - 4, sy[0] + 5), str(i + 1))
            p.setPen(QColor("#ffffff"))
            p.drawText(QPointF(sx[0] - 5, sy[0] + 4), str(i + 1))
        # axe « avant »
        nose = np.array([self.extent * 1.0, 0, 0])
        nx, ny, _, _ = self.project(nose)
        p.setPen(QPen(QColor(theme.ACCENT), 1.5, Qt.DashLine))
        p.drawLine(QPointF(cx[0], cy[0]), QPointF(nx[0], ny[0]))
        p.setPen(QColor(theme.ACCENT))
        p.drawText(QPointF(nx[0] + 4, ny[0]), "avant")
        p.setPen(QColor(theme.TEXT))
        p.drawText(10, 20, f"{s.name} — {s.spec.name} — {s.status.upper()}")
        p.setPen(QColor(theme.DIM))
        p.drawText(10, 38, f"bouclier {100 * frac:.0f} % · intégrité {100 * s.hp_fraction:.0f} % · équipage {100 * s.crew:.0f} %")
        p.drawText(10, self.height() - 10, "clic : désigner un composant · glisser : tourner · molette : zoom · double-clic : réinit.")

    def pick(self, x, y):
        for depth, poly, i in sorted(self._polys, key=lambda t: t[0]):      # le plus proche d'abord
            if poly.containsPoint(QPointF(x, y), Qt.OddEvenFill):
                return i
        return None
