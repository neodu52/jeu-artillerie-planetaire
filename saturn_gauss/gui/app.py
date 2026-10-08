"""Lancement de l'interface graphique."""
import argparse
import sys

from PySide6.QtWidgets import QApplication

from ..career import Career
from .main_window import MainWindow
from .theme import QSS


def make_app(argv=None):
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setStyleSheet(QSS)
    return app


def run(argv=None):
    ap = argparse.ArgumentParser(description="Saturn Gauss — interface graphique")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--no-assist", action="store_true")
    ap.add_argument("--load", metavar="FICHIER", help="charge une sauvegarde (.pkl)")
    args, rest = ap.parse_known_args(argv)
    app = make_app([sys.argv[0]] + rest)
    k = Career.load(args.load) if args.load else Career(seed=args.seed, assist=not args.no_assist)
    win = MainWindow(k)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
