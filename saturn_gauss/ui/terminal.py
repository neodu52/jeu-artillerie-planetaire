"""Interface terminal : une seule session pour tous les modes de jeu."""
import cmd
import json
import math
import os

import numpy as np

from ..ballistics.cannon import direction_angles, direction_vector
from ..ballistics.projectile import gamma_minus_1, mass_for_energy, speed_for_energy
from ..career import Career, GameError
from ..combat import engagement as eng
from ..combat.ammo import AMMO, penetration_m
from ..combat.launchers import LAUNCHERS, effective, energy_cap_j
from ..constants import AU_KM, C_KMS, DAY_S, MT_TNT_J
from ..contracts import AsteroidOp, DefenseOp, FleetOp, StrikeOp
from ..economy import UPGRADES, assist_cost, upgrade_cost
from ..guidance import Plan
from ..timeutils import format_date, parse_date, parse_duration
from . import formatting as fm
from .formatting import BOLD, CYAN, DIM, GREEN, RED, YELLOW, c, fmt_duration, fmt_mass, fmt_speed, money
from . import shipview

HELP = """
{b}CONTRATS ET ÉVÉNEMENTS{r}
  board                 tableau des contrats (⚠ = prioritaire, non refusable)
  accept <n> / refuse <n>   accepter / refuser un contrat optionnel
  focus <n>             travailler sur le contrat n          brief : rappel du contrat courant
{b}TIREURS ET MUNITIONS{r}
  stations              les tireurs : état, distance, visibilité de la cible
  use <n>               choisir le tireur (0 = canon interplanétaire, 1.. = stations)
  ammo [type]           munitions disponibles / choisir           cost : coût du tir courant
  set <param> <val>     longueur | rayon | masse | vitesse (km/s, 0.9c, 90%) | lon | lat | impulsion
  rod <L> <R>   aim <lon> <lat>   match vitesse|rayon|masse   (énergie demandée par le contrat)
{b}COMBAT CONTRE DES VAISSEAUX{r}
  ships | ship <n>      liste des vaisseaux / composants + dessin vu du tireur actuel
  target <n>.<pièce>    désigner un composant (ex: target 1.reactor, target 2.3)
  solve                 ordinateur de bord : visée exacte sur la cible (payant)
  calc <expr>           calculatrice (variables P, V, S, d, tau, vp, c ; sin, cos, atan2, norm, ...)
  view                  fenêtre graphique du vaisseau (ou PNG si pas d'écran)
{b}TIR INTERPLANÉTAIRE (frappes, flottes, astéroïdes){r}
  window [auto] [jours]   fenêtres de tir pour VOTRE vitesse (auto : vitesse optimale)   (payant)
  plan <n>   refine       charger une fenêtre / corriger par tirs d'essai                 (payant)
{b}TIR, TEMPS, ÉCONOMIE{r}
  fire                  tirer !                          wait <durée> | goto <date>
  upgrades | buy <clé>  améliorations et nouveaux lanceurs   repair <n|all> | refit <n> <lanceur>
  plot [system] | system [inner]   graphes et carte du système solaire
  save [nom] | load [nom] | quit
{b}REPÈRE{r} : toutes les directions sont écliptiques (longitude 0° = équinoxe, latitude +90° = pôle nord).
Les coordonnées de combat sont relatives au centre de Saturne (km).
"""


class GameShell(cmd.Cmd):
    prompt = "> "

    def __init__(self, career: Career, plots=True, save_only=False, save_dir="plots", saves_dir="saves"):
        super().__init__()
        self.k = career
        self.plots, self.save_only = plots, save_only
        self.save_dir, self.saves_dir = save_dir, saves_dir
        self._refresh_prompt()

    # ------------------------------------------------------------------ infrastructure
    def _refresh_prompt(self):
        k = self.k
        self.prompt = c(f"[{format_date(k.t)} | {money(k.credits)} | tireur {k.use_idx}] > ", CYAN)

    def _flush(self):
        for m in self.k.pop_messages():
            print(c(m, YELLOW if ("⚠" in m or "ÉCHEC" in m or "!!" in m or "CATASTROPHE" in m) else GREEN))

    def postcmd(self, stop, line):
        self._flush()
        self._refresh_prompt()
        return stop

    def preloop(self):
        self._flush()

    def emptyline(self):
        pass

    def default(self, line):
        print(c(f"Commande inconnue : {line.split()[0]!r}. Tapez 'help'.", YELLOW))

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except (GameError, ValueError, KeyError, IndexError) as e:
            print(c(f"Erreur : {e}", RED))
        return False

    def cmdloop(self, intro=None):
        while True:
            try:
                return super().cmdloop(intro)
            except KeyboardInterrupt:
                print("\n(Ctrl+C : tapez 'quit' pour quitter)")
                intro = ""

    def do_help(self, arg):
        on = fm._USE_COLOR
        print(HELP.format(b=BOLD if on else "", r="\033[0m" if on else ""))

    # ------------------------------------------------------------------ contrats
    def do_board(self, arg):
        k = self.k
        rows = []
        for ct in k.board:
            if ct.state in ("refused", "expired") and not arg:
                continue
            dl = "-" if ct.deadline is None else fmt_duration(ct.deadline - k.t) if ct.deadline > k.t else "échu"
            mark = ("⚠ " if ct.priority else "") + ("▶ " if k.focus is ct else "")
            rows.append((ct.id, mark + ct.kind, ct.state, ct.title[:38], money(ct.reward), dl))
        print(fm.table(rows, ("#", "type", "état", "titre", "récompense", "échéance")))
        print(f"Crédits : {money(k.credits)} | rang {k.rank} | gains cumulés {money(k.earned)}")
    do_missions = do_board
    do_contrats = do_board

    def do_accept(self, arg):
        self.k.accept(int(arg))
        self.do_brief("")

    def do_refuse(self, arg):
        self.k.refuse(int(arg))
        print("Contrat refusé.")

    def do_focus(self, arg):
        self.k.set_focus(int(arg))
        self.do_brief("")

    def do_brief(self, arg):
        k, ct = self.k, self.k.focus
        if ct is None:
            print("Aucun contrat sélectionné ('board' puis 'accept <n>' ou 'focus <n>').")
            return
        op = ct.op
        print(c(f"#{ct.id} {ct.title}", BOLD, CYAN) + (c("  [PRIORITAIRE]", RED) if ct.priority else ""))
        print(ct.text)
        print(f"  Récompense : {money(ct.reward)}" + (f" | pénalité d'échec : {money(ct.penalty)}" if ct.penalty else ""))
        if ct.deadline:
            print(f"  Échéance : {format_date(ct.deadline)} (dans {fmt_duration(ct.deadline - k.t)})" if ct.deadline > k.t else "  Échéance dépassée.")
        if isinstance(op, StrikeOp):
            print(f"  Cible : {op.target.body}, lat {op.target.lat:+.2f}°, lon {op.target.lon:+.2f}° | précision {op.tolerance_km:g} km")
            print(f"  Énergie à la bouche : {op.energy_j:.3e} J ({op.energy_j / MT_TNT_J:.3g} Mt) ± {op.energy_tol * 100:g} %")
            if op.min_penetration_m:
                print(f"  Pénétration minimale : {op.min_penetration_m:g} m")
            if op.max_flight_days:
                print(f"  Délai maximal de vol : {op.max_flight_days:g} jours")
        elif isinstance(op, FleetOp):
            i = k.system.index(op.target.planet)
            p = op.target.point(k.system, k.t).pos
            print(f"  Orbite autour de {op.target.planet} : rayon {op.target.radius_km:,.0f} km | distance de Saturne {np.linalg.norm(p - k.system.positions(k.t)[k.system.index('Saturne')]) / AU_KM:.2f} UA".replace(",", " "))
            for s in op.ships:
                print(f"   - {s.name:<20} {s.status:<10} bouclier {100 * s.shield / s.shield_max:3.0f} % | prime {money(s.spec.value)}")
            print("  Munitions conseillées : nuke / antimatter / dirty (détonation de proximité). Vol maximal : "
                  f"{op.max_flight_days:.1f} j -> utilisez de très hautes vitesses.")
        elif isinstance(op, AsteroidOp):
            a = op.asteroid
            print(f"  Astéroïde : diamètre {2000 * a.radius_km:.0f} m, masse {a.mass_kg:.2e} kg, v_inf {op.v_inf:.1f} km/s")
            print(f"  Impact sur {op.threatened} le {format_date(op.t_impact)} | passage prévu à {op.miss_km:,.0f} km du centre "
                  f"(il faut ≥ {1.3 * op.b_crit_km:,.0f} km) | tirs déjà reçus : {op.shots}".replace(",", " "))
        elif isinstance(op, DefenseOp):
            self.do_ships("")

    def do_status(self, arg):
        k = self.k
        sh, lau = k.shooter, k.launcher_of()
        print(c("=== ÉTAT ===", BOLD))
        print(f"Date : {format_date(k.t)} | crédits : {money(k.credits)} | rang {k.rank}")
        print(f"Tireur {sh.id} : {sh.name} — {lau.name} | structure {100 * sh.hp / sh.hp_max:.0f} % | bouclier {100 * sh.shield / sh.shield_max:.0f} %")
        if lau.kind == "beam":
            print(f"Impulsion : {k.pulse_j:.3e} J (max {lau.max_mass_kg:.2e}) | vitesse c")
        else:
            lim = f"v {lau.v_min_kms / C_KMS:.3f}c–{lau.v_max_kms / C_KMS:.3f}c" if lau.v_max_kms > 1000 else f"v {lau.v_min_kms:g}–{lau.v_max_kms:g} km/s"
            print(f"Limites : {lim}, masse ≤ {lau.max_mass_kg:.3g} kg, L ≤ {lau.max_length_m:g} m, r ≤ {lau.max_radius_m:g} m, portée {lau.max_range_km:,.0f} km".replace(",", " "))
            print(f"Munition : {AMMO[k.ammo].name} | L = {k.length:g} m, r = {k.radius:g} m → {fmt_mass(k.projectile.mass_kg)}")
            print(f"Vitesse : {fmt_speed(k.speed)}")
        print(f"Visée : longitude {k.lon:.6f}°, latitude {k.lat:+.6f}°")
        E = k.kinetic_energy()
        print(f"Énergie du tir : {E:.3e} J ({E / MT_TNT_J:.4g} Mt)" + (f" | cible {k.focus.op.energy_j:.3e} J ({100 * (E / k.focus.op.energy_j - 1):+.2f} %)" if k.focus and isinstance(k.focus.op, StrikeOp) else ""))
        co = k.cost_preview()
        print(f"Coût du tir : {money(co['total'])} (munition {money(co['munition'])} + énergie {money(co['energie'])})")
        if k.target_sel and k.focus and isinstance(k.focus.op, DefenseOp):
            s = next(x for x in k.focus.op.battle.ships if x.id == k.target_sel[0])
            print(f"Cible désignée : {s.name} / {s.comps[k.target_sel[1]].name}")

    def do_cost(self, arg):
        co = self.k.cost_preview()
        print(f"Munition {money(co['munition'])} | énergie consommée {co['energie_j']:.2e} J = {money(co['energie'])} | total {money(co['total'])}")

    # ------------------------------------------------------------------ tireurs / munitions
    def do_stations(self, arg):
        k = self.k
        rows = []
        battle = k.focus.op.battle if k.focus and isinstance(k.focus.op, DefenseOp) else None
        ship = None
        if battle and k.target_sel:
            ship = next((s for s in battle.ships if s.id == k.target_sel[0]), None)
        for s in k.shooters:
            lau = effective(LAUNCHERS[s.launcher], k.upgrades)
            r, _ = s.rel_state(k.t)
            row = [s.id + 0, s.name, lau.key, f"{np.linalg.norm(r):,.0f}".replace(",", " "),
                   f"{100 * s.hp / s.hp_max:.0f}%", f"{100 * s.shield / s.shield_max:.0f}%",
                   "OK" if s.online else "HORS SERVICE", "prêt" if s.ready_at <= k.t else f"{s.ready_at - k.t:.0f}s"]
            if ship is not None:
                vp = C_KMS if lau.kind == "beam" else min(max(k.speed, lau.v_min_kms), lau.v_max_kms)
                pos, _ = ship.state(k.t)
                dist = np.linalg.norm(pos - r)
                ok, why = eng.visibility(r, ship, k.target_sel[1], k.t, vp)
                row += [f"{dist:,.0f}".replace(",", " "), ("✔ " if ok else "✘ ") + why]
            rows.append(tuple(row))
        hdr = ["n", "nom", "arme", "r orbite km", "struct.", "bouclier", "état", "recharge"]
        if ship is not None:
            hdr += ["dist. cible km", "visibilité de la cible"]
        print(fm.table(rows, hdr))
        print(f"Tireur actif : {k.use_idx}")

    def do_use(self, arg):
        self.k.use(int(arg))
        self.do_status("")

    def do_ammo(self, arg):
        k = self.k
        if arg.strip():
            k.set_ammo(arg.strip())
            self._summary()
            return
        lau = k.launcher_of()
        for key in lau.ammo:
            a = AMMO[key]
            mark = "→" if key == k.ammo else " "
            print(f" {mark} {key:<11} {a.name:<36} {a.cost_per_kg:>6.0f} cr/kg | bouclier x{a.shield_mult:g}, coque x{a.hull_mult:g}, pénétration x{a.pen_mult:g}")
            print(f"              {a.desc}")

    def _summary(self):
        k = self.k
        lau = k.launcher_of()
        if lau.kind == "beam":
            print(f"Impulsion {k.pulse_j:.3e} J | visée {k.lon:.6f}° / {k.lat:+.6f}°")
            return
        E = k.kinetic_energy()
        extra = ""
        if k.focus and isinstance(k.focus.op, StrikeOp):
            extra = f" ({100 * (E / k.focus.op.energy_j - 1):+.2f} % vs cible)"
        print(f"{AMMO[k.ammo].name} L={k.length:g} m r={k.radius:g} m ({fmt_mass(k.projectile.mass_kg)}) | "
              f"v = {fmt_speed(k.speed)} | visée {k.lon:.6f}° / {k.lat:+.6f}° | E = {E:.3e} J{extra}")

    @staticmethod
    def _speed(text: str) -> float:
        t = text.strip().lower().replace(",", ".")
        if t.endswith("c"):
            return float(t[:-1]) * C_KMS
        if t.endswith("%"):
            return float(t[:-1]) / 100.0 * C_KMS
        return float(t)

    def do_set(self, arg):
        parts = arg.split()
        if len(parts) != 2:
            raise ValueError("usage : set <longueur|rayon|masse|vitesse|lon|lat|impulsion> <valeur>")
        key, val = parts[0].lower(), parts[1]
        k = self.k
        if key in ("longueur", "length", "l"):
            k.length = float(val.replace(",", "."))
        elif key in ("rayon", "radius", "r"):
            k.radius = float(val.replace(",", "."))
        elif key in ("masse", "mass", "m"):
            k.set_mass(float(val.replace(",", ".")))
        elif key in ("vitesse", "speed", "v"):
            k.speed = self._speed(val)
            if k.speed >= C_KMS:
                k.speed = C_KMS * (1 - 1e-9)
                print(c("(limitée juste sous c)", DIM))
        elif key in ("lon", "longitude", "az", "azimut"):
            k.lon = float(val.replace(",", ".")) % 360.0
        elif key in ("lat", "latitude", "el", "elevation"):
            k.lat = float(val.replace(",", "."))
        elif key in ("impulsion", "pulse", "energie"):
            k.pulse_j = float(val.replace(",", "."))
        else:
            raise ValueError(f"paramètre inconnu : {key}")
        self._summary()

    def do_rod(self, arg):
        a = arg.replace(",", ".").split()
        if len(a) != 2:
            raise ValueError("usage : rod <longueur m> <rayon m>")
        self.k.length, self.k.radius = float(a[0]), float(a[1])
        self._summary()

    def do_aim(self, arg):
        a = arg.replace(",", ".").split()
        if len(a) != 2:
            raise ValueError("usage : aim <longitude °> <latitude °>")
        self.k.lon, self.k.lat = float(a[0]) % 360.0, float(a[1])
        self._summary()

    def do_match(self, arg):
        k = self.k
        if not (k.focus and isinstance(k.focus.op, StrikeOp)):
            raise ValueError("'match' sert aux frappes planétaires (énergie imposée)")
        E, what = k.focus.op.energy_j, arg.strip().lower()
        if what in ("vitesse", "speed"):
            k.speed = speed_for_energy(E, k.projectile.mass_kg)
        elif what in ("rayon", "radius"):
            k.set_mass(mass_for_energy(E, k.speed))
        elif what in ("masse", "mass"):
            k.set_mass(mass_for_energy(E, k.speed))
        else:
            raise ValueError("usage : match vitesse | rayon | masse")
        self._summary()

    # ------------------------------------------------------------------ vaisseaux
    def _battle(self):
        k = self.k
        if not (k.focus and isinstance(k.focus.op, DefenseOp)):
            raise GameError("aucune attaque en cours sur ce contrat ('board' puis 'focus <n>')")
        return k.focus.op.battle

    def do_ships(self, arg):
        k, b = self.k, self._battle()
        rows = []
        for s in b.ships:
            pos, vel = s.state(k.t)
            d = np.linalg.norm(pos)
            eta = "-"
            rows.append((s.id, s.name, s.spec.name, s.status, f"{100 * s.shield / s.shield_max:.0f}%",
                         f"{100 * s.hp_fraction:.0f}%", f"{d:,.0f}".replace(",", " "), f"{np.linalg.norm(vel):.1f}",
                         f"{s.firepower_j:.1e}", money(s.spec.value)))
        print(fm.table(rows, ("n", "nom", "classe", "état", "bouclier", "coque", "dist. Saturne km", "v km/s", "feu J", "prime")))
        print(f"Objectif ennemi : atteindre {b.objective_km:,.0f} km de Saturne | état : {b.state}".replace(",", " "))

    def _ship(self, n):
        b = self._battle()
        for s in b.ships:
            if s.id == n:
                return s
        raise GameError(f"vaisseau {n} inconnu")

    def do_ship(self, arg):
        k = self.k
        s = self._ship(int(arg or (k.target_sel[0] if k.target_sel else 1)))
        origin, _ = k.shooter.rel_state(k.t)
        lau = k.launcher_of()
        vp = C_KMS if lau.kind == "beam" else max(k.speed, 1.0)
        pos, vel = s.state(k.t)
        print(c(f"{s.name} — {s.spec.name} | {s.status} | bouclier {s.shield:.2e}/{s.shield_max:.2e} J ({'actif' if s.shield_online else 'HORS SERVICE'}) | équipage {100 * s.crew:.0f} %", BOLD))
        rows = []
        for i, comp in enumerate(s.comps):
            if comp.alive:
                try:
                    ok, why = eng.visibility(origin, s, i, k.t, vp)
                except Exception:
                    ok, why = False, "?"
            else:
                ok, why = False, "détruit"
            rows.append((i + 1, comp.name, comp.role, f"{comp.size[0]:.0f}x{comp.size[1]:.0f}x{comp.size[2]:.0f}",
                         f"{100 * max(comp.hp, 0) / comp.hp_max:.0f}%", f"{comp.armor_m:.2f} m", "CRITIQUE" if comp.critical else "",
                         ("✔ " if ok else "✘ ") + why))
        print(fm.table(rows, ("#", "composant", "rôle", "taille m", "intégrité", "blindage", "", f"vu du tireur {k.use_idx}")))
        print(shipview.render_ascii(s, pos - origin, k.t, selected=(k.target_sel[1] if k.target_sel and k.target_sel[0] == s.id else None)))
        print(c("(# = composant désigné ; chiffres = numéros ; x = détruit)", DIM))

    def do_target(self, arg):
        k, b = self.k, self._battle()
        a = arg.strip().lower()
        if not a:
            raise ValueError("usage : target <vaisseau>.<composant>   (ex : target 1.reactor, target 1.3)")
        sid, _, part = a.partition(".")
        if not part:
            sid, part = "1", sid
        ship = self._ship(int(sid))
        idx = None
        if part.isdigit():
            idx = int(part) - 1
        else:
            part = part.replace("é", "e").replace("é", "e")
            for i, comp in enumerate(ship.comps):
                if comp.key == part or comp.role == part or comp.name.lower().replace("é", "e").startswith(part):
                    idx = i
                    break
        if idx is None or not 0 <= idx < len(ship.comps):
            raise ValueError("composant inconnu (voir 'ship')")
        comp = ship.comps[idx]
        k.target_sel = (ship.id, idx)
        origin, _ = k.shooter.rel_state(k.t)
        lau = k.launcher_of()
        vp = C_KMS if lau.kind == "beam" else k.speed
        pos, vel = ship.state(k.t)
        A = ship.axes(vel)
        cen = pos + A @ (comp.center / 1000.0)
        d = float(np.linalg.norm(cen - origin))
        print(c(f"Cible : {ship.name} / {comp.name} (n° {idx + 1}) — boîte {comp.size[0]:.0f} x {comp.size[1]:.0f} x {comp.size[2]:.0f} m, blindage {comp.armor_m:.2f} m", BOLD))
        print(f"  Position (repère Saturne, km) : P = ({cen[0]:.3f}, {cen[1]:.3f}, {cen[2]:.3f})")
        print(f"  Vitesse du vaisseau (km/s)    : V = ({vel[0]:.4f}, {vel[1]:.4f}, {vel[2]:.4f})  |V| = {np.linalg.norm(vel):.3f}")
        print(f"  Tireur {k.shooter.id} ({k.shooter.name}) en S = ({origin[0]:.3f}, {origin[1]:.3f}, {origin[2]:.3f}) ; distance d = {d:,.1f} km".replace(",", " "))
        print(f"  Durée de vol : tau = d / vp = {d / vp:.6f} s ; décalage à anticiper : V·tau = {np.linalg.norm(vel) * d / vp * 1000:.1f} m")
        print("  Point à viser : P + V·tau   (puis lon = atan2(y, x), lat = asin(z / norm) du vecteur (point - S))")
        ok, why = eng.visibility(origin, ship, idx, k.t, vp)
        print(f"  Visibilité depuis ce tireur : {'✔' if ok else '✘'} {why}")

    def do_solve(self, arg):
        lon, lat, tau, dist, fee = self.k.solve_aim()
        print(c(f"Ordinateur de bord (-{money(fee)}) : longitude {lon:.7f}°, latitude {lat:+.7f}° | vol {tau:.4f} s | distance {dist:,.1f} km".replace(",", " "), GREEN))
        self._summary()

    def do_calc(self, arg):
        k = self.k
        env = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                                              "degrees", "radians", "pi", "log", "exp", "hypot")}
        env.update(norm=lambda v: float(np.linalg.norm(v)), dot=lambda a, b: float(np.dot(a, b)),
                   cross=lambda a, b: np.cross(a, b).tolist(), vec=lambda *a: np.array(a, float),
                   asin_deg=lambda x: math.degrees(math.asin(x)), c=C_KMS, vp=k.speed)
        if k.target_sel and k.focus and isinstance(k.focus.op, DefenseOp):
            ship = self._ship(k.target_sel[0])
            origin, _ = k.shooter.rel_state(k.t)
            pos, vel = ship.state(k.t)
            cen = pos + ship.axes(vel) @ (ship.comps[k.target_sel[1]].center / 1000.0)
            vp = C_KMS if k.launcher_of().kind == "beam" else k.speed
            env.update(P=cen, V=vel, S=origin, d=float(np.linalg.norm(cen - origin)), vp=vp,
                       tau=float(np.linalg.norm(cen - origin) / vp))
        env = {k_: (np.array(v) if isinstance(v, list) else v) for k_, v in env.items()}
        res = eval(arg, {"__builtins__": {}}, env)       # noqa: S307  (jeu local, environnement restreint)
        print(np.array2string(np.asarray(res), precision=10) if hasattr(res, "__len__") else f"{res:.12g}")

    def do_view(self, arg):
        k = self.k
        b = self._battle()
        s = self._ship(int(arg or (k.target_sel[0] if k.target_sel else 1)))
        origin, _ = k.shooter.rel_state(k.t)
        pos, _ = s.state(k.t)
        from . import plots
        fig = shipview.plot_ship(s, pos - origin, k.t, selected=k.target_sel[1] if k.target_sel else None)
        path = plots.show_or_save(fig, f"vaisseau_{s.id}", self.save_dir, self.save_only)
        if path:
            print(f"Image enregistrée : {path}")

    # ------------------------------------------------------------------ temps et tir
    def do_wait(self, arg):
        dt = parse_duration(arg)
        done = self.k.advance(dt, interruptible=True)
        print(f"Nous sommes le {format_date(self.k.t)} (+{fmt_duration(done)}).")
        self.k.plan = None

    def do_goto(self, arg):
        t = parse_date(arg)
        if t < self.k.t:
            raise ValueError("on ne remonte pas le temps")
        self.k.advance(t - self.k.t, interruptible=True)
        print(f"Nous sommes le {format_date(self.k.t)}.")
        self.k.plan = None

    def do_fire(self, arg):
        k = self.k
        print(c("Mise à feu...", DIM))
        rep = k.fire()
        if rep["kind"] == "ship":
            for line in rep["lines"]:
                print(line)
            b = self._battle() if k.focus and isinstance(k.focus.op, DefenseOp) else None
            if b:
                for s in b.ships:
                    print(f"  {s.name}: {s.status}, bouclier {100 * s.shield / s.shield_max:.0f} %, coque {100 * s.hp_fraction:.0f} %")
        else:
            self._planetary_report(rep)
        print(c(f"Coût du tir : {money(rep['cost'])} | crédits : {money(k.credits)}", DIM))

    def _planetary_report(self, rep):
        k = self.k
        res = rep["result"]
        print(c("=== RÉSULTAT DU TIR ===", BOLD))
        op = k.focus.op
        if isinstance(op, StrikeOp):
            if res.outcome == "impact":
                print(f"IMPACT sur {res.body} le {format_date(res.t_end)} (après {fmt_duration(res.t_end - res.t_start)})")
                print(f"  Point d'impact : lat {res.impact_lat:+.3f}°, lon {res.impact_lon:+.3f}° | vitesse relative {fmt_speed(res.impact_speed)}")
                e_imp = k.projectile.energy_j(min(res.impact_speed, C_KMS * (1 - 1e-9)))
                print(f"  Énergie à l'impact : {e_imp:.3e} J ({e_imp / MT_TNT_J:.4g} Mt)")
                if rep.get("hit"):
                    print(f"  Écart à la cible : {rep['miss_km']:,.1f} km (tolérance {op.tolerance_km:g} km)".replace(",", " "))
                else:
                    print(c(f"  Mauvais corps : la cible était {op.target.body}.", YELLOW))
            else:
                print(c({"timeout": "Le projectile erre toujours (durée max).", "lost": "Le projectile a quitté le système solaire."}.get(res.outcome, res.outcome), YELLOW))
            if not rep.get("hit") and op.target.body in res.closest:
                d, t = res.closest[op.target.body]
                print(f"  Plus proche approche : {d:,.0f} km du centre le {format_date(t)}".replace(",", " "))
            ok = lambda b: c("OK", GREEN) if b else c("ÉCHEC", RED)
            print(f"  Contrôles : précision {ok(rep.get('hit') and rep['miss_km'] <= op.tolerance_km)} | énergie {ok(rep['energy_ok'])}"
                  + (f" | pénétration {rep['pen_m']:.1f} m {ok(rep['pen_ok'])}" if op.min_penetration_m else "")
                  + (f" | délai {ok(rep['flight_ok'])}" if op.max_flight_days else ""))
            if not rep.get("success"):
                print(c("Cible manquée ou conditions non remplies.", RED))
        else:
            for line in rep["lines"]:
                print(line)
        if self.plots and rep.get("result") is not None:
            from . import plots
            body = op.target.body if isinstance(op, StrikeOp) else (op.target.planet if isinstance(op, FleetOp) else None)
            try:
                path = plots.show_or_save(plots.plot_shot(k.system, rep["result"], body, k.focus.title), "dernier_tir", self.save_dir, save_only=True)
                print(c(f"Graphe : {path} ('plot' pour l'afficher)", DIM))
            except Exception as e:  # pragma: no cover
                print(c(f"(graphe indisponible : {e})", DIM))
        self._last_plot = (rep["result"], k.focus.title)

    def do_plot(self, arg):
        from . import plots
        k = self.k
        if arg.strip().startswith("sys"):
            fig, name = plots.plot_system(k.system, k.t), "systeme"
        else:
            if not (k.last_report and k.last_report.get("result") is not None):
                raise ValueError("aucun tir interplanétaire à tracer ; essayez 'plot system'")
            op = k.focus.op if k.focus else None
            body = op.target.body if isinstance(op, StrikeOp) else (op.target.planet if isinstance(op, FleetOp) else None)
            fig, name = plots.plot_shot(k.system, k.last_report["result"], body, k.focus.title if k.focus else "Tir"), "dernier_tir"
        path = plots.show_or_save(fig, name, self.save_dir, self.save_only)
        if path:
            print(f"Image enregistrée : {path}")

    def do_system(self, arg):
        k = self.k
        if arg.strip() == "plot":
            return self.do_plot("system")
        print(fm.planets_table(k.system, k.t))
        print()
        print(fm.ascii_map(k.system, k.t, extent_au=1.8 if arg.strip() == "inner" else None))

    # ------------------------------------------------------------------ guidage
    def do_window(self, arg):
        k = self.k
        toks = arg.replace(",", ".").split()
        auto = "auto" in toks
        days = next((float(t) for t in toks if t != "auto"), None)
        print(c(f"Calcul des fenêtres ({'vitesse optimale' if auto else 'pour votre vitesse ' + fmt_speed(k.speed)})...", DIM))
        wins, fee = k.find_windows(auto=auto, max_days=days, progress=lambda s: print(c(s, DIM)))
        print(c(f"Frais de calcul : {money(fee)}", DIM))
        if not wins:
            print(c(k.guidance.last_note or "Aucune fenêtre trouvée à partir de cette date ('wait 1y' ?).", YELLOW))
            return
        rows = []
        for i, p in enumerate(wins, 1):
            lon, lat = p.lon_lat
            rows.append((i, format_date(p.t_launch), format_date(p.t_arrival), fmt_duration(p.flight_s),
                         fmt_speed(round(p.speed, 3)), f"{lon:.3f}/{lat:+.3f}", f"{p.visibility:.2f}",
                         (f"{p.rod.length_m:g}x{p.rod.radius_m:g}" if p.rod else "(la vôtre)")))
        print(fm.table(rows, ("n", "départ", "arrivée", "vol", "v bouche", "lon/lat tir", "visib.", "barre L x r")))
        print(c("Solutions approchées : 'plan <n>' puis 'refine'.", DIM))

    def do_plan(self, arg):
        k = self.k
        n = int(arg) - 1
        if not 0 <= n < len(k.windows):
            raise ValueError("lancez d'abord 'window' et choisissez un numéro valide")
        k.apply_plan(k.windows[n])
        print(c(f"Plan {n + 1} chargé. Tir le {format_date(k.t)}, impact prévu {format_date(k.plan.t_arrival)}.", GREEN))
        self.do_status("")

    def do_refine(self, arg):
        k = self.k
        if arg.strip():
            plan = Plan(k.t, parse_date(arg), k.speed * direction_vector(k.lon, k.lat), 0.0, 0.0, 1.0)
        elif k.plan is not None:
            plan = Plan(k.t, k.plan.t_arrival, k.speed * direction_vector(k.lon, k.lat), 0.0, 0.0, 1.0)
        else:
            raise ValueError("pas de plan actif : 'plan <n>' ou 'refine <date d'arrivée>'")
        print(c("Tirs d'essai (Newton) : direction et heure de tir ajustées, votre vitesse est conservée...", DIM))
        new = k.refine(plan, progress=lambda s: print(c(s, DIM)))
        if new.residual_km is None or new.residual_km > 25:
            print(c(f"Correction non convergée (écart {new.residual_km:,.0f} km) : essayez une autre fenêtre.".replace(",", " "), RED))
            return
        k.apply_plan(new)
        print(c(f"Correction terminée : écart résiduel {new.residual_km:.3f} km. Tir le {format_date(k.t)}.", GREEN))
        self._summary()

    # ------------------------------------------------------------------ économie
    def do_upgrades(self, arg):
        k = self.k
        rows = []
        for key, u in UPGRADES.items():
            lvl = int(k.upgrades.get(key, 0))
            rows.append((key, u.name, f"{lvl}/{u.max_level}", money(upgrade_cost(key, lvl)) if lvl < u.max_level else "MAX", u.desc))
        print(fm.table(rows, ("clé", "amélioration", "niveau", "prochain prix", "effet")))
        rows = [(key, l.name, "✔" if key in k.unlocked else money(l.unlock_cost), l.desc) for key, l in LAUNCHERS.items() if key != "canon"]
        print()
        print(fm.table(rows, ("lanceur", "nom", "débloqué / prix", "description")))
        print(f"Énergie max du canon interplanétaire : {energy_cap_j(k.upgrades):.1e} J")

    def do_buy(self, arg):
        self.k.buy(arg.strip())

    def do_repair(self, arg):
        a = arg.strip() or "all"
        self.k.repair(a if a == "all" else int(a))

    def do_refit(self, arg):
        n, lau = arg.split()
        self.k.refit(int(n), lau)

    # ------------------------------------------------------------------ sauvegarde
    def _path(self, name):
        return os.path.join(self.saves_dir, (name.strip() or "partie") + ".pkl")

    def do_save(self, arg):
        self.k.save(self._path(arg))
        print(f"Partie sauvegardée : {self._path(arg)}")
        os.makedirs(self.saves_dir, exist_ok=True)
        sp = os.path.join(self.saves_dir, "scores.json")
        scores = json.load(open(sp)) if os.path.exists(sp) else []
        scores.append({"date": format_date(self.k.t), "rang": self.k.rank, "gains": round(self.k.earned),
                       "credits": round(self.k.credits)})
        json.dump(sorted(scores, key=lambda s: -s["gains"])[:10], open(sp, "w"), indent=1)

    def do_load(self, arg):
        self.k = Career.load(self._path(arg))
        print(f"Partie chargée ({format_date(self.k.t)}).")

    def do_quit(self, arg):
        print("À bientôt, commandant !")
        return True

    do_exit = do_quit
    do_EOF = do_quit
