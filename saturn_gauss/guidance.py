"""Ordinateur de visée : fenêtres de tir, conversion v_inf -> vecteur de tir, correction.

Le principe (conique raccordée + correction numérique) :
 1. Lambert héliocentrique : de la position du canon jusqu'au point visé à la date d'arrivée.
 2. La vitesse à l'infini par rapport à Saturne est convertie en vitesse de tir depuis l'orbite
    du canon (hyperbole d'évasion exacte à deux corps).
 3. ``refine`` corrige ensuite ce vecteur par tirs d'essai sur la vraie simulation
    (Newton / Broyden) afin d'annuler l'écart au point visé.
"""
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .ballistics.cannon import V_MAX_KMS, GaussCannon, direction_angles
from .ballistics.integrator import Propagator
from .ballistics.lambert import lambert
from .ballistics.projectile import LENGTH_RANGE_M, RADIUS_RANGE_M, Rod, radius_for_mass
from .constants import AU_KM, DAY_S, GM_SUN, TUNGSTEN_DENSITY, YEAR_S
from .solarsystem.rotation import surface_unit_vector
from .solarsystem.system import SolarSystem


# --------------------------------------------------------------------------- conique à 2 corps
def asymptote_direction(r, v, mu):
    """Direction de la vitesse à l'infini de l'hyperbole passant par (r, v)."""
    h = np.cross(r, v)
    ev = np.cross(v, h) / mu - r / np.linalg.norm(r)
    e = np.linalg.norm(ev)
    if e <= 1.0:
        raise ValueError("orbite liée")
    eh = ev / e
    qh = np.cross(h / np.linalg.norm(h), eh)
    return (-eh + np.sqrt(e * e - 1) * qh) / e


def launch_velocity_for_asymptote(r, mu, vinf_vec, r_min):
    """Vitesse (relative au corps central) au point r donnant la vitesse à l'infini vinf_vec.

    Retourne None si la trajectoire passerait sous r_min (impact avec Saturne).
    """
    rn = np.linalg.norm(r)
    rhat = r / rn
    vinf = np.linalg.norm(vinf_vec)
    u = vinf_vec / vinf
    cr = np.cross(rhat, u)
    s = np.linalg.norm(cr)
    if s < 1e-9:
        return None
    hhat = cr / s
    alpha = np.arctan2(s, rhat @ u)
    vl = np.sqrt(vinf ** 2 + 2 * mu / rn)
    that = np.cross(hhat, rhat)

    def geom(h):
        e = np.sqrt(1 + (vinf * h / mu) ** 2)
        nu = np.arccos(np.clip((h * h / mu / rn - 1) / e, -1, 1))
        nuinf = np.arccos(-1 / e)
        return e, nu, nuinf

    hs = np.linspace(1e-6, rn * vl * (1 - 1e-9), 1500)
    e, nu, nuinf = geom(hs)
    for branch in ("out", "in"):
        delta = nuinf - nu if branch == "out" else nuinf + nu
        f = delta - alpha
        ok = (f[:-1] * f[1:]) <= 0
        if not ok.any():
            continue
        k = int(np.argmax(ok))
        lo, hi = hs[k], hs[k + 1]
        flo = f[k]
        for _ in range(60):
            mid = 0.5 * (lo + hi)
            e_, nu_, ni_ = geom(mid)
            fm = (ni_ - nu_ if branch == "out" else ni_ + nu_) - alpha
            if (fm < 0) == (flo < 0):
                lo, flo = mid, fm
            else:
                hi = mid
        h = 0.5 * (lo + hi)
        e_, _, _ = geom(h)
        vr = np.sqrt(max(vl ** 2 - (h / rn) ** 2, 0.0)) * (1 if branch == "out" else -1)
        if branch == "in" and h * h / mu / (1 + e_) < r_min:
            return None
        return vr * rhat + (h / rn) * that
    return None


# --------------------------------------------------------------------------- plans
def suggest_rod(mission, speed_kms: float, density_target: float) -> Optional[Rod]:
    """Géométrie de barre donnant l'énergie demandée à cette vitesse et la pénétration requise."""
    mass = 2 * mission.energy_j / (speed_kms * 1e3) ** 2
    lmin = LENGTH_RANGE_M[0]
    if mission.min_penetration_m:
        lmin = max(lmin, 1.05 * mission.min_penetration_m / np.sqrt(TUNGSTEN_DENSITY / density_target))
    for L in (max(lmin, 10.0), 20.0, 40.0, LENGTH_RANGE_M[1], lmin):
        if L < lmin or L > LENGTH_RANGE_M[1]:
            continue
        r = radius_for_mass(mass, L)
        if RADIUS_RANGE_M[0] <= r <= RADIUS_RANGE_M[1]:
            return Rod(round(float(L), 2), round(float(r), 4))
    return None


@dataclass
class Plan:
    t_launch: float
    t_arrival: float
    v0_vec: np.ndarray          # vitesse de bouche (relative au canon), km/s
    v_inf: float
    arrival_speed: float
    visibility: float
    rod: Optional[Rod] = None
    refined: bool = False
    residual_km: Optional[float] = None

    @property
    def speed(self) -> float:
        return float(np.linalg.norm(self.v0_vec))

    @property
    def lon_lat(self):
        return direction_angles(self.v0_vec)

    @property
    def flight_days(self) -> float:
        return (self.t_arrival - self.t_launch) / DAY_S


class Guidance:
    def __init__(self, system: SolarSystem, cannon: GaussCannon, propagator: Propagator):
        self.system, self.cannon, self.prop = system, cannon, propagator
        self.i_sat = system.index("Saturne")

    # ---- évaluation d'un couple (départ, arrivée)
    def evaluate(self, mission, t_l, t_a) -> Optional[Plan]:
        sys_ = self.system
        body = sys_.get(mission.target)
        i = sys_.index(mission.target)
        P, V = sys_.states(t_l)
        Vs = V[self.i_sat]
        cs = self.cannon.state(t_l)
        Pa, Va = sys_.states(t_a)
        n = surface_unit_vector(body, t_a, mission.lat, mission.lon)
        target = Pa[i] + body.radius * n
        lam = lambert(cs.r_helio, target, t_a - t_l, GM_SUN)
        if lam is None:
            return None
        v1, v2 = lam
        v_arr = v2 - Va[i]
        sp = np.linalg.norm(v_arr)
        vis = float(-(v_arr @ n) / sp)
        if vis < 0.4:
            return None
        vinf_vec = v1 - Vs
        v_rel = launch_velocity_for_asymptote(cs.r_rel, self.cannon.mu, vinf_vec,
                                              self.cannon.saturn.radius + 5000.0)
        if v_rel is None:
            return None
        v0 = v_rel - cs.v_rel
        if np.linalg.norm(v0) > 0.98 * V_MAX_KMS:
            return None
        plan = Plan(t_l, t_a, v0, float(np.linalg.norm(vinf_vec)), float(sp), vis)
        plan.rod = suggest_rod(mission, plan.speed, body.surface_density)
        return plan

    # ---- recherche de fenêtres
    def find_windows(self, mission, t_now, n_results=5,
                     progress: Optional[Callable[[str], None]] = None, max_flight_days=None):
        say = progress or (lambda s: None)
        sys_ = self.system
        body = sys_.get(mission.target)
        ib = sys_.index(mission.target) - 1
        isat = self.i_sat - 1
        Ps0, _ = sys_.states(t_now)
        r1 = np.linalg.norm(Ps0[self.i_sat])
        r2 = np.linalg.norm(Ps0[sys_.index(mission.target)])
        a = 0.5 * (r1 + r2)
        hoh = np.pi * np.sqrt(a ** 3 / GM_SUN)
        syn = abs(1.0 / (1.0 / (2 * np.pi / sys_._eph.Mdot[isat]) - 1.0 / (2 * np.pi / sys_._eph.Mdot[ib])))
        span = float(np.clip(syn, 0.3 * YEAR_S, 3.0 * YEAR_S))
        t_launch = t_now + np.linspace(0.0, span, 70)
        hi = 1.3 * hoh
        limit = max_flight_days or getattr(mission, "max_flight_days", None)
        if limit:
            hi = min(hi, limit * DAY_S)
        lo = min(0.35 * hoh, 0.4 * hi)
        tofs = np.linspace(lo, hi, 90)
        say(f"Balayage grossier : {len(t_launch)} dates de départ x {len(tofs)} durées de vol...")

        PL, VL = sys_.planet_states(t_launch)
        TA = t_launch[:, None] + tofs[None, :]
        PA, _ = sys_.planet_states(TA)
        cost = np.full(TA.shape, np.inf)
        for i in range(len(t_launch)):
            r_s, v_s = PL[i, isat], VL[i, isat]
            for j in range(len(tofs)):
                lam = lambert(r_s, PA[i, j, ib], tofs[j], GM_SUN)
                if lam is not None:
                    cost[i, j] = np.linalg.norm(lam[0] - v_s)

        pad = np.pad(cost, 1, constant_values=np.inf)
        neigh = np.min([pad[1 + di:1 + di + cost.shape[0], 1 + dj:1 + dj + cost.shape[1]]
                        for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di, dj) != (0, 0)], axis=0)
        minima = np.argwhere(np.isfinite(cost) & (cost <= neigh))
        minima = sorted(minima, key=lambda ij: cost[tuple(ij)])[:8]
        say(f"{len(minima)} fenêtres candidates ; affinage (rotation de la cible, phase du canon)...")

        rot_days = min(abs(body.rotation_period_h) / 24.0, 120.0)
        plans = []
        for i, j in minima:
            tl0, ta0 = t_launch[i], t_launch[i] + tofs[j]
            best = None
            offs = np.linspace(-0.5, 0.5, 48) * rot_days * DAY_S
            cand = []
            for off in offs:
                p = self.evaluate(mission, tl0, ta0 + off)
                if p is not None:
                    cand.append(p)
            for p0 in sorted(cand, key=lambda p: p.v_inf)[:3]:
                for k in range(24):
                    tl = tl0 + k * self.cannon.period_s / 24.0
                    p = self.evaluate(mission, tl, p0.t_arrival)
                    if p is not None and p.rod is not None and (best is None or p.speed < best.speed):
                        best = p
            if best is not None:
                plans.append(best)
        plans.sort(key=lambda p: p.speed)
        return plans[:n_results]

    # ---- correction par tirs d'essai (Newton / Broyden)
    def refine(self, mission, plan: Plan, tol_km=1.0, max_iter=10,
               progress: Optional[Callable[[str], None]] = None) -> Plan:
        say = progress or (lambda s: None)
        sys_ = self.system
        body = sys_.get(mission.target)
        i = sys_.index(mission.target)
        cs = self.cannon.state(plan.t_launch)
        n = surface_unit_vector(body, plan.t_arrival, mission.lat, mission.lon)
        target = sys_.positions(plan.t_arrival)[i] + body.radius * n

        def resid(w):
            res = self.prop.run(plan.t_launch, cs.r_helio, cs.v_helio + w, t_end=plan.t_arrival,
                                stop_on_hit=False)
            return res.final_pos - target

        w = plan.v0_vec.copy()
        f = resid(w)
        h = 1e-5
        J = np.empty((3, 3))
        for k in range(3):
            dw = np.zeros(3)
            dw[k] = h
            J[:, k] = (resid(w + dw) - f) / h
        say(f"  écart initial : {np.linalg.norm(f):,.0f} km")
        for it in range(max_iter):
            if np.linalg.norm(f) < tol_km:
                break
            step = -np.linalg.solve(J, f)
            lam = 1.0
            for _ in range(6):
                w_new = w + lam * step
                f_new = resid(w_new)
                if np.linalg.norm(f_new) < np.linalg.norm(f):
                    break
                lam *= 0.5
            else:
                break
            df, dw = f_new - f, w_new - w
            J = J + np.outer(df - J @ dw, dw) / (dw @ dw)           # mise à jour de Broyden
            w, f = w_new, f_new
            say(f"  itération {it + 1} : écart {np.linalg.norm(f):,.2f} km")
        out = Plan(plan.t_launch, plan.t_arrival, w, plan.v_inf, plan.arrival_speed, plan.visibility,
                   refined=True, residual_km=float(np.linalg.norm(f)))
        out.rod = suggest_rod(mission, out.speed, body.surface_density)
        return out
