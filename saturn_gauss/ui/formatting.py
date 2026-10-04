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
    return f"{m:,.0f} kg".replace(",", " ")


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


def briefing(m, game) -> str:
    lines = [c(f"MISSION : {m.title}", BOLD, CYAN), m.briefing, "",
             f"  Cible            : {m.target}, latitude {m.lat:+.2f}°, longitude {m.lon:+.2f}° (Est)",
             f"  Précision        : impact à moins de {m.tolerance_km:g} km du point visé",
             f"  Énergie à la bouche : {fmt_energy(m.energy_j)} ± {m.energy_tol * 100:g} %"]
    if m.min_penetration_m:
        lines.append(f"  Pénétration min. : {m.min_penetration_m:g} m (roche, limite hydrodynamique)")
    if m.max_flight_days:
        lines.append(f"  Délai maximal    : impact {m.max_flight_days:g} jours au plus après le tir")
    return "\n".join(lines)


def shot_report(rep, system) -> str:
    r, m = rep.result, rep.mission
    L = []
    flight = (r.t_end - r.t_start) / DAY_S
    L.append(c("=== RÉSULTAT DU TIR ===", BOLD))
    L.append(f"Tir le {format_date(r.t_start)} | barre {rep.rod.length_m:g} m x r={rep.rod.radius_m:g} m "
             f"({fmt_mass(rep.rod.mass_kg)}) à {rep.speed_kms:.3f} km/s")
    L.append(f"Énergie à la bouche : {fmt_energy(rep.energy_j)} | recul de la station : {rep.recoil_ms * 1000:.2f} mm/s")
    if r.outcome == "impact":
        L.append(f"IMPACT sur {r.body} le {format_date(r.t_end)} (après {flight:,.0f} jours)".replace(",", " "))
        L.append(f"  Point d'impact : lat {r.impact_lat:+.3f}°, lon {r.impact_lon:+.3f}° | vitesse relative {r.impact_speed:.2f} km/s")
        e_imp = 0.5 * rep.rod.mass_kg * (r.impact_speed * 1e3) ** 2
        L.append(f"  Énergie à l'impact : {fmt_energy(e_imp)}")
        if rep.hit_target_body:
            L.append(f"  Écart à la cible : {rep.miss_km:,.1f} km (tolérance {m.tolerance_km:g} km)".replace(",", " "))
        else:
            L.append(c(f"  Mauvais corps : la cible était {m.target}.", YELLOW))
    else:
        txt = {"timeout": "Le projectile erre toujours dans le système solaire (durée max. atteinte).",
               "lost": "Le projectile a quitté le système solaire.",
               "time_reached": "Simulation arrêtée."}[r.outcome]
        L.append(c(txt, YELLOW))
    if not rep.hit_target_body:
        d, t = r.closest[m.target]
        R = system.get(m.target).radius
        L.append(f"  Plus proche approche de {m.target} : {d:,.0f} km du centre (altitude {d - R:,.0f} km) le {format_date(t)}".replace(",", " "))
    ok = lambda b: c("OK", GREEN) if b else c("ÉCHEC", RED)
    L.append(f"  Contrôles : précision {ok(rep.hit_target_body and rep.miss_km <= m.tolerance_km)}"
             f" | énergie {ok(rep.energy_ok)}"
             + (f" | pénétration {rep.penetration_m:.1f} m {ok(rep.penetration_ok)}" if rep.penetration_m else "")
             + (f" | délai {ok(rep.flight_ok)}" if m.max_flight_days else ""))
    if rep.success:
        L.append(c(f"MISSION ACCOMPLIE ! Score : {rep.score}", BOLD, GREEN) + "  (tapez 'next' pour la suivante)")
    else:
        L.append(c("Cible manquée ou conditions non remplies.", RED))
    return "\n".join(L)
