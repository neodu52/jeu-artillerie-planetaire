"""Onglet Console : journal des événements + ligne de commande (mêmes commandes que le mode terminal)."""
import io
from contextlib import redirect_stdout

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ...ui import formatting as fm
from ...ui.terminal import GameShell
from ..common import title


class ConsoleTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.addWidget(title("Journal et console"))
        self.out = QPlainTextEdit()
        self.out.setReadOnly(True)
        self.out.setMaximumBlockCount(5000)
        lay.addWidget(self.out, 1)
        row = QHBoxLayout()
        row.addWidget(QLabel("Commande :"))
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("ex : board, ships, target 1.reactor, solve, fire, help …")
        self.inp.returnPressed.connect(self.run)
        row.addWidget(self.inp, 1)
        b = QPushButton("Exécuter")
        b.clicked.connect(self.run)
        row.addWidget(b)
        lay.addLayout(row)
        self.shell = None

    def log(self, text):
        self.out.appendPlainText(text)

    def run(self):
        line = self.inp.text().strip()
        if not line:
            return
        self.inp.clear()
        fm.set_color(False)
        if self.shell is None or self.shell.k is not self.win.k:
            self.shell = GameShell(self.win.k, plots=False, save_only=True)
        self.log(f"> {line}")
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.shell.onecmd(line)
            self.shell._flush()
        self.log(buf.getvalue().rstrip())
        if self.shell.k is not self.win.k:
            self.win.set_career(self.shell.k)
        self.win.after_action(flush=False)

    def refresh(self):
        pass
