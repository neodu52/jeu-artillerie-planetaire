"""Moteur 3D minimal (QPainter) : caméra orbitale, projection orthographique ou perspective.

Rotation : bouton gauche ; zoom : molette ; double-clic : vue par défaut.
"""
import math

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

from . import theme


class View3D(QWidget):
    clicked = Signal(float, float)            # clic sans glisser (coordonnées écran)

    def __init__(self, perspective=False, parent=None):
        super().__init__(parent)
        self.perspective = perspective
        self.az, self.el = 0.7, 0.55
        self.scale = 1.0                       # pixels par unité au niveau de la cible
        self.cam_dist = 1.0                    # (perspective) distance caméra-cible en unités
        self.target = np.zeros(3)
        self._drag = None
        self._moved = False
        self.setMinimumSize(280, 220)
        self.setMouseTracking(True)
        self.setCursor(Qt.OpenHandCursor)

    # ---- caméra
    def basis(self):
        cp = np.array([math.cos(self.el) * math.cos(self.az), math.cos(self.el) * math.sin(self.az), math.sin(self.el)])
        f = -cp
        right = np.cross(f, [0.0, 0.0, 1.0])
        if np.linalg.norm(right) < 1e-9:
            right = np.array([1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        return f, right, np.cross(right, f)

    def set_view_direction(self, d):
        """Oriente la caméra pour regarder dans la direction d (vecteur du monde)."""
        d = np.asarray(d, float) / np.linalg.norm(d)
        self.el = float(np.clip(math.asin(np.clip(-d[2], -1, 1)), -1.55, 1.55))
        self.az = math.atan2(-d[1], -d[0])
        self.update()

    def project(self, P):
        """Points (N,3) -> (sx, sy, profondeur, facteur d'échelle en px/unité)."""
        P = np.atleast_2d(np.asarray(P, float)) - self.target
        f, r, u = self.basis()
        x, y, z = P @ r, P @ u, P @ f
        if self.perspective:
            depth = np.maximum(self.cam_dist + z, 0.05 * self.cam_dist)
            k = self.scale * self.cam_dist / depth
        else:
            k = np.full(len(P), self.scale)
        return self.width() / 2 + x * k, self.height() / 2 - y * k, z, k

    # ---- souris
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag, self._moved = e.position(), False
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            d = e.position() - self._drag
            if abs(d.x()) + abs(d.y()) > 2:
                self._moved = True
            self.az -= d.x() * 0.01
            self.el = float(np.clip(self.el + d.y() * 0.01, -1.55, 1.55))
            self._drag = e.position()
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not self._moved:
                self.clicked.emit(e.position().x(), e.position().y())
            self._drag = None
            self.setCursor(Qt.OpenHandCursor)

    def wheelEvent(self, e):
        self.scale *= 1.15 ** (e.angleDelta().y() / 120.0)
        self.update()

    def mouseDoubleClickEvent(self, e):
        self.reset_view()

    def reset_view(self):          # surchargé
        self.update()

    # ---- aides de dessin
    @staticmethod
    def poly(xs, ys):
        return QPolygonF([QPointF(float(a), float(b)) for a, b in zip(xs, ys)])

    def draw_path(self, p: QPainter, pts, color, width=1.0, style=Qt.SolidLine, alpha=255):
        if len(pts) < 2:
            return
        sx, sy, _, _ = self.project(pts)
        c = QColor(color)
        c.setAlpha(alpha)
        pen = QPen(c, width, style)
        pen.setCosmetic(True)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline(self.poly(sx, sy))

    def draw_label(self, p, x, y, text, color=theme.TEXT, dx=7, dy=-6):
        p.setPen(QColor(color))
        p.drawText(QPointF(x + dx, y + dy), text)
