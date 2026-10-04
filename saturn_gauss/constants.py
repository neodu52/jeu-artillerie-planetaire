"""Constantes physiques et conventions d'unités.

Unités internes : kilomètres, secondes, kg (sauf indication contraire).
Le temps ``t`` est exprimé en secondes depuis J2000 (2000-01-01 12:00).
"""
import math
from datetime import datetime

AU_KM = 149_597_870.7
DAY_S = 86_400.0
YEAR_S = 365.25 * DAY_S
CENTURY_S = 36_525.0 * DAY_S

GM_SUN = 1.32712440018e11          # km^3/s^2
SUN_RADIUS_KM = 695_700.0

TUNGSTEN_DENSITY = 19_250.0        # kg/m^3
MT_TNT_J = 4.184e15                # 1 mégatonne de TNT en joules

J2000 = datetime(2000, 1, 1, 12, 0, 0)
OBLIQUITY = math.radians(23.43929111)   # inclinaison de l'écliptique sur l'équateur ICRF

# Date de départ du jeu
GAME_START = datetime(2150, 1, 1, 0, 0, 0)
