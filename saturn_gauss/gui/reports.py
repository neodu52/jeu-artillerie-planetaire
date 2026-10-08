"""Mise en forme texte des résultats de tirs interplanétaires."""
from ..constants import C_KMS, MT_TNT_J
from ..contracts import StrikeOp
from ..timeutils import format_date
from ..ui.formatting import fmt_duration, fmt_speed


def planetary_report(k, rep) -> str:
    op = k.focus.op
    L = []
    if isinstance(op, StrikeOp):
        res = rep["result"]
        if res.outcome == "impact":
            L.append(f"IMPACT sur {res.body} le {format_date(res.t_end)} (après {fmt_duration(res.t_end - res.t_start)})")
            L.append(f"  Point d'impact : lat {res.impact_lat:+.3f}°, lon {res.impact_lon:+.3f}° ; vitesse relative {fmt_speed(res.impact_speed)}")
            if rep.get("hit"):
                L.append(f"  Écart à la cible : {rep['miss_km']:,.1f} km (tolérance {op.tolerance_km:g} km)".replace(",", " "))
            else:
                L.append(f"  Mauvais corps : la cible était {op.target.body}.")
        else:
            L.append({"timeout": "Le projectile erre toujours (durée max).",
                      "lost": "Le projectile a quitté le système solaire."}.get(res.outcome, res.outcome))
        if not rep.get("hit") and op.target.body in res.closest:
            d, t = res.closest[op.target.body]
            L.append(f"  Plus proche approche : {d:,.0f} km du centre le {format_date(t)}".replace(",", " "))
        ok = lambda b: "OK" if b else "ÉCHEC"
        L.append(f"  Contrôles : précision {ok(rep.get('hit') and rep['miss_km'] <= op.tolerance_km)} | énergie {ok(rep['energy_ok'])}"
                 + (f" | pénétration {rep['pen_m']:.1f} m {ok(rep['pen_ok'])}" if op.min_penetration_m else "")
                 + (f" | délai {ok(rep['flight_ok'])}" if op.max_flight_days else ""))
        L.append("MISSION ACCOMPLIE !" if rep.get("success") else "Cible manquée ou conditions non remplies.")
    else:
        L += rep["lines"]
    return "\n".join(L)
