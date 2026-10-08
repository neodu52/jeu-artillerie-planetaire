"""Graphes matplotlib intégrés : distance à la cible et approche finale d'un tir interplanétaire."""
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..constants import DAY_S
from . import theme


class ShotCharts(FigureCanvasQTAgg):
    def __init__(self, parent=None):
        fig = Figure(figsize=(7, 3), facecolor=theme.BG)
        super().__init__(fig)
        self.setParent(parent)
        self.ax1 = fig.add_subplot(1, 2, 1)
        self.ax2 = fig.add_subplot(1, 2, 2)
        self.clear()

    def _style(self, ax, title):
        ax.set_facecolor("#0e1424")
        ax.set_title(title, color="white", fontsize=9)
        ax.tick_params(colors="#aab", labelsize=7)
        for s in ax.spines.values():
            s.set_color("#445")

    def clear(self):
        for ax, t in ((self.ax1, "Distance à la cible"), (self.ax2, "Approche finale")):
            ax.clear()
            self._style(ax, t)
        self.figure.tight_layout()
        self.draw_idle()

    def show_result(self, system, res, planet=None, radius=None, target=None):
        ts = res.times
        k = max(1, len(ts) // 1500)
        ts, pts = ts[::k], res.positions[::k]
        if planet:
            ip = system.index(planet) - 1
            ref = system.planet_states(ts)[0][:, ip, :]
        elif target is not None:
            sel = np.linspace(0, len(ts) - 1, min(len(ts), 500)).astype(int)
            ts, pts = ts[sel], pts[sel]
            ref = np.array([target.point(system, t).pos for t in ts])
        else:
            return
        rel = pts - ref
        dist = np.linalg.norm(rel, axis=1)
        days = (ts - ts[0]) / DAY_S
        unit, div = ("jours", 1.0) if days[-1] > 3 else ("heures", 1 / 24.0)
        self.ax1.clear()
        self.ax2.clear()
        self._style(self.ax1, "Distance à la cible (km)")
        self._style(self.ax2, "Approche finale (km, repère de la cible)")
        self.ax1.semilogy(days / div, np.maximum(dist, 1e-3), color="#4cc9f0")
        if radius:
            self.ax1.axhline(radius, color="#ff6b4a", ls="--", lw=1)
        self.ax1.set_xlabel(f"{unit} depuis le tir", color="#aab", fontsize=8)
        near = dist < max((15 * radius) if radius else 0, 6 * float(dist.min()), 1.0)
        if near.sum() >= 2:
            self.ax2.plot(rel[near, 0], rel[near, 1], color="#4cc9f0")
            if radius:
                from matplotlib.patches import Circle
                self.ax2.add_patch(Circle((0, 0), radius, color="#ff6b4a", alpha=0.8))
            self.ax2.plot(*rel[-1, :2], "x", color="white")
        self.ax2.set_aspect("equal", adjustable="datalim")
        self.figure.tight_layout()
        self.draw_idle()
