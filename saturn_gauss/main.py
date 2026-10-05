"""Point d'entrée : python main.py [options]"""
import argparse

from .career import Career
from .ui import formatting as fm
from .ui.terminal import GameShell

BANNER = r"""
   ___  _   _____ _   _ ___ _  _ ___    ___   _   _   _ ___ ___
  / __|/_\ |_   _| | | | _ \ \| | __|  / __| /_\ | | | / __/ __|
  \__ \ _ \  | | | |_| |   / .` | _|  | (_ || _ \| |_| \__ \__ \
  |___/_/ \_\ |_|  \___/|_|_\_|\_|___|  \___/_/ \_\\___/|___/___/
   Commandement orbital de Saturne - An 2150
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="Canon de Gauss en orbite de Saturne")
    ap.add_argument("--no-assist", action="store_true", help="désactive l'ordinateur de visée interplanétaire (expert)")
    ap.add_argument("--no-plot", action="store_true", help="pas de graphe automatique après un tir interplanétaire")
    ap.add_argument("--save-plots", action="store_true", help="graphes en PNG au lieu de fenêtres")
    ap.add_argument("--no-color", action="store_true", help="désactive les couleurs ANSI")
    ap.add_argument("--seed", type=int, default=0, help="graine du hasard (événements)")
    ap.add_argument("--load", metavar="NOM", help="charge une sauvegarde du dossier saves/")
    args = ap.parse_args(argv)

    fm.set_color(not args.no_color)
    career = Career.load(f"saves/{args.load}.pkl") if args.load else Career(seed=args.seed, assist=not args.no_assist)
    shell = GameShell(career, plots=not args.no_plot, save_only=args.save_plots)
    print(BANNER)
    print("Tapez 'help' pour les commandes, 'board' pour les contrats.\n")
    shell.do_board("")
    shell.cmdloop()


if __name__ == "__main__":
    main()
