"""Point d'entrée : python main.py [options]"""
import argparse

from .game.state import Game
from .ui import formatting as fm
from .ui.terminal import GameShell

BANNER = r"""
   ___  _   _____ _   _ ___ _  _ ___    ___   _   _   _ ___ ___
  / __|/_\ |_   _| | | | _ \ \| | __|  / __| /_\ | | | / __/ __|
  \__ \ _ \  | | | |_| |   / .` | _|  | (_ || _ \| |_| \__ \__ \
  |___/_/ \_\ |_|  \___/|_|_\_|\_|___|  \___/_/ \_\\___/|___/___/
   Canon de Gauss orbital - Artilleur du futur - An 2150
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Canon de Gauss en orbite de Saturne")
    ap.add_argument("--no-assist", action="store_true", help="désactive l'ordinateur de visée (mode expert)")
    ap.add_argument("--no-plot", action="store_true", help="pas de graphe automatique après chaque tir")
    ap.add_argument("--save-plots", action="store_true", help="enregistre les graphes en PNG au lieu d'ouvrir une fenêtre")
    ap.add_argument("--no-color", action="store_true", help="désactive les couleurs ANSI")
    ap.add_argument("--mission", type=int, default=1, help="numéro de mission de départ")
    args = ap.parse_args(argv)

    fm.set_color(not args.no_color)
    game = Game(assist_enabled=not args.no_assist)
    game.select_mission(args.mission - 1)
    shell = GameShell(game, plots=not args.no_plot, save_only=args.save_plots)
    print(BANNER)
    print("Tapez 'help' pour la liste des commandes.\n")
    shell.do_mission("")
    shell.cmdloop()


if __name__ == "__main__":
    main()
