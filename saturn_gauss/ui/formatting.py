"""Mise en forme texte pour le terminal."""
import numpy as np

from ..constants import AU_KM, DAY_S, MT_TNT_J
from ..timeutils import format_date

RESET, BOLD, DIM = "\033[0m", "\033[1m", "\033[2m"
RED, GREEN, YELLOW, CYAN = "\033[31m", "\033[32m", "\033[33m", "\033[36m"
_USE_COLOR = True


def set_color(enabled: bool):
    global _USE_COLOR
    _USE_COLOR = enabled


def c(text, *codes):
    return ("".join(codes) + str(text) + RESET) if _USE_COLOR else str(text)


def fmt_energy(e_j: float) -> str:
    return f"{e_j:.3e} J ({e_j / MT_TNT_J:.4g} Mt TNT)"


def fmt_mass(m: float) -> str:
    if m >= 100:
        return f"{m:,.0f} kg".replace(",", " ")
    if m >= 1:
        return f"{m:.3g} kg"
    if m >= 1e-3:
        return f"{m * 1e3:.3g} g"
    return f"{m * 1e6:.3g} mg"


def fmt_speed(v_kms: float) -> str:
    from ..constants import C_KMS
    if v_kms >= 1000:
        return f"{v_kms:,.0f} km/s ({v_kms / C_KMS:.5f} c)".replace(",", " ")
    return f"{v_kms:g} km/s"


def fmt_duration(s: float) -> str:
    s = abs(s)
    if s < 120:
        return f"{s:.1f} s"
    if s < 7200:
        return f"{s / 60:.1f} min"
    if s < 2 * 86400:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:,.1f} j".replace(",", " ")


def money(x: float) -> str:
    return f"{x:,.0f} cr".replace(",", " ")


def table(rows, header):
    widths = [max(len(str(x)) for x in col) for col in zip(header, *rows)]
    line = "  ".join(str(h).ljust(w) for h, w in zip(header, widths))
    out = [c(line, BOLD), "  ".join("-" * w for w in widths)]
    for r in rows:
        out.append("  ".join(str(x).ljust(w) for x, w in zip(r, widths)))
    return "\n".join(out)


def planets_table(system, t) -> str:
    P, V = system.states(t)
    rows = []
    for i, b in enumerate(system.bodies[1:], start=1):
        r = np.linalg.norm(P[i]) / AU_KM
        lon = np.degrees(np.arctan2(P[i][1], P[i][0])) % 360
        lat = np.degrees(np.arcsin(P[i][2] / np.linalg.norm(P[i])))
        rows.append((i, b.name, f"{r:7.3f}", f"{lon:6.1f}", f"{lat:5.2f}", f"{np.linalg.norm(V[i]):6.2f}",
                     f"{b.rotation_period_h:9.2f}", f"{b.radius:9.1f}"))
    return table(rows, ("#", "Corps", "r (UA)", "lon (°)", "lat (°)", "v (km/s)", "rotation (h)", "rayon (km)"))


def ascii_map(system, t, extent_au=None, width=73, height=37) -> str:
    """Vue de dessus (plan de l'écliptique). Sans extent_au : échelle en racine carrée du rayon."""
    grid = [[" "] * width for _ in range(height)]
    P = system.positions(t) / AU_KM
    rmax = extent_au if extent_au else 32.0

    def plot(x, y, ch):
        r = np.hypot(x, y)
        if extent_au is None and r > 0:
            k = np.sqrt(r / rmax) / (r / rmax)
            x, y, r = x * k, y * k, r * k
        col = int(round(width / 2 + x / rmax * (width / 2 - 1)))
        row = int(round(height / 2 - y / rmax * (width / 2 - 1) * 0.5))
        if 0 <= col < width and 0 <= row < height:
            grid[row][col] = ch

    for i in range(1, len(system.bodies)):
        pts = system.orbit_path(system.names[i], t, 240) / AU_KM
        for p in pts:
            plot(p[0], p[1], "·")
    plot(0, 0, "*")
    for i in range(1, len(system.bodies)):
        plot(P[i][0], P[i][1], str(i))
    scale = "échelle √r jusqu'à 32 UA" if extent_au is None else f"±{extent_au} UA"
    legend = "  ".join(f"{i}={system.names[i]}" for i in range(1, 9))
    return "\n".join("".join(r) for r in grid) + f"\n* Soleil   {legend}\n({scale}, vue du pôle nord écliptique)"


