"""Interface graphique : python gui.py [--seed N] [--no-assist] [--load fichier.pkl]"""
import sys

# Précharger matplotlib/dateutil/six AVANT PySide6 (conflit connu sous Windows) ; fait aussi par saturn_gauss.gui.
import matplotlib.dates  # noqa: F401  isort:skip
import dateutil.rrule  # noqa: F401  isort:skip

from saturn_gauss.gui.app import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run())
