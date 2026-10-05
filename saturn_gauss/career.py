"""Carrière : le monde de jeu unique (temps, argent, stations, contrats, tirs, événements)."""
import os
import pickle
from typing import List, Optional

import numpy as np

from .ballistics.cannon import (V_MAX_KMS, GaussCannon, add_velocity, direction_vector)
from .ballistics.integrator import Propagator
from .ballistics.projectile import Rod, gamma_minus_1, radius_for_mass
from .combat import damage as dmg
from .combat import engagement as eng
from .combat.ammo import AMMO, blast_energy_on_ship, blast_yield_j
from .combat.battle import retaliation
from .combat.launchers import LAUNCHERS, effective, energy_cap_j
from .combat.stations import CannonShooter, default_stations
from .constants import C_KMS, C_MS, DAY_S, GAME_START
from .contracts import (AsteroidOp, Contract, DefenseOp, FleetOp, StrikeOp, asteroid_miss,
                        initial_strikes, new_asteroid, new_attack, new_fleet_contract)
from .economy import (START_CREDITS, UPGRADES, assist_cost, shot_cost, upgrade_cost)
from .guidance import Guidance, Plan
from .solarsystem.rotation import great_circle_km
from .solarsystem.system import SolarSystem
from .timeutils import format_date, from_datetime

EJECTA_BETA = {"rod": 1.0, "ferrite": 0.6, "ap_he": 1.5, "dirty": 2.0, "gas": 0.2, "nuke": 2.0,
               "antimatter": 2.0, "beam": 0.0}


class GameError(ValueError):
    pass


class Career:
    def __init__(self, seed: int = 0, assist: bool = True):
        self.rng = np.random.default_rng(seed)
        self.assist_enabled = assist
        self.system = SolarSystem()
        self.cannon = GaussCannon(self.system)
        self.prop = Propagator(self.system)
        self.guidance = Guidance(self.system, self.cannon, self.prop)
        self.mu = self.cannon.mu
        self.t = from_datetime(GAME_START)
        self.credits = START_CREDITS
        self.rank = 0
        self.upgrades: dict = {}
        self.unlocked = {"canon", "gauss", "poudre"}
        self.earned = 0.0
        self.shooters = [CannonShooter(0, "Canon interplanétaire", "canon", 8e17, 3e17, 400_000.0,
                                       cannon=self.cannon)] + default_stations(self.mu)
        self.board: List[Contract] = []
        self._next_id = 1
        self.board += initial_strikes(self.t, self._next_id)
        self._next_id += len(self.board)
        self.focus: Optional[Contract] = None
        self.use_idx = 0
        self.ammo = "rod"
        self.length, self.radius, self.pulse_j = 10.0, 0.30, 1e15
        self.speed, self.lon, self.lat = 15.0, 180.0, 0.0
        self.target_sel = None                  # (id vaisseau, indice composant)
        self.messages: List[str] = []
        self.windows: List[Plan] = []
        self.plan: Optional[Plan] = None
        self.last_report: Optional[dict] = None
        self.next_attack = self.t + 2 * DAY_S
        self.next_offer = self.t + 12 * DAY_S
        self.next_asteroid = self.t + 120 * DAY_S
        self.log_earned: list = []
        self._interrupt = False

    # ------------------------------------------------------------------ utilitaires
    def say(self, msg: str):
        self.messages.append(msg)

    def pop_messages(self):
        m, self.messages = self.messages, []
        return m

    def contract(self, cid: int) -> Contract:
        for c in self.board:
            if c.id == cid:
                return c
        raise GameError(f"contrat {cid} introuvable")

    def _new_id(self):
        self._next_id += 1
        return self._next_id - 1

    @property
    def shooter(self):
        return self.shooters[self.use_idx]

    def launcher_of(self, shooter=None):
        sh = shooter or self.shooter
        return effective(LAUNCHERS[sh.launcher], self.upgrades)

    @property
    def projectile(self) -> Rod:
        return Rod(self.length, self.radius, AMMO[self.ammo].density)

    @property
    def ammo_spec(self):
        return AMMO[self.ammo]

    def kinetic_energy(self) -> float:
        lau = self.launcher_of()
        if lau.kind == "beam":
            return self.pulse_j
        return self.projectile.energy_j(self.speed)

    def mass_kg(self) -> float:
        return self.pulse_j / C_MS ** 2 if self.launcher_of().kind == "beam" else self.projectile.mass_kg

    def active_contracts(self):
        return [c for c in self.board if c.state == "active"]

    # ------------------------------------------------------------------ réglages du tir
    def use(self, idx: int):
        if not 0 <= idx < len(self.shooters):
            raise GameError(f"tireur inconnu (0-{len(self.shooters) - 1})")
        self.use_idx = idx
        lau = self.launcher_of()
        if self.ammo not in lau.ammo:
            self.ammo = lau.ammo[0]
        if lau.key in ("gauss", "rail"):
            self.length, self.radius = 0.3, 0.012
            self.speed = float(np.clip(0.7 * C_KMS, lau.v_min_kms, lau.v_max_kms))
        elif lau.key == "laser":
            self.speed, self.pulse_j = C_KMS, min(self.pulse_j, lau.max_mass_kg)
        elif lau.key == "poudre":
            self.length, self.radius, self.speed = 0.5, 0.05, 10.0
        self.target_sel = None

    def set_ammo(self, key: str):
        if key not in AMMO:
            raise GameError(f"munition inconnue : {', '.join(k for k in AMMO if k != 'beam')}")
        lau = self.launcher_of()
        if key not in lau.ammo:
            raise GameError(f"{lau.name} ne tire pas ce type de munition ({', '.join(lau.ammo)})")
        self.ammo = key

    def set_mass(self, m: float):
        """Masse voulue (kg) : on garde la longueur et on ajuste le rayon (puis la longueur si nécessaire)."""
        rho = AMMO[self.ammo].density
        lau = self.launcher_of()
        r = float(np.sqrt(m / (rho * np.pi * self.length)))
        if lau.max_radius_m and r > lau.max_radius_m:
            r = lau.max_radius_m
            self.length = m / (rho * np.pi * r * r)
        elif r < 2e-3:                       # barre trop fine : on la raccourcit plutôt que de la rendre filiforme
            r = 2e-3
            self.length = max(m / (rho * np.pi * r * r), 1e-3)
        self.radius = r

    def check_launcher(self, require_ready=True):
        lau = self.launcher_of()
        sh = self.shooter
        if not sh.online:
            raise GameError(f"{sh.name} est hors service (réparez-le : 'repair {sh.id}')")
        if lau.key not in self.unlocked and sh.launcher not in self.unlocked:
            raise GameError("lanceur non débloqué")
        if self.ammo not in lau.ammo:
            raise GameError(f"{lau.name} ne tire pas {self.ammo}")
        if lau.kind == "beam":
            if not 0 < self.pulse_j <= lau.max_mass_kg:
                raise GameError(f"impulsion hors limites (max {lau.max_mass_kg:.1e} J)")
        else:
            self.projectile.validate()
            if self.length > lau.max_length_m or self.radius > lau.max_radius_m:
                raise GameError(f"projectile trop grand pour {lau.name} (L ≤ {lau.max_length_m:g} m, r ≤ {lau.max_radius_m:g} m)")
            if self.projectile.mass_kg > lau.max_mass_kg:
                raise GameError(f"masse {self.projectile.mass_kg:.3g} kg > maximum {lau.max_mass_kg:.3g} kg")
            if not lau.v_min_kms <= self.speed <= lau.v_max_kms:
                raise GameError(f"vitesse hors plage : {lau.v_min_kms:,.1f} – {lau.v_max_kms:,.1f} km/s "
                                f"({lau.v_min_kms / C_KMS:.2f}c – {lau.v_max_kms / C_KMS:.3f}c)")
        if lau.key == "canon" and self.kinetic_energy() > energy_cap_j(self.upgrades):
            raise GameError(f"énergie {self.kinetic_energy():.2e} J > capacité {energy_cap_j(self.upgrades):.1e} J")
        if require_ready and sh.ready_at > self.t + 1e-6:
            raise GameError(f"{sh.name} recharge encore {sh.ready_at - self.t:.0f} s")

    def cost_preview(self) -> dict:
        lau = self.launcher_of()
        return shot_cost(AMMO[self.ammo], lau, self.mass_kg(), self.kinetic_energy())

    # ------------------------------------------------------------------ contrats
    def accept(self, cid: int):
        c = self.contract(cid)
        if c.state != "offered":
            raise GameError("ce contrat n'est pas proposé")
        c.state = "active"
        self.focus = c
        self.say(f"Contrat accepté : {c.title}")

    def refuse(self, cid: int):
        c = self.contract(cid)
        if c.priority:
            raise GameError("les missions prioritaires ne peuvent pas être refusées")
        if c.state != "offered":
            raise GameError("ce contrat n'est pas proposé")
        c.state = "refused"

    def set_focus(self, cid: int):
        c = self.contract(cid)
        if c.state not in ("active", "offered"):
            raise GameError("contrat terminé")
        self.focus = c
        self.windows, self.plan, self.target_sel = [], None, None
        if c.kind == "defense":
            self.use_best_station()
        elif self.use_idx != 0:
            self.use(0)

    def use_best_station(self):
        if self.focus is None or self.focus.kind != "defense":
            return
        ships = [s for s in self.focus.op.battle.ships if not s.neutralized]
        if not ships or self.use_idx != 0 and self.shooter.online:
            return
        for sh in self.shooters[1:]:
            if sh.online:
                self.use(sh.id)
                return

    # ------------------------------------------------------------------ temps et événements
    def advance(self, dt: float, interruptible: bool = False) -> float:
        """Fait passer le temps. Si `interruptible`, s'arrête à l'apparition d'un événement prioritaire.
        Retourne la durée réellement écoulée."""
        remaining = float(dt)
        t_start = self.t
        self._interrupt = False
        while remaining > 1e-9:
            step = remaining
            if any(c.kind == "defense" and c.state == "active" for c in self.board):
                step = min(remaining, 15.0 if self._battle_close() else 300.0)
            else:
                step = min(remaining, 3600.0 * 6)
            self._step(step)
            remaining -= step
            if interruptible and self._interrupt:
                self.say("⏸ Temps interrompu : événement prioritaire.")
                break
        return self.t - t_start

    def _battle_close(self) -> bool:
        for c in self.board:
            if c.kind == "defense" and c.state == "active":
                for s in c.op.battle.ships:
                    if not s.neutralized and np.linalg.norm(s.state(self.t)[0]) < 1.4e6:
                        return True
        return False

    def _step(self, dt):
        t_old = self.t
        self.t += dt
        any_battle = False
        for c in self.board:
            if c.kind == "defense" and c.state == "active":
                any_battle = True
                b = c.op.battle
                b.step(t_old, dt, self.shooters, self.say)
                if b.state != "ongoing":
                    self._end_defense(c)
        if not any_battle:
            for s in self.shooters:
                s.regen(dt)
        self._world_tick()

    def _end_defense(self, c: Contract):
        b = c.op.battle
        bounty = sum(s.bounty for s in b.ships)
        if b.state == "won":
            c.state = "done"
            self._pay(bounty, f"Attaque repoussée : prime {bounty:,.0f} cr".replace(",", " "))
            self.rank += 1
        else:
            pen = sum(s.spec.penalty for s in b.ships if not s.neutralized)
            c.state = "failed"
            self.credits -= pen
            self._pay(bounty, f"Primes partielles : {bounty:,.0f} cr".replace(",", " "))
            self.say(f"ÉCHEC : l'ennemi a atteint Saturne. Dommages : -{pen:,.0f} cr".replace(",", " "))

    def _pay(self, amount, text):
        self.credits += amount
        self.earned += amount
        self.say(text)

    def _world_tick(self):
        t = self.t
        # offres expirées et contrats échus
        for c in self.board:
            if c.state == "offered" and c.offer_until is not None and t > c.offer_until:
                c.state = "expired"
            if c.state == "active" and c.kind in ("fleet", "protect") and t > c.deadline:
                self._fleet_deadline(c)
            if c.state == "active" and c.kind == "asteroid" and t > c.op.t_impact:
                self._asteroid_deadline(c)
        # génération
        if t >= self.next_attack:
            c = new_attack(self.system, t, self.rank, self.rng, self._new_id(), self.mu)
            self.board.append(c)
            self.next_attack = t + float(self.rng.uniform(25, 50)) * DAY_S
            self.say(f"⚠ ÉVÉNEMENT PRIORITAIRE #{c.id} : {c.text}")
            self._interrupt = True
            if self.focus is None or self.focus.kind != "defense":
                self.focus = c
                self.use_best_station()
        if t >= self.next_asteroid:
            c = new_asteroid(self.system, t, self.rng, self._new_id())
            self.board.append(c)
            self.next_asteroid = t + float(self.rng.uniform(150, 260)) * DAY_S
            self.say(f"⚠ ÉVÉNEMENT PRIORITAIRE #{c.id} : {c.text}")
            self._interrupt = True
        if t >= self.next_offer:
            if sum(1 for c in self.board if c.state == "offered" and c.kind in ("fleet", "protect", "asteroid")) < 3:
                r = self.rng.random()
                if r < 0.25:
                    c = new_asteroid(self.system, t, self.rng, self._new_id(), priority=False)
                else:
                    c = new_fleet_contract(self.system, t, self.rank, self.rng, self._new_id(), protect=r > 0.6)
                self.board.append(c)
                self.say(f"Nouveau contrat #{c.id} : {c.title} (récompense {c.reward:,.0f} cr)".replace(",", " "))
            self.next_offer = t + float(self.rng.uniform(10, 20)) * DAY_S

    def _fleet_deadline(self, c: Contract):
        op: FleetOp = c.op
        alive = [s for s in op.ships if not s.neutralized]
        bounty = sum(s.bounty for s in op.ships)
        if not alive:
            return
        c.state = "failed"
        self._pay(0.5 * bounty if c.kind == "fleet" else 0.0, f"Contrat #{c.id} échu : {len(alive)} vaisseaux ont survécu.")
        if c.kind == "protect":
            self.credits -= c.penalty
            self.say(f"La colonie de {op.protect} est attaquée. Pénalité : -{c.penalty:,.0f} cr".replace(",", " "))
        if self.rng.random() < 0.5:
            b = retaliation(alive, self.t, self.rng, self.mu)
            n = self._new_id()
            from .combat.battle import eta_to_objective
            eta = eta_to_objective(b.ships, self.t, b.objective_km)
            nc = Contract(n, "defense", "RIPOSTE SUR SATURNE", "Les survivants de la flotte attaquent Saturne !", True,
                          sum(s.spec.value for s in alive), sum(s.spec.penalty for s in alive), self.t, eta,
                          DefenseOp(b), state="active")
            self.board.append(nc)
            self.say(f"⚠ RIPOSTE #{n} : {len(alive)} vaisseaux foncent sur Saturne (arrivée dans {(eta - self.t) / 3600:.1f} h).")

    def _asteroid_deadline(self, c: Contract):
        op: AsteroidOp = c.op
        if op.miss_km >= 1.3 * op.b_crit_km:
            return
        c.state = "failed"
        self.credits -= c.penalty
        self.say(f"CATASTROPHE : l'astéroïde frappe {op.threatened}. Pénalité : -{c.penalty:,.0f} cr".replace(",", " "))

    # ------------------------------------------------------------------ tir
    def fire(self) -> dict:
        self.check_launcher()
        if self.focus is None or self.focus.state != "active":
            raise GameError("aucun contrat actif : 'accept <n>' ou 'focus <n>' d'abord")
        sh, lau = self.shooter, self.launcher_of()
        cost = self.cost_preview()
        if cost["total"] > self.credits:
            raise GameError(f"fonds insuffisants : {cost['total']:,.0f} cr requis".replace(",", " "))
        c = self.focus
        if isinstance(c.op, DefenseOp):
            rep = self._fire_ship(c, sh, lau, cost)
        else:
            if sh.launcher != "canon":
                raise GameError("seul le canon interplanétaire peut atteindre cette cible ('use 0')")
            rep = self._fire_planetary(c, sh, lau, cost)
        self.credits -= cost["total"]
        sh.ready_at = self.t + lau.reload_s
        rep["cost"] = cost["total"]
        self.last_report = rep
        return rep

    # -- vaisseaux
    def _fire_ship(self, c, sh, lau, cost):
        battle = c.op.battle
        origin, _ = sh.rel_state(self.t)
        d = direction_vector(self.lon, self.lat)
        vp = C_KMS if lau.kind == "beam" else self.speed
        E, ammo = self.kinetic_energy(), self.ammo_spec
        rep = {"kind": "ship", "hit": False, "lines": []}
        hit = eng.locate_hit(origin, d, vp, battle.ships, self.t)
        ship_sel = None
        if self.target_sel:
            ship_sel = next((s for s in battle.ships if s.id == self.target_sel[0]), None)
        if hit is not None and hit[0] != "saturne" and hit[0] > lau.max_range_km:
            rep["lines"].append(f"Impact au-delà de la portée du lanceur ({lau.max_range_km:,.0f} km) : projectile perdu.".replace(",", " "))
            hit = None
        if hit is None:
            rep["lines"].append("RATÉ : le projectile ne rencontre aucun composant.")
            if ship_sel is not None:
                m = eng.miss_report(origin, d, ship_sel, self.target_sel[1], self.t, vp)
                rep["miss"] = m
                rep["lines"].append(
                    f"  Écart au centre de « {ship_sel.comps[self.target_sel[1]].name} » : {m['distance_m']:,.1f} m "
                    f"(avant {m['avant_m']:+,.1f} m, gauche {m['gauche_m']:+,.1f} m, haut {m['haut_m']:+,.1f} m)".replace(",", " "))
        elif hit[0] == "saturne":
            rep["lines"].append("Le tir est arrêté par Saturne.")
        else:
            dist, ship, idx, tau = hit
            rep["hit"], rep["ship"], rep["comp"] = True, ship.name, ship.comps[idx].name
            comp = ship.comps[idx]
            r = dmg.apply_hit(ship, idx, ammo, E, self.length, self.mass_kg())
            ship.last_attacker = sh.id
            rep["lines"].append(f"TOUCHÉ : {ship.name} → {comp.name} (distance {dist:,.0f} km, vol {tau:.2f} s)".replace(",", " "))
            rep["lines"].append(f"  {r['text']}")
            if ship.destroyed:
                rep["lines"].append(f"  ★ {ship.name} DÉTRUIT")
            elif ship.neutralized:
                rep["lines"].append(f"  ★ {ship.name} NEUTRALISÉ")
            rep["ship_status"] = ship.status
        tau = rep.get("miss", {}).get("tau_s") or (hit[3] if (hit is not None and hit[0] != "saturne") else 1.0)
        self.advance(max(1.0, float(tau)))
        return rep

    # -- interplanétaire
    def _closest_approach(self, target, t0, r0, v0, t_guess):
        t_end = t_guess
        for _ in range(10):
            res = self.prop.run(t0, r0, v0, t_end=t_end, stop_on_hit=False)
            tp = target.point(self.system, t_end)
            rel, vrel = res.final_pos - tp.pos, res.final_vel - tp.vel
            ts = -(rel @ vrel) / (vrel @ vrel)
            if abs(ts) < max(1e-4, 1e-8 * (t_end - t0)):
                break
            t_end = max(t_end + ts, t0 + 1e-3)
        ts = -(rel @ vrel) / (vrel @ vrel)
        return float(np.linalg.norm(rel + vrel * ts)), t_end, res, tp

    def _guess_arrival(self, target, t0, r0, speed_helio):
        t = t0 + 1.0
        for _ in range(6):
            t = t0 + float(np.linalg.norm(target.point(self.system, t).pos - r0)) / max(speed_helio, 1e-3)
        return t

    def _fire_planetary(self, c, sh, lau, cost):
        cs = self.cannon.state(self.t)
        d = direction_vector(self.lon, self.lat)
        v0 = add_velocity(cs.v_helio, self.speed * d)
        op, E = c.op, self.kinetic_energy()
        rep = {"kind": "planetary", "lines": []}
        if isinstance(op, StrikeOp):
            res = self.prop.run(self.t, cs.r_helio, v0)
            rep["result"] = res
            self._eval_strike(c, op, res, rep, E)
            return rep
        target = op.target if isinstance(op, FleetOp) else op.asteroid
        tg = self._guess_arrival(target, self.t, cs.r_helio, float(np.linalg.norm(v0)))
        miss, t_end, res, tp = self._closest_approach(target, self.t, cs.r_helio, v0, tg)
        rep["result"], rep["miss_km"], rep["t_end"] = res, miss, t_end
        flight = t_end - self.t
        rep["lines"].append(f"Vol de {flight / 3600:,.2f} h ; plus proche approche de la cible : {miss:,.3f} km.".replace(",", " "))
        if isinstance(op, FleetOp):
            self._eval_fleet(c, op, res, tp, t_end, miss, E, rep)
        else:
            self._eval_asteroid(c, op, res, tp, t_end, miss, rep)
        return rep

    def _eval_strike(self, c, op: StrikeOp, res, rep, E):
        body = self.system.get(op.target.body)
        hit = res.outcome == "impact" and res.body == body.name
        miss = great_circle_km(res.impact_lat, res.impact_lon, op.target.lat, op.target.lon, body.radius) if hit else None
        e_ok = abs(E - op.energy_j) <= op.energy_tol * op.energy_j
        pen = self.projectile.penetration_m(body.surface_density)
        pen_ok = (op.min_penetration_m is None) or pen >= op.min_penetration_m
        flight_ok = True
        if op.max_flight_days and hit:
            flight_ok = (res.t_end - res.t_start) / DAY_S <= op.max_flight_days
        ok = bool(hit and miss <= op.tolerance_km and e_ok and pen_ok and flight_ok)
        rep.update(hit=hit, miss_km=miss, energy_ok=e_ok, pen_ok=pen_ok, flight_ok=flight_ok, success=ok, pen_m=pen,
                   energy_j=E)
        if ok:
            bonus = int(0.5 * c.reward * (1 - miss / op.tolerance_km))
            c.state = "done"
            self.rank += 1
            self._pay(c.reward + bonus, f"MISSION ACCOMPLIE : +{c.reward:,.0f} cr (+{bonus:,.0f} de précision)".replace(",", " "))

    def _eval_fleet(self, c, op: FleetOp, res, tp, t_end, miss, E, rep):
        if t_end > c.deadline:
            rep["lines"].append(f"Impact prévu {format_date(t_end)} : APRÈS l'échéance du contrat ({format_date(c.deadline)}).")
        ammo, mass = self.ammo_spec, self.mass_kg()
        positions = op.ship_positions(self.system, t_end)
        dists = [float(np.linalg.norm(res.final_pos - p)) for p in positions]
        if ammo.blast_eff > 0:
            Y = blast_yield_j(ammo, mass, E)
            rep["lines"].append(f"Détonation de proximité : charge {Y:.2e} J ({Y / 4.184e15:,.1f} Mt).".replace(",", " "))
            for s, dd in zip(op.ships, dists):
                if s.destroyed:
                    continue
                Ei = blast_energy_on_ship(ammo, Y, dd)
                r = dmg.apply_blast(s, Ei)
                rep["lines"].append(f"  {s.name:<18} à {dd:9,.1f} km : {Ei:.2e} J reçus -> {s.status} "
                                    f"(bouclier {100 * s.shield / s.shield_max:.0f} %)".replace(",", " "))
        else:
            near = [(dd, s) for s, dd in zip(op.ships, dists) if dd < 0.3 and not s.destroyed]
            if near:
                dd, s = min(near, key=lambda x: x[0])
                r = dmg.apply_hit(s, 0, ammo, E, self.length, mass)
                rep["lines"].append(f"Impact direct sur {s.name} : {r['text']}")
            else:
                rep["lines"].append("Sans détonation de proximité (nuke / antimatter / dirty), un tir cinétique "
                                    "doit toucher un vaisseau (< 300 m). Aucun effet.")
        left = [s for s in op.ships if not s.neutralized]
        rep["survivors"] = len(left)
        if not left and c.state == "active":
            c.state = "done"
            self.rank += 1
            bounty = sum(s.bounty for s in op.ships)
            self._pay(c.reward + 0.0 * bounty, f"FLOTTE ANÉANTIE : +{c.reward:,.0f} cr".replace(",", " "))
            rep["success"] = True
        else:
            rep["lines"].append(f"Vaisseaux restants : {len(left)}/{len(op.ships)}")

    def _eval_asteroid(self, c, op: AsteroidOp, res, tp, t_end, miss, rep):
        ast = op.asteroid
        if miss > ast.radius_km:
            rep["lines"].append(f"RATÉ : il fallait passer à moins de {ast.radius_km * 1000:.0f} m du centre "
                                f"({miss * 1000:,.0f} m).".replace(",", " "))
            return
        ammo, mass = self.ammo_spec, self.mass_kg()
        vrel_vec = res.final_vel - tp.vel
        vrel = float(np.linalg.norm(vrel_vec))
        gam = 1.0 + gamma_minus_1(min(vrel, 0.9999999 * C_KMS))
        p = gam * mass * vrel * 1e3
        beta = EJECTA_BETA.get(self.ammo, 1.0)
        if ammo.bomb:
            p += 0.02 * ammo.specific_yield * mass / 2e4
        dv = (1 + beta) * p / ast.mass_kg / 1e3
        new_v = tp.vel + dv * vrel_vec / vrel
        from .targets import AsteroidTarget
        op.asteroid = AsteroidTarget(t_end, tp.pos.copy(), new_v, ast.radius_km, ast.mass_kg)
        op.shots += 1
        op.miss_km, _, _ = asteroid_miss(op.asteroid, self.system, op.threatened, op.t_impact)
        op.history.append((t_end, op.miss_km))
        need = 1.3 * op.b_crit_km
        rep["lines"].append(f"IMPACT sur l'astéroïde : Δv = {dv * 1000:.3f} m/s (facteur d'éjectas {1 + beta:.1f}).")
        rep["lines"].append(f"  Distance de passage prévue : {op.miss_km:,.0f} km (sécurité : {need:,.0f} km).".replace(",", " "))
        rep["miss_new_km"] = op.miss_km
        if op.miss_km >= need:
            c.state = "done"
            self.rank += 1
            self._pay(c.reward, f"ASTÉROÏDE DÉVIÉ : +{c.reward:,.0f} cr".replace(",", " "))
            rep["success"] = True

    # ------------------------------------------------------------------ aide au calcul (payante)
    def solve_aim(self):
        """Visée exacte sur le composant désigné (ordinateur de bord, payant)."""
        if self.focus is None or not isinstance(self.focus.op, DefenseOp):
            raise GameError("'solve' sert au combat contre des vaisseaux (focus sur une attaque)")
        if not self.target_sel:
            raise GameError("désignez d'abord un composant : 'target <vaisseau>.<composant>'")
        fee = assist_cost("solve", self.upgrades)
        if fee > self.credits:
            raise GameError("fonds insuffisants")
        ship = next(s for s in self.focus.op.battle.ships if s.id == self.target_sel[0])
        origin, _ = self.shooter.rel_state(self.t)
        lau = self.launcher_of()
        vp = C_KMS if lau.kind == "beam" else self.speed
        lon, lat, tau, dist = eng.solve_aim(origin, ship, self.target_sel[1], self.t, vp)
        self.credits -= fee
        self.lon, self.lat = lon, lat
        return lon, lat, tau, dist, fee

    # ------------------------------------------------------------------ boutique
    def buy(self, key: str):
        if key in LAUNCHERS and key not in ("canon",):
            lau = LAUNCHERS[key]
            if key in self.unlocked:
                raise GameError("déjà débloqué")
            if self.credits < lau.unlock_cost:
                raise GameError(f"{lau.unlock_cost:,.0f} cr requis".replace(",", " "))
            self.credits -= lau.unlock_cost
            self.unlocked.add(key)
            self.say(f"{lau.name} débloqué (utilisez 'refit <station> {key}').")
            return
        if key not in UPGRADES:
            raise GameError("inconnu : " + ", ".join(list(UPGRADES) + [k for k in LAUNCHERS if k != 'canon']))
        up, lvl = UPGRADES[key], int(self.upgrades.get(key, 0))
        if lvl >= up.max_level:
            raise GameError("niveau maximum atteint")
        cost = upgrade_cost(key, lvl)
        if cost > self.credits:
            raise GameError(f"{cost:,.0f} cr requis".replace(",", " "))
        self.credits -= cost
        self.upgrades[key] = lvl + 1
        if key in ("blindage", "boucliers"):
            for s in self.shooters:
                if key == "blindage":
                    s.hp_max *= 1.5
                    s.hp *= 1.5
                else:
                    s.shield_max *= 1.5
                    s.shield *= 1.5
        self.say(f"Amélioration achetée : {up.name} niveau {lvl + 1} (-{cost:,.0f} cr)".replace(",", " "))

    def repair(self, which):
        targets = self.shooters if which == "all" else [self.shooters[int(which)]]
        total = sum(s.repair_cost for s in targets)
        if total <= 0:
            raise GameError("rien à réparer")
        if total > self.credits:
            raise GameError(f"{total:,.0f} cr requis".replace(",", " "))
        self.credits -= total
        for s in targets:
            s.hp, s.shield = s.hp_max, s.shield_max
        self.say(f"Réparations effectuées : -{total:,.0f} cr".replace(",", " "))

    def refit(self, idx: int, launcher: str):
        if launcher not in LAUNCHERS or launcher == "canon":
            raise GameError("lanceurs : gauss, rail, laser, poudre")
        if launcher not in self.unlocked:
            raise GameError("lanceur non débloqué ('buy " + launcher + "')")
        if idx == 0:
            raise GameError("le canon interplanétaire ne se remplace pas")
        fee = 5000.0
        if fee > self.credits:
            raise GameError("5 000 cr requis")
        self.credits -= fee
        self.shooters[idx].launcher = launcher
        if idx == self.use_idx:
            self.use(idx)
        self.say(f"{self.shooters[idx].name} équipé de : {LAUNCHERS[launcher].name} (-5 000 cr)")

    # ------------------------------------------------------------------ guidage interplanétaire
    def focus_spec(self):
        if self.focus is None or isinstance(self.focus.op, DefenseOp):
            raise GameError("le guidage sert aux cibles lointaines (frappe, flotte, astéroïde)")
        op = self.focus.op
        spec = op.spec(self.system)
        if isinstance(op, AsteroidOp):
            spec.max_flight_days = max((op.t_impact - self.t) / DAY_S - 1.0, 1.0)
            spec.t_latest = op.t_impact - DAY_S
        elif isinstance(op, FleetOp):
            spec.max_flight_days = max(min(op.max_flight_days, (self.focus.deadline - self.t) / DAY_S), 0.05)
            spec.t_latest = self.focus.deadline
        return spec

    def find_windows(self, auto=False, max_days=None, progress=None):
        if not self.assist_enabled:
            raise GameError("l'ordinateur de bord est désactivé (--no-assist)")
        spec = self.focus_spec()
        fee = assist_cost("window", self.upgrades)
        if fee > self.credits:
            raise GameError("fonds insuffisants")
        self.credits -= fee
        speed = None if auto else self.speed
        self.windows = self.guidance.find_windows(spec, self.t, speed=speed, progress=progress,
                                                  max_flight_days=max_days)
        return self.windows, fee

    def apply_plan(self, plan: Plan):
        if plan.t_launch >= self.t:
            self.advance(plan.t_launch - self.t, interruptible=True)
            if self.t < plan.t_launch - 1e-6:
                self.plan = None
                raise GameError("plan interrompu par un événement prioritaire : traitez-le, puis relancez "
                                "'window' / 'plan' (les dates de tir sont recalculées).")
        else:
            self.t = plan.t_launch
        self.speed = plan.speed
        from .ballistics.cannon import direction_angles
        self.lon, self.lat = direction_angles(plan.v0_vec)
        if plan.rod is not None and self.ammo == "rod":
            self.length, self.radius = plan.rod.length_m, plan.rod.radius_m
        self.plan = plan

    def refine(self, plan: Plan, progress=None) -> Plan:
        if not self.assist_enabled:
            raise GameError("l'ordinateur de bord est désactivé (--no-assist)")
        spec = self.focus_spec()
        fee = assist_cost("refine", self.upgrades)
        if fee > self.credits:
            raise GameError("fonds insuffisants")
        self.credits -= fee
        tol = 1.0
        if isinstance(spec.target, type(getattr(self.focus.op, "asteroid", None))) and hasattr(spec.target, "radius_km"):
            tol = min(1.0, 0.25 * spec.target.radius_km)
        return self.guidance.refine(spec, plan, tol_km=tol, progress=progress)

    # ------------------------------------------------------------------ sauvegarde
    def save(self, path: str):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @staticmethod
    def load(path: str) -> "Career":
        with open(path, "rb") as f:
            return pickle.load(f)
