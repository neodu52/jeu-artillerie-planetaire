"""Interface terminal (REPL) du jeu."""
import cmd

import numpy as np

from ..ballistics.cannon import E_MAX_J, V_MAX_KMS, direction_vector
from ..ballistics.projectile import LENGTH_RANGE_M, RADIUS_RANGE_M, radius_for_mass
from ..constants import AU_KM, DAY_S
from ..game.missions import CAMPAIGN
from ..guidance import Plan
from ..timeutils import format_date, parse_date, parse_duration
from . import formatting as fm
from .formatting import BOLD, CYAN, DIM, GREEN, RED, YELLOW, c

HELP = """
{b}COMMANDES{r}
  {b}Mission{r}
    mission [n]          briefing de la mission courante (ou choisir la mission n)
    missions             liste de la campagne        next : mission suivante
  {b}Réglages du tir{r}
    status               état complet (canon, barre, visée, énergie)
    set <param> <val>    longueur (m) | rayon (m) | vitesse (km/s) | lon (°) | lat (°)
    rod <L> <R>          raccourci : longueur et rayon de la barre
    aim <lon> <lat>      raccourci : direction de tir (longitude / latitude écliptiques)
    match vitesse|rayon  ajuste la vitesse ou le rayon pour atteindre l'énergie demandée
  {b}Temps{r}
    wait <durée>         avance le temps : 3d, 12h, 45m, 2y     goto <AAAA-MM-JJ [HH:MM]>
  {b}Tir et analyse{r}
    fire                 tire ! (simulation complète du vol)
    plot [system]        graphe du dernier tir (ou du système solaire)
    system [inner|plot]  planètes : tableau + carte ASCII
  {b}Ordinateur de visée (optionnel, pénalise le score){r}
    window [jours max]   cherche des fenêtres de tir          (-100 pts)
    plan <n>             charge la fenêtre n (date + réglages approchés)
    refine [arrivée]     corrige le tir par tirs d'essai       (-150 pts)
  quit                   quitter
{b}REPÈRE{r} : la direction de tir est donnée dans le repère écliptique héliocentrique
(longitude 0° = direction de l'équinoxe, latitude +90° = pôle nord écliptique).
"""


class GameShell(cmd.Cmd):
    prompt = "> "

    def __init__(self, game, plots=True, save_only=False, save_dir="plots"):
        super().__init__()
        self.game = game
        self.plots = plots
        self.save_only = save_only
        self.save_dir = save_dir
        self.plan = None
        self._refresh_prompt()

    # ------------------------------------------------------------------ infrastructure
    def _refresh_prompt(self):
        self.prompt = c(f"[{format_date(self.game.t)} | M{self.game.mission_index + 1}] > ", CYAN)

    def postcmd(self, stop, line):
        self._refresh_prompt()
        return stop

    def emptyline(self):
        pass

    def default(self, line):
        print(c(f"Commande inconnue : {line.split()[0]!r}. Tapez 'help'.", YELLOW))

    def onecmd(self, line):
        try:
            return super().onecmd(line)
        except (ValueError, KeyError) as e:
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
        print(HELP.format(b=BOLD if fm._USE_COLOR else "", r="\033[0m" if fm._USE_COLOR else ""))

    # ------------------------------------------------------------------ missions
    def do_mission(self, arg):
        if arg.strip():
            self.game.select_mission(int(arg) - 1)
            self.plan = None
        print(fm.briefing(self.game.mission, self.game))

    def do_missions(self, arg):
        g = self.game
        for i, m in enumerate(CAMPAIGN):
            mark = c("✔", GREEN) if i in g.completed else " "
            cur = "→" if i == g.mission_index else " "
            print(f" {cur} {mark} {i + 1}. {m.title} ({m.target})")
        print(f"Score total : {g.total_score}")

    def do_next(self, arg):
        g = self.game
        if g.mission_index not in g.completed:
            print(c("Mission courante non réussie ; 'mission <n>' permet de changer quand même.", YELLOW))
            return
        if g.mission_index + 1 >= len(CAMPAIGN):
            print(c(f"Campagne terminée ! Score final : {g.total_score}", BOLD, GREEN))
            return
        self.do_mission(str(g.mission_index + 2))

    # ------------------------------------------------------------------ réglages
    def do_status(self, arg):
        g, m = self.game, self.game.mission
        cs = g.cannon.state(g.t)
        saturn = g.system.position("Saturne", g.t)
        E = g.energy_j()
        lines = [
            c("=== ÉTAT DU CANON ===", BOLD),
            f"Date            : {format_date(g.t)}",
            f"Saturne         : {np.linalg.norm(saturn) / AU_KM:.3f} UA du Soleil",
            f"Orbite du canon : r = {g.cannon.radius_km:,.0f} km, v = {g.cannon.speed_kms:.2f} km/s, "
            f"période {g.cannon.period_s / 3600:.2f} h".replace(",", " "),
            f"Barre           : L = {g.rod.length_m:g} m, r = {g.rod.radius_m:g} m, masse {fm.fmt_mass(g.rod.mass_kg)}",
            f"Vitesse bouche  : {g.speed:g} km/s (max {V_MAX_KMS:g})",
            f"Visée           : longitude {g.lon:.4f}°, latitude {g.lat:+.4f}°",
            f"Énergie         : {fm.fmt_energy(E)} (cible {m.energy_j:.3e} J, écart {100 * (E / m.energy_j - 1):+.2f} %)"
            + ("" if E <= E_MAX_J else c("  > capacité max !", RED)),
        ]
        if m.min_penetration_m:
            pen = g.rod.penetration_m(g.system.get(m.target).surface_density)
            lines.append(f"Pénétration     : {pen:.1f} m (min {m.min_penetration_m:g} m)")
        print("\n".join(lines))

    def _summary(self):
        g, m = self.game, self.game.mission
        E = g.energy_j()
        print(f"Barre {g.rod.length_m:g} m x r={g.rod.radius_m:g} m ({fm.fmt_mass(g.rod.mass_kg)}) | "
              f"v = {g.speed:g} km/s | visée {g.lon:.4f}° / {g.lat:+.4f}° | "
              f"E = {E:.3e} J ({100 * (E / m.energy_j - 1):+.2f} % vs cible)")

    def do_set(self, arg):
        parts = arg.replace(",", ".").split()
        if len(parts) != 2:
            raise ValueError("usage : set <longueur|rayon|vitesse|lon|lat> <valeur>")
        key, val = parts[0].lower(), float(parts[1])
        g = self.game
        if key in ("longueur", "length", "l"):
            g.rod.length_m = val
        elif key in ("rayon", "radius", "r"):
            g.rod.radius_m = val
        elif key in ("vitesse", "speed", "v"):
            g.speed = val
        elif key in ("lon", "longitude", "az", "azimut"):
            g.lon = val % 360.0
        elif key in ("lat", "latitude", "el", "elevation"):
            g.lat = val
        else:
            raise ValueError(f"paramètre inconnu : {key}")
        self._summary()

    def do_rod(self, arg):
        a = arg.replace(",", ".").split()
        if len(a) != 2:
            raise ValueError("usage : rod <longueur m> <rayon m>")
        self.game.rod.length_m, self.game.rod.radius_m = float(a[0]), float(a[1])
        self._summary()

    def do_aim(self, arg):
        a = arg.replace(",", ".").split()
        if len(a) != 2:
            raise ValueError("usage : aim <longitude °> <latitude °>")
        self.game.lon, self.game.lat = float(a[0]) % 360.0, float(a[1])
        self._summary()

    def do_match(self, arg):
        g, E = self.game, self.game.mission.energy_j
        what = arg.strip().lower()
        if what in ("vitesse", "speed"):
            g.speed = float(np.sqrt(2 * E / g.rod.mass_kg) / 1e3)
        elif what in ("rayon", "radius"):
            g.rod.radius_m = radius_for_mass(2 * E / (g.speed * 1e3) ** 2, g.rod.length_m)
        else:
            raise ValueError("usage : match vitesse | match rayon")
        self._summary()

    # ------------------------------------------------------------------ temps
    def do_wait(self, arg):
        self.game.t += parse_duration(arg)
        print(f"Nous sommes le {format_date(self.game.t)}.")
        self.plan = None

    def do_goto(self, arg):
        self.game.t = parse_date(arg)
        print(f"Nous sommes le {format_date(self.game.t)}.")
        self.plan = None

    # ------------------------------------------------------------------ tir
    def do_fire(self, arg):
        g = self.game
        print(c("Mise à feu... simulation du vol en cours.", DIM))
        rep = g.fire()
        print(fm.shot_report(rep, g.system))
        if self.plots:
            from . import plots
            path = plots.show_or_save(plots.plot_shot(g.system, rep), "dernier_tir", self.save_dir, save_only=True)
            print(c(f"Graphe enregistré : {path}  (commande 'plot' pour l'afficher)", DIM))

    def do_plot(self, arg):
        from . import plots
        g = self.game
        if arg.strip().startswith("sys"):
            fig, name = plots.plot_system(g.system, g.t), "systeme"
        elif g.last is None:
            raise ValueError("aucun tir à tracer ; utilisez 'fire' ou 'plot system'")
        else:
            fig, name = plots.plot_shot(g.system, g.last), "dernier_tir"
        path = plots.show_or_save(fig, name, self.save_dir, self.save_only)
        if path:
            print(f"Pas d'écran graphique détecté : image enregistrée dans {path}")

    def do_system(self, arg):
        g = self.game
        a = arg.strip()
        if a == "plot":
            return self.do_plot("system")
        print(fm.planets_table(g.system, g.t))
        print()
        print(fm.ascii_map(g.system, g.t, extent_au=1.8 if a == "inner" else None))

    # ------------------------------------------------------------------ assistance
    def _need_assist(self):
        if not self.game.assist_enabled:
            raise ValueError("l'ordinateur de visée est désactivé (--no-assist)")

    def do_window(self, arg):
        self._need_assist()
        g = self.game
        max_days = float(arg.replace(",", ".")) if arg.strip() else None
        print(c("Calcul des fenêtres de tir (conique raccordée, Lambert)...", DIM))
        wins = g.find_windows(progress=lambda s: print(c(s, DIM)), max_flight_days=max_days)
        if not wins:
            print(c("Aucune fenêtre trouvée à partir de cette date. Essayez 'wait 1y'.", YELLOW))
            return
        rows = []
        for i, p in enumerate(wins, 1):
            lon, lat = p.lon_lat
            rows.append((i, format_date(p.t_launch), format_date(p.t_arrival), f"{p.flight_days:.0f}",
                         f"{p.speed:.2f}", f"{lon:.1f}/{lat:+.1f}", f"{p.arrival_speed:.1f}",
                         f"{p.rod.length_m:g}x{p.rod.radius_m:g}" if p.rod else "-"))
        print(fm.table(rows, ("n", "départ", "arrivée", "vol (j)", "v0 km/s", "lon/lat tir", "v arrivée", "barre L x r")))
        print(c("Ces solutions sont approchées : chargez-en une avec 'plan <n>' puis 'refine'.", DIM))

    def do_plan(self, arg):
        self._need_assist()
        g = self.game
        n = int(arg) - 1
        if not 0 <= n < len(g.windows):
            raise ValueError("lancez d'abord 'window' et choisissez un numéro valide")
        self.plan = g.windows[n]
        g.apply_plan(self.plan)
        print(c(f"Plan {n + 1} chargé. Date du tir : {format_date(g.t)} ; impact prévu : {format_date(self.plan.t_arrival)}.", GREEN))
        self.do_status("")
        print(c("Astuce : 'fire' tout de suite montrera l'erreur de la conique raccordée ; 'refine' la supprime.", DIM))

    def do_refine(self, arg):
        self._need_assist()
        g = self.game
        if arg.strip():
            t_arr = parse_date(arg)
            vec = g.speed * direction_vector(g.lon, g.lat)
            plan = Plan(g.t, t_arr, vec, 0.0, 0.0, 1.0)
        elif self.plan is not None and abs(self.plan.t_launch - g.t) < 1.0:
            plan = self.plan
        else:
            raise ValueError("pas de plan actif : utilisez 'plan <n>' ou 'refine <date d'arrivée>'")
        print(c("Tirs d'essai (Newton) pour viser le point exact à la date d'arrivée...", DIM))
        new = g.refine(plan, progress=lambda s: print(c(s, DIM)))
        self.plan = new
        g.apply_plan(new, keep_rod_length=True)
        print(c(f"Correction terminée : écart résiduel {new.residual_km:.2f} km.", GREEN))
        self.do_status("")

    # ------------------------------------------------------------------ sortie
    def do_quit(self, arg):
        print("À bientôt, artilleur !")
        return True

    do_exit = do_quit
    do_EOF = do_quit
