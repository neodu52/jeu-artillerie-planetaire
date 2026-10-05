"""Catalogue de munitions et modèle de pénétration."""
from dataclasses import dataclass

import numpy as np

RHO_ARMOR = 5000.0     # densité équivalente du blindage des vaisseaux (kg/m^3)


@dataclass(frozen=True)
class Ammo:
    key: str
    name: str
    density: float            # kg/m^3 (pour déduire la masse de la géométrie)
    cost_per_kg: float        # crédits
    shield_mult: float        # énergie infligée au bouclier = E x shield_mult
    hull_mult: float          # énergie infligée à la coque = E x hull_mult
    pen_mult: float           # bonus de longueur de pénétration (pic)
    internal_mult: float      # amplification si la coque est percée (explosion interne)
    splash_m: float           # rayon de dégâts collatéraux (m)
    crew_mult: float = 0.0    # efficacité contre l'équipage
    specific_yield: float = 0.0   # J/kg de charge explosive (bombes)
    blast_eff: float = 0.0
    blast_r0_km: float = 0.0
    desc: str = ""

    @property
    def bomb(self) -> bool:
        return self.specific_yield > 0


AMMO = {a.key: a for a in [
    Ammo("rod", "Barre de tungstène", 19250, 20, 1.0, 1.0, 1.0, 1.0, 0,
         desc="Polyvalente. Pénètre selon sa longueur."),
    Ammo("ferrite", "Ferrite (dissipateur de bouclier)", 7800, 45, 4.0, 0.25, 0.5, 1.0, 0,
         desc="Sature les boucliers (x4) mais abîme peu la coque."),
    Ammo("ap_he", "Perforant-explosif (pic + ogive)", 15000, 120, 0.7, 1.0, 3.0, 2.5, 60,
         desc="Le pic perce la coque (x3 de pénétration), l'ogive explose à l'intérieur (x2,5)."),
    Ammo("dirty", "Projectile sale (fragmentation)", 8000, 60, 1.0, 0.5, 0.3, 1.0, 120,
         blast_eff=0.1, blast_r0_km=0.5, desc="Gerbe de fragments : dégâts de zone, mauvaise pénétration."),
    Ammo("gas", "Projectile à gaz (neutralisant)", 1500, 30, 0.1, 0.02, 0.1, 1.0, 0, crew_mult=1.0,
         desc="Traverse les boucliers, neutralise l'équipage (capture)."),
    Ammo("nuke", "Bombe nucléaire", 12000, 100, 1.0, 1.0, 0.5, 3.0, 400, specific_yield=5e13,
         blast_eff=0.25, blast_r0_km=0.5, desc="Charge fusion. Détonation de proximité contre les flottes."),
    Ammo("antimatter", "Bombe à antimatière", 12000, 800, 1.0, 1.0, 0.5, 3.0, 400, specific_yield=9e16,
         blast_eff=0.25, blast_r0_km=0.5, desc="Annihilation : 9e16 J/kg. Hors de prix."),
    Ammo("beam", "Impulsion laser", 1.0, 0, 1.5, 0.8, 0.0, 1.0, 0, desc="Énergie pure : aucune pénétration."),
]}


def penetration_m(ammo: Ammo, length_m: float) -> float:
    """Profondeur de pénétration (hydrodynamique) dans le blindage, en mètres."""
    if ammo.pen_mult <= 0:
        return 0.0
    return ammo.pen_mult * length_m * float(np.sqrt(ammo.density / RHO_ARMOR))


def blast_yield_j(ammo: Ammo, mass_kg: float, kinetic_j: float) -> float:
    return ammo.specific_yield * mass_kg + 0.1 * kinetic_j


def blast_energy_on_ship(ammo: Ammo, yield_j: float, distance_km: float) -> float:
    """Énergie déposée sur un vaisseau à `distance_km` du point de détonation (loi en 1/d^2)."""
    r0 = ammo.blast_r0_km * float(np.sqrt(yield_j / 1e15))
    d = max(distance_km, 1e-6)
    return ammo.blast_eff * yield_j * min(1.0, (r0 / d) ** 2)
