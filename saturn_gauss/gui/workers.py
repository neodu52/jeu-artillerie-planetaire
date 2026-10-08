"""Exécution des calculs longs (fenêtres, correction, tirs interplanétaires) hors du thread de l'interface."""
from PySide6.QtCore import QObject, QRunnable, Signal


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(str)


class Worker(QRunnable):
    """fn(progress_callback) -> résultat. Les signaux sont émis dans le thread principal."""

    def __init__(self, fn):
        super().__init__()
        self.setAutoDelete(False)          # on garde la main sur la durée de vie (les signaux en dépendent)
        self.fn = fn
        self.signals = _Signals()

    def run(self):
        try:
            res = self.fn(self.signals.progress.emit)
        except Exception as e:  # noqa: BLE001
            self.signals.failed.emit(f"{type(e).__name__}: {e}")
        else:
            self.signals.done.emit(res)
