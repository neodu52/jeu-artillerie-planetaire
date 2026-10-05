"""Ordinateur de visée du canon interplanétaire.

Deux modes de recherche de fenêtres :
 * ``speed=None`` (« auto ») : vitesse la plus économe, la barre est ensuite déduite de l'énergie ;
 * ``speed=v`` : la vitesse de bouche *du joueur* est imposée, on cherche dates et directions.

Principe : conique raccordée (Lambert, ou ligne droite pour les vols très rapides) puis
correction par tirs d'essai sur la vraie simulation (Newton / Broyden). La correction
garde la vitesse du joueur et ajuste la direction et la date d'arrivée.
"""
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

from .ballistics.cannon import V_MAX_KMS, GaussCannon, add_velocity, direction_angles, direction_vector
from .ballistics.integrator import Propagator
from .ballistics.lambert import lambert
from .ballistics.projectile import (LENGTH_RANGE_M, RADIUS_RANGE_M, Rod, mass_for_energy, radius_for_mass)
from .constants import DAY_S, GM_SUN, TUNGSTEN_DENSITY, YEAR_S
from .solarsystem.system import SolarSystem

FAST_KMS = 150.0       # au-delà (distance/durée), trajectoire rectiligne au lieu de Lambert


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
    """Vitesse (relative au corps central) en r donnant la vitesse à l'infini vinf_vec.

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
@dataclass
class GuidanceSpec:
    """Ce que le guidage doit savoir de la mission."""
    target: object
    energy_j: Optional[float] = None
    min_penetration_m: Optional[float] = None
    density: float = 2800.0
    max_flight_days: Optional[float] = None
    t_latest: Optional[float] = None       # date limite d'arrivée (échéance du contrat)


def suggest_rod(spec: GuidanceSpec, speed_kms: float) -> Optional[Rod]:
    """Barre donnant l'énergie demandée (relativiste) à cette vitesse et la pénétration requise."""
    if spec.energy_j is None:
        return None
    mass = mass_for_energy(spec.energy_j, speed_kms)
    lmin = LENGTH_RANGE_M[0]
    if spec.min_penetration_m:
        lmin = max(lmin, 1.05 * spec.min_penetration_m / np.sqrt(TUNGSTEN_DENSITY / spec.density))
    for L in (max(lmin, 10.0), 20.0, 40.0, LENGTH_RANGE_M[1], 5.0, 2.0, 1.0, 0.5, 0.2, 0.1, 0.05,
              0.02, 0.01, 0.005, 0.002, lmin):
        if L < lmin or L > LENGTH_RANGE_M[1]:
            continue
        r = radius_for_mass(mass, L)
        if RADIUS_RANGE_M[0] <= r <= RADIUS_RANGE_M[1]:
            return Rod(round(float(L), 4), round(float(r), 5))
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
    def flight_s(self) -> float:
        return self.t_arrival - self.t_launch

    @property
    def flight_days(self) -> float:
        return self.flight_s / DAY_S


class Guidance:
    def __init__(self, system: SolarSystem, cannon: GaussCannon, propagator: Propagator):
        self.system, self.cannon, self.prop = system, cannon, propagator
        self.i_sat = system.index("Saturne")
        self.last_note = ""

    # ---- transfert (t_l, t_a)
    def _transfer(self, spec, t_l, t_a, cs=None):
        tof = t_a - t_l
        if tof <= 0:
            return None
        cs = cs or self.cannon.state(t_l)
        tp = spec.target.point(self.system, t_a)
        Vs = cs.v_helio - cs.v_rel
        d = tp.pos - cs.r_helio
        dist = float(np.linalg.norm(d))
        r_min = self.cannon.saturn.radius + 5000.0
        if dist / tof > FAST_KMS:                   # trajectoire quasi rectiligne
            v1 = d / tof
            v2 = v1
            v0 = v1 - cs.v_helio
            vv = float(v0 @ v0)
            s_ = max(-float(cs.r_rel @ v0) / vv, 0.0)
            if np.linalg.norm(cs.r_rel + s_ * v0) < r_min:
                return None
            vinf = float(np.linalg.norm(v1 - Vs))
        else:
            lam = lambert(cs.r_helio, tp.pos, tof, GM_SUN)
            if lam is None:
                return None
            v1, v2 = lam
            vinf_vec = v1 - Vs
            v_rel = launch_velocity_for_asymptote(cs.r_rel, self.cannon.mu, vinf_vec, r_min)
            if v_rel is None:
                return None
            v0 = v_rel - cs.v_rel
            vinf = float(np.linalg.norm(vinf_vec))
        v_arr = v2 - tp.vel
        sp = float(np.linalg.norm(v_arr))
        vis = 1.0 if tp.normal is None else float(-(v_arr @ tp.normal) / sp)
        return v0, vinf, sp, vis

    def evaluate(self, spec, t_l, t_a, rod=None, want_rod=True) -> Optional[Plan]:
        tr = self._transfer(spec, t_l, t_a)
        if tr is None:
            return None
        v0, vinf, sp, vis = tr
        if vis < 0.4 or np.linalg.norm(v0) > 0.98 * V_MAX_KMS:
            return None
        plan = Plan(t_l, t_a, v0, vinf, sp, vis)
        plan.rod = rod if rod is not None else (suggest_rod(spec, plan.speed) if want_rod else None)
        if want_rod and rod is None and spec.energy_j is not None and plan.rod is None:
            return None
        return plan

    # ---- grilles communes
    def _span(self, spec, t_now):
        p0 = spec.target.centers(self.system, np.array([t_now]))[0]
        r2 = np.linalg.norm(p0)
        i = self.i_sat - 1
        syn = 2.0 * YEAR_S
        if getattr(spec.target, "kind", "") != "asteroid":
            ib = self.system.index(spec.target.planet) - 1
            w = abs(self.system._eph.Mdot[i] - self.system._eph.Mdot[ib])
            syn = 2 * np.pi / w if w > 0 else syn
        return float(np.clip(syn, 0.3 * YEAR_S, 3.0 * YEAR_S)), r2

    def _distance_bounds(self, spec, t_now):
        ts = t_now + np.linspace(0, 3 * YEAR_S, 24)
        Ps = self.system.planet_states(ts)[0][:, self.i_sat - 1, :]
        Pt = spec.target.centers(self.system, ts)
        d = np.linalg.norm(Ps - Pt, axis=1)
        return max(0.7 * d.min(), 1e6), 1.3 * d.max()

    # ---- fenêtres
    def find_windows(self, spec, t_now, n_results=5, progress: Optional[Callable[[str], None]] = None,
                     max_flight_days=None, speed=None):
        say = progress or (lambda s: None)
        self.last_note = ""
        limit = max_flight_days or spec.max_flight_days
        if speed is not None:
            return self._windows_for_speed(spec, t_now, float(speed), n_results, say, limit)
        return self._windows_auto(spec, t_now, n_results, say, limit)

    def _coarse_arrays(self, spec, t_now, tofs, n_launch=70):
        span, _ = self._span(spec, t_now)
        if spec.t_latest is not None:
            span = max(min(span, spec.t_latest - t_now - float(np.min(tofs))), 0.02 * DAY_S)
        t_launch = t_now + np.linspace(0.0, span, n_launch)
        isat = self.i_sat - 1
        PL, VL = self.system.planet_states(t_launch)
        TA = t_launch[:, None] + tofs[None, :]
        PT = spec.target.centers(self.system, TA)
        return span, t_launch, PL[:, isat], VL[:, isat], PT, TA

    def _windows_auto(self, spec, t_now, n_results, say, limit):
        sys_ = self.system
        r1 = np.linalg.norm(sys_.positions(t_now)[self.i_sat])
        _, r2 = self._span(spec, t_now)
        hoh = np.pi * np.sqrt((0.5 * (r1 + r2)) ** 3 / GM_SUN)
        hi = min(1.3 * hoh, limit * DAY_S) if limit else 1.3 * hoh
        lo = min(0.35 * hoh, 0.4 * hi)
        tofs = np.linspace(lo, hi, 90)
        span, t_launch, Ps, Vs, PT, TA = self._coarse_arrays(spec, t_now, tofs)
        say(f"Balayage grossier : {len(t_launch)} dates de départ x {len(tofs)} durées de vol...")
        cost = np.full(TA.shape, np.inf)
        for i in range(len(t_launch)):
            for j in range(len(tofs)):
                dvec = PT[i, j] - Ps[i]
                if np.linalg.norm(dvec) / tofs[j] > FAST_KMS:
                    v1 = dvec / tofs[j]
                else:
                    lam = lambert(Ps[i], PT[i, j], tofs[j], GM_SUN)
                    if lam is None:
                        continue
                    v1 = lam[0]
                cost[i, j] = np.linalg.norm(v1 - Vs[i])
        pad = np.pad(cost, 1, constant_values=np.inf)
        neigh = np.min([pad[1 + a:1 + a + cost.shape[0], 1 + b:1 + b + cost.shape[1]]
                        for a in (-1, 0, 1) for b in (-1, 0, 1) if (a, b) != (0, 0)], axis=0)
        minima = np.argwhere(np.isfinite(cost) & (cost <= neigh))
        minima = sorted(minima, key=lambda ij: cost[tuple(ij)])[:8]
        say(f"{len(minima)} fenêtres candidates ; affinage (rotation de la cible, phase du canon)...")

        plans = []
        for i, j in minima:
            tl0, ta0 = t_launch[i], t_launch[i] + tofs[j]
            cand = []
            for off in np.linspace(-0.5, 0.5, 48) * self._rot_span(spec):
                p = self.evaluate(spec, tl0, ta0 + off)
                if p is not None:
                    cand.append(p)
            best = None
            for p0 in sorted(cand, key=lambda p: p.v_inf)[:3]:
                for k in range(24):
                    p = self.evaluate(spec, tl0 + k * self.cannon.period_s / 24.0, p0.t_arrival)
                    if p is not None and (best is None or p.speed < best.speed):
                        best = p
            if best is not None:
                plans.append(best)
        plans.sort(key=lambda p: p.speed)
        return plans[:n_results]

    @staticmethod
    def _rot_span(spec):
        """Durée sur laquelle la rotation de la cible change la géométrie d'arrivée."""
        if getattr(spec.target, "kind", "") != "surface":
            return 2 * DAY_S
        return DAY_S * 24.0   # recalculé par le joueur via body ; valeur large raisonnable

    def _windows_for_speed(self, spec, t_now, s, n_results, say, limit):
        sys_ = self.system
        vorb, mu = self.cannon.speed_kms, self.cannon.mu
        rc = self.cannon.radius_km
        d_min, d_max = self._distance_bounds(spec, t_now)
        r1 = np.linalg.norm(sys_.positions(t_now)[self.i_sat])
        _, r2 = self._span(spec, t_now)
        hoh = np.pi * np.sqrt((0.5 * (r1 + r2)) ** 3 / GM_SUN)
        t_lo = 0.3 * d_min / (s + 60.0)
        t_hi = min(1.3 * hoh, 3.0 * d_max / max(s, 1.0))
        if limit:
            t_hi = min(t_hi, limit * DAY_S)
        t_lo = min(t_lo, 0.5 * t_hi)
        tofs = np.geomspace(t_lo, t_hi, 120)
        span, t_launch, Ps, Vs, PT, TA = self._coarse_arrays(spec, t_now, tofs, n_launch=60)
        say(f"Balayage grossier pour v = {s:,.1f} km/s : {len(t_launch)} départs x {len(tofs)} durées...")
        vl = np.full(TA.shape, np.nan)
        for i in range(len(t_launch)):
            for j in range(len(tofs)):
                dvec = PT[i, j] - Ps[i]
                if np.linalg.norm(dvec) / tofs[j] > FAST_KMS:
                    v1 = dvec / tofs[j]
                else:
                    lam = lambert(Ps[i], PT[i, j], tofs[j], GM_SUN)
                    if lam is None:
                        continue
                    v1 = lam[0]
                vinf = np.linalg.norm(v1 - Vs[i])
                vl[i, j] = np.sqrt(vinf ** 2 + 2 * mu / rc)
        lower = np.maximum(vl - vorb, 0.0)
        with np.errstate(invalid="ignore"):
            score = np.abs(vl - s)
            band = vorb + 0.03 * s
            if np.isfinite(lower).any():
                lmin = float(np.nanmin(lower))
                if s < lmin:
                    self.last_note = (f"Vitesse insuffisante : il faut au moins ≈ {lmin:,.1f} km/s "
                                      f"pour cette cible à cette période (vous : {s:,.1f} km/s).")
            ok = score <= band
            if spec.t_latest is not None:
                ok &= TA <= spec.t_latest
        cands = []
        for i in range(score.shape[0]):
            row = score[i]
            for j in range(len(row)):
                if not ok[i, j]:
                    continue
                left = row[j - 1] if j > 0 and np.isfinite(row[j - 1]) else np.inf
                right = row[j + 1] if j < len(row) - 1 and np.isfinite(row[j + 1]) else np.inf
                if row[j] <= left and row[j] <= right:
                    cands.append((float(row[j]), i, j))
        cands.sort()
        chosen = []
        for sc, i, j in cands:
            if all(abs(i - i0) >= 5 or abs(j - j0) >= 25 for _, i0, j0 in chosen):
                chosen.append((sc, i, j))
            if len(chosen) >= 6:
                break
        say(f"{len(chosen)} candidats ; affinage (phase du canon, rotation de la cible)...")

        plans = []
        for _, i, j in chosen:
            tl0, tof0 = t_launch[i], tofs[j]
            span_l = max(2 * self.cannon.period_s, self._rot_days(spec) * DAY_S)
            if spec.t_latest is not None:
                span_l = max(min(span_l, spec.t_latest - tl0 - tof0), 0.0)
            best = None
            for k in range(36):
                tl = tl0 + span_l * k / 36.0
                tof = self._solve_tof(spec, tl, tof0, s)
                if tof is None or (spec.t_latest is not None and tl + tof > spec.t_latest):
                    continue
                p = self.evaluate(spec, tl, tl + tof, rod=Rod(1, 1), want_rod=False)
                if p is not None and (best is None or p.visibility > best.visibility):
                    best = p
            if best is not None:
                best.v0_vec = best.v0_vec * (s / best.speed)
                best.rod = None
                plans.append(best)
        plans.sort(key=lambda p: p.t_launch)
        return plans[:n_results]

    def _rot_days(self, spec):
        if getattr(spec.target, "kind", "") != "surface":
            return 2.0
        b = self.system.get(spec.target.body)
        return min(abs(b.rotation_period_h) / 24.0, 40.0)

    def _speed_at(self, spec, tl, tof, cs):
        tr = self._transfer(spec, tl, tl + tof, cs)
        return np.nan if tr is None else float(np.linalg.norm(tr[0]))

    def _solve_tof(self, spec, tl, tof0, s):
        """Durée de vol donnant exactement la vitesse de bouche s (racine de |v0|(tof) - s)."""
        cs = self.cannon.state(tl)
        tofs = tof0 * (1 + np.linspace(-0.35, 0.35, 15))
        vals = np.array([self._speed_at(spec, tl, x, cs) for x in tofs]) - s
        best = None
        for k in range(len(tofs) - 1):
            a, b = vals[k], vals[k + 1]
            if not (np.isfinite(a) and np.isfinite(b) and a * b <= 0):
                continue
            lo, hi, flo = tofs[k], tofs[k + 1], a
            good = True
            for _ in range(24):
                mid = 0.5 * (lo + hi)
                fm = self._speed_at(spec, tl, mid, cs) - s
                if not np.isfinite(fm):
                    good = False
                    break
                if (fm < 0) == (flo < 0):
                    lo, flo = mid, fm
                else:
                    hi = mid
            if good:
                cand = 0.5 * (lo + hi)
                if best is None or abs(cand - tof0) < abs(best - tof0):
                    best = cand
        return best

    # ---- correction par tirs d'essai (vitesse du joueur conservée)
    def refine(self, spec, plan: Plan, tol_km=1.0, max_iter=14,
               progress: Optional[Callable[[str], None]] = None) -> Plan:
        """Ajuste (longitude, latitude, heure de tir) pour annuler l'écart au point visé à la date
        d'arrivée prévue. La vitesse de bouche du joueur et l'instant d'arrivée sont conservés :
        la géométrie d'arrivée (face visible de la cible) reste donc valide."""
        say = progress or (lambda s: None)
        sys_ = self.system
        speed = plan.speed
        T = plan.t_arrival
        lon0, lat0 = plan.lon_lat
        tp = spec.target.point(sys_, T)

        def sim(x):
            cs = self.cannon.state(x[2])
            d = direction_vector(np.degrees(x[0]), np.degrees(x[1]))
            res = self.prop.run(x[2], cs.r_helio, add_velocity(cs.v_helio, speed * d), t_end=T,
                                stop_on_hit=False)
            return res.final_pos - tp.pos

        x = np.array([np.radians(lon0), np.radians(lat0), plan.t_launch])
        steps = np.array([5e-9, 5e-9, 10.0])
        f = sim(x)
        say(f"  écart initial : {np.linalg.norm(f):,.0f} km")
        J = np.empty((3, 3))
        for k in range(3):
            xp = x.copy()
            xp[k] += steps[k]
            J[:, k] = (sim(xp) - f) / steps[k]
        for it in range(max_iter):
            if np.linalg.norm(f) < tol_km:
                break
            step = -np.linalg.solve(J, f)
            lam = 1.0
            for _ in range(8):
                x_new = x + lam * step
                f_new = sim(x_new)
                if np.linalg.norm(f_new) < np.linalg.norm(f):
                    break
                lam *= 0.5
            else:
                break
            dx, df = x_new - x, f_new - f
            J = J + np.outer(df - J @ dx, dx) / (dx @ dx)
            x, f = x_new, f_new
            say(f"  itération {it + 1} : écart {np.linalg.norm(f):,.2f} km")
        d = direction_vector(np.degrees(x[0]), np.degrees(x[1]))
        return Plan(float(x[2]), T, speed * d, plan.v_inf, plan.arrival_speed, plan.visibility,
                    rod=None, refined=True, residual_km=float(np.linalg.norm(f)))
