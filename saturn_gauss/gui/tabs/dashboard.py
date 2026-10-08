"""Onglet Tableau de bord : contrats, événements prioritaires, situation générale."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
                               QSplitter, QVBoxLayout, QWidget)

from ...briefing import brief_text
from ...ui.formatting import fmt_duration, money
from .. import theme
from ..common import bar, cell, new_table, select_row_by_id, title, value_label

KIND = {"strike": "Frappe planétaire", "fleet": "Élimination", "protect": "Protection", "asteroid": "Astéroïde",
        "defense": "DÉFENSE"}
STATE = {"offered": "proposé", "active": "actif", "done": "réussi", "failed": "échec", "refused": "refusé",
         "expired": "expiré"}


class DashboardTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        left = QWidget()
        ll = QVBoxLayout(left)
        ll.addWidget(title("Contrats et événements"))
        self.table = new_table(["#", "Type", "État", "Titre", "Récompense", "Échéance"], stretch=3)
        self.table.itemSelectionChanged.connect(self._selected)
        self.table.itemDoubleClicked.connect(lambda *_: self.work_on())
        ll.addWidget(self.table, 1)
        self.show_old = QCheckBox("Afficher les contrats terminés / expirés")
        self.show_old.toggled.connect(self.refresh)
        ll.addWidget(self.show_old)
        row = QHBoxLayout()
        self.b_accept = QPushButton("✔ Accepter")
        self.b_accept.setObjectName("good")
        self.b_refuse = QPushButton("✘ Refuser")
        self.b_work = QPushButton("▶ Travailler dessus")
        self.b_work.setObjectName("accent")
        self.b_accept.clicked.connect(self.accept)
        self.b_refuse.clicked.connect(self.refuse)
        self.b_work.clicked.connect(self.work_on)
        for b in (self.b_accept, self.b_refuse, self.b_work):
            row.addWidget(b)
        ll.addLayout(row)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        box = QGroupBox("Situation")
        g = QGridLayout(box)
        self.l_credits, self.l_rank, self.l_earned, self.l_date = (value_label() for _ in range(4))
        for i, (t, w) in enumerate((("Date", self.l_date), ("Crédits", self.l_credits), ("Rang", self.l_rank),
                                    ("Gains cumulés", self.l_earned))):
            g.addWidget(QLabel(t), i, 0)
            g.addWidget(w, i, 1)
        rl.addWidget(box)
        box2 = QGroupBox("Stations")
        self.st_grid = QGridLayout(box2)
        rl.addWidget(box2)
        box3 = QGroupBox("Briefing")
        b3 = QVBoxLayout(box3)
        self.brief = QPlainTextEdit()
        self.brief.setReadOnly(True)
        b3.addWidget(self.brief)
        rl.addWidget(box3, 1)
        split.addWidget(right)
        split.setSizes([620, 520])
        self._rows = []

    def _contract(self):
        r = self.table.currentRow()
        if r < 0 or r >= len(self._rows):
            return None
        return self._rows[r]

    def _selected(self):
        ct = self._contract()
        self.brief.setPlainText(brief_text(self.win.k, ct) if ct else "")
        self._buttons(ct)

    def _buttons(self, ct):
        self.b_accept.setEnabled(bool(ct and ct.state == "offered"))
        self.b_refuse.setEnabled(bool(ct and ct.state == "offered" and not ct.priority))
        self.b_work.setEnabled(bool(ct and ct.state in ("active", "offered")))

    def accept(self):
        ct = self._contract()
        if ct and self.win.guard(self.win.k.accept, ct.id)[0]:
            self.win.after_action()
            self.win.goto_for(ct)

    def refuse(self):
        ct = self._contract()
        if ct:
            self.win.guard(self.win.k.refuse, ct.id)
            self.win.after_action()

    def work_on(self):
        ct = self._contract()
        if ct and self.win.guard(self.win.k.set_focus, ct.id)[0]:
            self.win.after_action()
            self.win.goto_for(ct)

    def refresh(self):
        k = self.win.k
        keep = self._contract().id if self._contract() else None
        self._rows = [c for c in k.board if self.show_old.isChecked() or c.state in ("offered", "active")]
        self._rows.sort(key=lambda c: (not c.priority, c.state != "active", c.id))
        self.table.setRowCount(len(self._rows))
        for r, c in enumerate(self._rows):
            dl = "-" if c.deadline is None else (fmt_duration(c.deadline - k.t) if c.deadline > k.t else "échu")
            col = theme.BAD if c.priority and c.state == "active" else (theme.GOOD if c.state == "done" else
                  theme.DIM if c.state in ("refused", "expired", "failed") else theme.TEXT)
            foc = "▶ " if k.focus is c else ""
            vals = [c.id, ("⚠ " if c.priority else "") + KIND[c.kind], foc + STATE[c.state], c.title, money(c.reward), dl]
            for j, v in enumerate(vals):
                self.table.setItem(r, j, cell(v, col, "r" if j in (0, 4, 5) else None, bold=c.priority and c.state == "active"))
        if keep is not None:
            select_row_by_id(self.table, keep)
        elif self._rows:
            self.table.selectRow(0)
        self.l_date.setText(self.win.date_text())
        self.l_credits.setText(money(k.credits))
        self.l_rank.setText(str(k.rank))
        self.l_earned.setText(money(k.earned))
        while self.st_grid.count():
            w = self.st_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        for i, s in enumerate(k.shooters):
            self.st_grid.addWidget(QLabel(f"{s.name}"), i, 0)
            self.st_grid.addWidget(bar(s.hp / s.hp_max), i, 1)
            self.st_grid.addWidget(bar(s.shield / s.shield_max, color=theme.ACCENT), i, 2)
        self._selected()
