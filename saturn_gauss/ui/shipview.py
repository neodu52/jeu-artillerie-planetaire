"""Vue des vaisseaux : dessin ASCII (terminal) et fenêtre matplotlib."""
import numpy as np

from ..combat.ships import Ship


def _basis(view_dir):
    d = np.asarray(view_dir, float)
    d = d / np.linalg.norm(d)
    right = np.cross(d, [0.0, 0.0, 1.0])
    if np.linalg.norm(right) < 1e-6:
        right = np.cross(d, [1.0, 0.0, 0.0])
    right /= np.linalg.norm(right)
    return d, right, np.cross(right, d)


_SIGNS = np.array([[sx, sy, sz] for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)], float)


def project(ship: Ship, view_dir, t):
    """Rectangles englobants projetés : [(indice, xmin, xmax, ymin, ymax, profondeur, coins)]."""
    pos, v = ship.state(t)
    A = Ship.axes(v)
    d, right, up = _basis(view_dir)
    out = []
    for i, c in enumerate(ship.comps):
        corners = (A @ (c.center[:, None] + _SIGNS.T * (c.size[:, None] / 2))).T       # m
        px, py = corners @ right, corners @ up
        out.append((i, px.min(), px.max(), py.min(), py.max(), float((A @ c.center) @ d), np.column_stack([px, py])))
    return out


def render_ascii(ship: Ship, view_dir, t, selected=None, width=76, height=22) -> str:
    rects = project(ship, view_dir, t)
    x0, x1 = min(r[1] for r in rects), max(r[2] for r in rects)
    y0, y1 = min(r[3] for r in rects), max(r[4] for r in rects)
    sx = (width - 2) / max(x1 - x0, 1e-9)
    sy = sx * 0.5
    if (y1 - y0) * sy > height - 2:
        sy = (height - 2) / (y1 - y0)
        sx = sy * 2
    W = int((x1 - x0) * sx) + 2
    H = int((y1 - y0) * sy) + 2
    grid = [[" "] * W for _ in range(H)]
    for i, xa, xb, ya, yb, depth, _ in sorted(rects, key=lambda r: -r[5]):     # du plus loin au plus proche
        c0, c1 = int((xa - x0) * sx), int((xb - x0) * sx)
        r0, r1 = int((y1 - yb) * sy), int((y1 - ya) * sy)
        c1, r1 = max(c1, c0 + 2), max(r1, r0 + 2)
        comp = ship.comps[i]
        border = "#" if selected == i else ("+" if comp.alive else ".")
        for r in range(r0, min(r1 + 1, H)):
            for c in range(c0, min(c1 + 1, W)):
                edge_h, edge_v = r in (r0, r1), c in (c0, c1)
                grid[r][c] = (border if (edge_h and edge_v) else "-" if edge_h else "|" if edge_v else
                              ("x" if not comp.alive else " ")) if not (not comp.alive and not (edge_h or edge_v)) else "x"
        label = str(i + 1)
        rm, cm = (r0 + r1) // 2, (c0 + c1) // 2 - len(label) // 2
        for k, ch in enumerate(label):
            if 0 <= rm < H and 0 <= cm + k < W:
                grid[rm][cm + k] = ch
    return "\n".join("".join(r).rstrip() for r in grid)


def _hull(points):
    """Enveloppe convexe (chaîne monotone d'Andrew)."""
    pts = sorted(map(tuple, points))
    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, up = [], []
    for p in pts:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], p) <= 0:
            lo.pop()
        lo.append(p)
    for p in reversed(pts):
        while len(up) >= 2 and cross(up[-2], up[-1], p) <= 0:
            up.pop()
        up.append(p)
    return np.array(lo[:-1] + up[:-1])


def plot_ship(ship: Ship, view_dir, t, selected=None, title=None):
    """Fenêtre matplotlib : vue du tireur + vue de profil du vaisseau (couleur = intégrité)."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse, Polygon

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.2), facecolor="#070a12")
    views = [("Vue du tireur", view_dir), ("Vue de profil (vaisseau)", Ship.axes(ship.state(t)[1])[:, 1])]
    cmap = plt.get_cmap("RdYlGn")
    for ax, (ttl, vd) in zip(axes, views):
        ax.set_facecolor("#0b0f1a")
        rects = project(ship, vd, t)
        xs = np.concatenate([r[6][:, 0] for r in rects])
        ys = np.concatenate([r[6][:, 1] for r in rects])
        cx, cy = 0.5 * (xs.min() + xs.max()), 0.5 * (ys.min() + ys.max())
        rad = 0.75 * max(xs.max() - xs.min(), ys.max() - ys.min())
        frac = ship.shield / ship.shield_max if ship.shield_max else 0
        if ship.shield_online and frac > 0:
            ax.add_patch(Ellipse((cx, cy), 2 * rad * 0.97, 2 * rad * 0.72, color="cyan", alpha=0.04 + 0.12 * frac))
        for i, xa, xb, ya, yb, depth, pts in sorted(rects, key=lambda r: -r[5]):
            comp = ship.comps[i]
            col = cmap(max(comp.hp, 0) / comp.hp_max) if comp.alive else "#333"
            poly = _hull(pts)
            ax.add_patch(Polygon(poly, closed=True, facecolor=col, edgecolor="white" if selected == i else "#556",
                                 lw=2.5 if selected == i else 0.8, alpha=0.9))
            ax.text(0.5 * (xa + xb), 0.5 * (ya + yb), str(i + 1), ha="center", va="center", fontsize=9, color="black")
        ax.set_xlim(cx - rad, cx + rad)
        ax.set_ylim(cy - rad * 0.7, cy + rad * 0.7)
        ax.set_aspect("equal")
        ax.set_title(ttl + " (m)", color="w", fontsize=10)
        ax.tick_params(colors="#aab", labelsize=7)
    fig.suptitle(title or f"{ship.name} ({ship.spec.name}) — bouclier {100 * ship.shield / ship.shield_max:.0f} %"
                 f" — intégrité {100 * ship.hp_fraction:.0f} % — {ship.status}", color="w")
    fig.tight_layout()
    return fig
