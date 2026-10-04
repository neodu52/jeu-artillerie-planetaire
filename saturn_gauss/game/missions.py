"""Objectifs de la campagne."""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Mission:
    title: str
    briefing: str
    target: str
    lat: float                      # deg
    lon: float                      # deg Est
    tolerance_km: float             # rayon de précision exigé à la surface
    energy_j: float                 # énergie cinétique à la bouche
    energy_tol: float = 0.05        # tolérance relative
    min_penetration_m: Optional[float] = None
    max_flight_days: Optional[float] = None   # délai de livraison maximal


CAMPAIGN = [
    Mission("Prise de contact : Mars",
            "Test de calibrage sur le volcan Olympus Mons. Large tolérance : l'important est de "
            "comprendre la mécanique orbitale.",
            "Mars", 18.65, -133.8, 1200.0, 5.0e12),
    Mission("Cratère Caloris",
            "Frappe de démonstration sur le bassin Caloris de Mercure. Mercure est rapide, "
            "les fenêtres sont fréquentes mais la cible tourne lentement.",
            "Mercure", 30.5, 189.8, 600.0, 3.0e12),
    Mission("Maxwell Montes",
            "Les nuages de Vénus sont ignorés par la simulation : visez le sommet de Maxwell "
            "Montes. Rotation rétrograde, 243 jours !",
            "Vénus", 65.2, 3.3, 400.0, 1.0e13),
    Mission("Bunker de Hellas",
            "Une installation enterrée sous Hellas Planitia exige une pénétration d'au moins "
            "25 m. La longueur de la barre compte.",
            "Mars", -42.4, 70.5, 200.0, 2.0e13, 0.05, 25.0),
    Mission("Pôle nord de Mercure",
            "Les cratères polaires de Mercure sont en ombre permanente. Précision maximale.",
            "Mercure", 88.0, 0.0, 100.0, 8.0e12, 0.03),
    Mission("Valles Marineris : livraison express",
            "Frappe urgente : l'impact doit avoir lieu moins de 1400 jours après le tir. "
            "Un vol rapide exige plus de vitesse, donc une barre plus légère pour la même énergie.",
            "Mars", -13.9, -59.2, 80.0, 8.0e12, 0.05, None, 1400.0),
]
