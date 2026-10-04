"""Graphes matplotlib : système solaire et trajectoire d'un tir."""
import os
import sys

import matplotlib
import numpy as np

if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
    matplotlib.use("Agg")
import matplotlib.pyplot as plt   # noqa: E402

from ..constants import AU_KM, DAY_S   # noqa: E402
from ..timeutils import format_date    # noqa: E402

_HEADLESS = {"agg", "pdf", "svg", "ps", "cairo", "template"}


def show_or_save(fig, name, save_dir="plots", save_only=False):
    """Affiche la figure (fenêtre) ou l'enregistre en PNG si pas d'écran. Retourne le chemin ou None."""
    if save_only or matplotlib.get_backend().lower() in _HEADLESS:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, f"{name}.png")
        fig.savefig(path, dpi=130, bbox_inches="tight")
        plt.close(fig)
        return path
    plt.show()
    return None


def _style(ax):
    ax.set_facecolor("#0b0f1a")
    ax.tick_params(colors="#aab", labelsize=8)
    for s in ax.spines.values():
        s.set_color("#445")


def plot_system(system, t, title=None):
    fig, axes = plt.subplots(1, 2, figsize=(13, 6.3), facecolor="#070a12")
    P = system.positions(t) / AU_KM
    for ax, ext, ttl in ((axes[0], 32, "Système complet"), (axes[1], 1.8, "Système interne")):
        _style(ax)
        ax.set_aspect("equal")
        ax.set_xlim(-ext, ext)
        ax.set_ylim(-ext, ext)
        ax.plot(0, 0, "o", color="gold", ms=9)
        for i, b in enumerate(system.bodies[1:], start=1):
            o = system.orbit_path(b.name, t) / AU_KM
            ax.plot(o[:, 0], o[:, 1], color=b.color, lw=0.6, alpha=0.5)
            if abs(P[i][0]) < ext and abs(P[i][1]) < ext:
                ax.plot(P[i][0], P[i][1], "o", color=b.color, ms=5 if ext > 5 else 8)
                ax.annotate(b.name, P[i][:2], color="#dde", fontsize=8, xytext=(4, 4), textcoords="offset points")
        ax.set_title(f"{ttl} (UA)", color="w", fontsize=10)
    fig.suptitle(title or f"Système solaire au {format_date(t)} (vue de dessus, écliptique)", color="w")
    fig.tight_layout()
    return fig


def plot_shot(system, report):
    res, m = report.result, report.mission
    k = max(1, len(res.times) // 2500)
    ts = res.times[::k]
    if ts[-1] != res.times[-1]:
        ts = np.append(ts, res.times[-1])
    pts = res.positions[::k]
    if len(pts) != len(ts):
        pts = np.vstack([pts, res.positions[-1]])
    pos, _ = system.planet_states(ts)                     # (K, 8, 3)
    it = system.index(m.target) - 1
    isat = system.index("Saturne") - 1
    rel = pts - pos[:, it, :]
    dist = np.linalg.norm(rel, axis=1)
    R = system.get(m.target).radius
    days = (ts - ts[0]) / DAY_S

    fig = plt.figure(figsize=(14, 9), facecolor="#070a12")
    ax1 = fig.add_subplot(2, 2, 1)
    ax2 = fig.add_subplot(2, 2, 2, projection="3d")
    ax3 = fig.add_subplot(2, 2, 3)
    ax4 = fig.add_subplot(2, 2, 4)
    for ax in (ax1, ax3, ax4):
        _style(ax)
    ax2.set_facecolor("#0b0f1a")

    rmax = max(np.abs(pts[:, :2]).max() / AU_KM, 1.8) * 1.15
    for i, b in enumerate(system.bodies[1:], start=1):
        o = system.orbit_path(b.name, ts[0]) / AU_KM
        if np.abs(o[:, :2]).max() < rmax * 1.5:
            ax1.plot(o[:, 0], o[:, 1], color=b.color, lw=0.5, alpha=0.4)
    ax1.plot(0, 0, "o", color="gold", ms=8)
    ax1.plot(pts[:, 0] / AU_KM, pts[:, 1] / AU_KM, color="cyan", lw=1.3, label="projectile")
    ax1.plot(pos[:, it, 0] / AU_KM, pos[:, it, 1] / AU_KM, color="orangered", lw=2, alpha=0.6, label=m.target)
    ax1.plot(pos[:, isat, 0] / AU_KM, pos[:, isat, 1] / AU_KM, color="khaki", lw=2, alpha=0.6, label="Saturne")
    ax1.plot(*(pts[0, :2] / AU_KM), "o", color="khaki", ms=6)
    ax1.plot(*(pts[-1, :2] / AU_KM), "x", color="red", ms=9)
    ax1.set_aspect("equal")
    ax1.set_xlim(-rmax, rmax)
    ax1.set_ylim(-rmax, rmax)
    ax1.set_title("Vue de dessus (UA)", color="w", fontsize=10)
    ax1.legend(facecolor="#112", labelcolor="w", fontsize=8, loc="lower left")

    ax2.plot(pts[:, 0] / AU_KM, pts[:, 1] / AU_KM, pts[:, 2] / AU_KM, color="cyan", lw=1.2)
    for idx, col in ((it, "orangered"), (isat, "khaki")):
        ax2.plot(pos[:, idx, 0] / AU_KM, pos[:, idx, 1] / AU_KM, pos[:, idx, 2] / AU_KM, color=col, lw=2, alpha=0.7)
    ax2.scatter([0], [0], [0], color="gold", s=40)
    ax2.set_title("Vue 3D (UA)", color="w", fontsize=10)
    ax2.tick_params(colors="#aab", labelsize=7)
    lim = rmax
    ax2.set_xlim(-lim, lim)
    ax2.set_ylim(-lim, lim)
    ax2.set_zlim(-lim / 3, lim / 3)
    ax2.set_box_aspect((1, 1, 0.4))
    for axis in (ax2.xaxis, ax2.yaxis, ax2.zaxis):
        axis.set_pane_color((0.04, 0.06, 0.1, 1.0))

    ax3.semilogy(days, np.maximum(dist, 1.0), color="cyan")
    ax3.axhline(R, color="orangered", ls="--", lw=1, label=f"surface de {m.target}")
    ax3.set_xlabel("jours depuis le tir", color="#aab")
    ax3.set_ylabel(f"distance à {m.target} (km)", color="#aab")
    ax3.set_title("Distance à la cible", color="w", fontsize=10)
    ax3.legend(facecolor="#112", labelcolor="w", fontsize=8)

    near = dist < max(15 * R, 4 * dist.min())
    if near.sum() >= 2:
        ax4.plot(rel[near, 0], rel[near, 1], color="cyan", lw=1.4)
        ax4.add_patch(plt.Circle((0, 0), R, color="orangered", alpha=0.8))
        ax4.plot(*rel[-1, :2], "x", color="white", ms=9)
    ax4.set_aspect("equal")
    ax4.set_title(f"Approche de {m.target} (km, repère de la planète)", color="w", fontsize=10)
    fig.suptitle(f"Tir du {format_date(res.t_start)} : {m.title}", color="w")
    fig.tight_layout()
    return fig
