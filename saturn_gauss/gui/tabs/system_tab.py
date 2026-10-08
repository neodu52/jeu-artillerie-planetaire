"""Onglet Système solaire : vue 3D animée, tableau des planètes, rotation propre."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QSplitter,
                               QVBoxLayout, QWidget)

from ...constants import AU_KM
from ..common import cell, new_table, title
from ..system_view import SolarSystemView


class SystemTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)
        self.view = SolarSystemView(win.k)
        split.addWidget(self.view)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.addWidget(title("Système solaire"))
        box = QGroupBox("Vue")
        bl = QVBoxLayout(box)
        r1 = QHBoxLayout()
        for text, fn in (("Complet", lambda: self.view.set_extent(32)), ("Planètes externes", lambda: self.view.set_extent(12)),
                         ("Interne", lambda: self.view.set_extent(1.8))):
            b = QPushButton(text)
            b.clicked.connect(fn)
            r1.addWidget(b)
        bl.addLayout(r1)
        r2 = QHBoxLayout()
        for text, name in (("Dessus", "top"), ("Profil", "side"), ("3D", "3d")):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, n=name: self.view.preset(n))
            r2.addWidget(b)
        bl.addLayout(r2)
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Centrer sur"))
        self.follow = QComboBox()
        self.follow.addItem("Soleil", None)
        for b in win.k.system.bodies[1:]:
            self.follow.addItem(b.name, b.name)
        self.follow.currentIndexChanged.connect(self._follow)
        r3.addWidget(self.follow, 1)
        bl.addLayout(r3)
        for attr, text in (("show_orbits", "Orbites"), ("show_labels", "Étiquettes"), ("show_axes", "Axes de rotation"),
                           ("show_grid", "Grille (1, 5, 10, 20, 30 UA)")):
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.toggled.connect(lambda v, a=attr: (setattr(self.view, a, v), self.view.update()))
            bl.addWidget(cb)
        rl.addWidget(box)
        rl.addWidget(title("Planètes"))
        self.table = new_table(["Corps", "r (UA)", "v (km/s)", "Rotation (h)", "Inclinaison axe"], select=False)
        rl.addWidget(self.table, 1)
        rl.addWidget(QLabel("Le point blanc de chaque planète marque son méridien origine :\n"
                            "en accélérant le temps, vous voyez les planètes tourner sur elles-mêmes."))
        split.addWidget(right)
        split.setSizes([800, 380])

    def _follow(self):
        self.view.follow = self.follow.currentData()
        self.view.update()

    def refresh(self):
        k = self.win.k
        self.view.k = k
        P, V = k.system.states(k.t)
        bodies = k.system.bodies
        self.table.setRowCount(len(bodies) - 1)
        from ...solarsystem.rotation import pole_vector
        for i, b in enumerate(bodies[1:], start=1):
            tilt = np.degrees(np.arccos(np.clip(pole_vector(b)[2], -1, 1)))
            vals = (b.name, f"{np.linalg.norm(P[i]) / AU_KM:.3f}", f"{np.linalg.norm(V[i]):.2f}",
                    f"{b.rotation_period_h:,.2f}".replace(",", " "), f"{tilt:.1f}°")
            for j, v in enumerate(vals):
                self.table.setItem(i - 1, j, cell(v, b.color if j == 0 else None, "r" if j else None))
        self.view.update()
