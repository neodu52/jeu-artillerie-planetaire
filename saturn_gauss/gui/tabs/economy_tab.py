"""Onglet Stations & économie : état des tireurs, réparations, améliorations, lanceurs, sauvegardes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget)

from ...combat.launchers import LAUNCHERS, effective, energy_cap_j
from ...economy import UPGRADES, upgrade_cost
from ...ui.formatting import money
from .. import theme
from ..common import bar, cell, hp_cell, new_table, title


class EconomyTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        lay.addLayout(top, 2)

        box = QGroupBox("Tireurs (canon + stations)")
        bl = QVBoxLayout(box)
        self.t_sh = new_table(["#", "Nom", "Lanceur", "Structure", "Bouclier", "État", "Réparation"], stretch=1, select=True)
        bl.addWidget(self.t_sh)
        r = QHBoxLayout()
        self.b_rep = QPushButton("🔧 Réparer la sélection")
        self.b_all = QPushButton("🔧 Tout réparer")
        self.cb_launcher = QComboBox()
        self.b_refit = QPushButton("Équiper le lanceur →")
        self.b_rep.clicked.connect(self.repair_sel)
        self.b_all.clicked.connect(lambda: self._do(self.win.k.repair, "all"))
        self.b_refit.clicked.connect(self.refit)
        for w in (self.b_rep, self.b_all, self.cb_launcher, self.b_refit):
            r.addWidget(w)
        bl.addLayout(r)
        top.addWidget(box, 3)

        box2 = QGroupBox("Lanceurs")
        b2 = QVBoxLayout(box2)
        self.t_l = new_table(["Lanceur", "Vitesse", "Masse max", "Portée", "Débloqué"], stretch=0, select=True)
        b2.addWidget(self.t_l)
        self.b_unlock = QPushButton("Débloquer")
        self.b_unlock.clicked.connect(self.unlock)
        b2.addWidget(self.b_unlock)
        top.addWidget(box2, 2)

        box3 = QGroupBox("Améliorations")
        b3 = QVBoxLayout(box3)
        self.t_up = new_table(["Amélioration", "Niveau", "Prix suivant", "Effet"], stretch=3, select=True)
        b3.addWidget(self.t_up)
        row = QHBoxLayout()
        self.b_buy = QPushButton("Acheter l'amélioration sélectionnée")
        self.b_buy.setObjectName("good")
        self.b_buy.clicked.connect(self.buy)
        self.l_cap = QLabel()
        row.addWidget(self.b_buy)
        row.addWidget(self.l_cap, 1)
        b3.addLayout(row)
        lay.addWidget(box3, 3)

        box4 = QGroupBox("Partie")
        b4 = QHBoxLayout(box4)
        for text, fn in (("💾 Sauvegarder", self.win.save_dialog), ("📂 Charger", self.win.load_dialog),
                         ("🆕 Nouvelle partie", self.win.new_game_dialog)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            b4.addWidget(b)
        lay.addWidget(box4)
        self._launch_keys = []
        self._up_keys = []

    def _do(self, fn, *a):
        if self.win.guard(fn, *a)[0]:
            self.win.after_action()

    def repair_sel(self):
        r = self.t_sh.currentRow()
        if r >= 0:
            self._do(self.win.k.repair, r)

    def refit(self):
        r = self.t_sh.currentRow()
        if r >= 0:
            self._do(self.win.k.refit, r, self.cb_launcher.currentData())

    def unlock(self):
        r = self.t_l.currentRow()
        if r >= 0:
            self._do(self.win.k.buy, self._launch_keys[r])

    def buy(self):
        r = self.t_up.currentRow()
        if r >= 0:
            self._do(self.win.k.buy, self._up_keys[r])

    def refresh(self):
        k = self.win.k
        keep = self.t_sh.currentRow()
        self.t_sh.setRowCount(len(k.shooters))
        for i, s in enumerate(k.shooters):
            lau = LAUNCHERS[s.launcher]
            vals = (s.id, s.name, lau.name, "", "", "OK" if s.online else "HORS SERVICE",
                    money(s.repair_cost) if s.damage_fraction > 1e-6 else "-")
            for j, v in enumerate(vals):
                self.t_sh.setItem(i, j, cell(v, theme.BAD if (j == 5 and not s.online) else None))
            self.t_sh.setItem(i, 3, hp_cell(s.hp / s.hp_max))
            self.t_sh.setItem(i, 4, hp_cell(s.shield / s.shield_max, theme.ACCENT))
        if keep >= 0:
            self.t_sh.selectRow(keep)
        self.cb_launcher.clear()
        for key in k.unlocked:
            if key != "canon":
                self.cb_launcher.addItem(LAUNCHERS[key].name, key)
        self._launch_keys = [key for key in LAUNCHERS if key != "canon"]
        self.t_l.setRowCount(len(self._launch_keys))
        for i, key in enumerate(self._launch_keys):
            l = effective(LAUNCHERS[key], k.upgrades)
            vit = f"{l.v_min_kms / 299792.458:.2f}c – {l.v_max_kms / 299792.458:.3f}c" if l.v_max_kms > 1000 else f"{l.v_min_kms:g}–{l.v_max_kms:g} km/s"
            vals = (l.name, vit, f"{l.max_mass_kg:.3g}", f"{l.max_range_km:,.0f} km".replace(",", " "),
                    "✔" if key in k.unlocked else money(l.unlock_cost))
            for j, v in enumerate(vals):
                self.t_l.setItem(i, j, cell(v, theme.GOOD if (j == 4 and key in k.unlocked) else None))
        self._up_keys = list(UPGRADES)
        self.t_up.setRowCount(len(self._up_keys))
        for i, key in enumerate(self._up_keys):
            u, lvl = UPGRADES[key], int(k.upgrades.get(key, 0))
            vals = (u.name, f"{lvl}/{u.max_level}", money(upgrade_cost(key, lvl)) if lvl < u.max_level else "MAX", u.desc)
            for j, v in enumerate(vals):
                self.t_up.setItem(i, j, cell(v))
        self.l_cap.setText(f"Énergie max du canon interplanétaire : {energy_cap_j(k.upgrades):.1e} J")
