"""Interface graphique Qt (PySide6).

IMPORTANT : ces imports doivent rester AVANT tout import de PySide6.
Sous Windows, PySide6 installe un crochet d'import qui plante (« _SixMetaPathImporter object has no
attribute '_path' ») si `six` / `dateutil` sont chargés après lui, ce que fait matplotlib.dates
quand on importe son backend Qt. On les charge donc ici, en premier.
"""
import dateutil.parser  # noqa: F401
import dateutil.rrule  # noqa: F401
import matplotlib  # noqa: F401
import matplotlib.dates  # noqa: F401
import matplotlib.figure  # noqa: F401
import six.moves  # noqa: F401
