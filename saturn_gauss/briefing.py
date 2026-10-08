"""Texte de briefing d'un contrat (utilisé par l'interface graphique)."""
import numpy as np

from .constants import AU_KM, MT_TNT_J
from .contracts import AsteroidOp, Contract, DefenseOp, FleetOp, StrikeOp
from .timeutils import format_date


def _dur(s):
    s = abs(s)
    return f"{s:.0f} s" if s < 120 else f"{s / 3600:.1f} h" if s < 2 * 86400 else f"{s / 86400:.1f} j"


def brief_text(k, ct: Contract) -> str:
    if ct is None:
        return "Aucun contrat sélectionné."
    op = ct.op
    L = [f"#{ct.id}  {ct.title}" + ("   [PRIORITAIRE]" if ct.priority else ""), "", ct.text, "",
         f"Récompense : {ct.reward:,.0f} cr".replace(",", " ")
         + (f"   |   pénalité d'échec : {ct.penalty:,.0f} cr".replace(",", " ") if ct.penalty else "")]
    if ct.deadline:
        L.append(f"Échéance : {format_date(ct.deadline)} (dans {_dur(ct.deadline - k.t)})" if ct.deadline > k.t
                 else "Échéance dépassée.")
    if isinstance(op, StrikeOp):
        L += ["", f"Cible : {op.target.body}, lat {op.target.lat:+.2f}°, lon {op.target.lon:+.2f}°",
              f"Précision exigée : {op.tolerance_km:g} km",
              f"Énergie à la bouche : {op.energy_j:.3e} J ({op.energy_j / MT_TNT_J:.3g} Mt) ± {op.energy_tol * 100:g} %"]
        if op.min_penetration_m:
            L.append(f"Pénétration minimale : {op.min_penetration_m:g} m")
        if op.max_flight_days:
            L.append(f"Délai maximal de vol : {op.max_flight_days:g} jours")
    elif isinstance(op, FleetOp):
        p = op.target.point(k.system, k.t).pos
        d = np.linalg.norm(p - k.system.positions(k.t)[k.system.index("Saturne")]) / AU_KM
        L += ["", f"Orbite autour de {op.target.planet} : rayon {op.target.radius_km:,.0f} km ; distance de Saturne {d:.2f} UA".replace(",", " ")]
        for s in op.ships:
            L.append(f"  - {s.name:<20} {s.status:<10} bouclier {100 * s.shield / s.shield_max:3.0f} %   prime {s.spec.value:,.0f} cr".replace(",", " "))
        L += ["", "Munitions conseillées : nuke / antimatter / dirty (détonation de proximité).",
              f"Vol maximal : {op.max_flight_days:.1f} j -> très hautes vitesses."]
    elif isinstance(op, AsteroidOp):
        a = op.asteroid
        L += ["", f"Astéroïde : diamètre {2000 * a.radius_km:.0f} m, masse {a.mass_kg:.2e} kg, v_inf {op.v_inf:.1f} km/s",
              f"Impact sur {op.threatened} le {format_date(op.t_impact)}",
              f"Distance de passage prévue : {op.miss_km:,.0f} km ; il faut ≥ {1.3 * op.b_crit_km:,.0f} km".replace(",", " "),
              f"Tirs déjà reçus : {op.shots}"]
    elif isinstance(op, DefenseOp):
        L.append("")
        for s in op.battle.ships:
            L.append(f"  - {s.name:<18} {s.spec.name:<22} {s.status:<10} bouclier {100 * s.shield / s.shield_max:3.0f} %  prime {s.spec.value:,.0f} cr".replace(",", " "))
        L.append(f"\nÉtat de la bataille : {op.battle.state}")
    return "\n".join(L)
