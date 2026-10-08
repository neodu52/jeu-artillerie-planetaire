"""Onglet Combat : défendre Saturne contre des vaisseaux (visée, composants, munitions)."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ...combat import engagement as eng
from ...combat.ammo import AMMO
from ...constants import C_KMS
from ...contracts import DefenseOp
from ...ui.formatting import fmt_mass, money
from .. import theme
from ..calc import evaluate
from ..common import bar, cell, hp_cell, new_table, spin, title
from ..saturn_view import SaturnView
from ..ship_view import ShipView


class CombatTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        # ---------------------------------------------------------------- colonne gauche : vues 3D
        left = QSplitter(Qt.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        bar_row = QHBoxLayout()
        hv = QVBoxLayout()
        self.l_head = QLabel("Aucune attaque en cours")
        self.l_head.setObjectName("title")
        self.l_sub = QLabel("")
        self.l_sub.setStyleSheet(f"color:{theme.DIM}")
        hv.addWidget(self.l_head)
        hv.addWidget(self.l_sub)
        bar_row.addLayout(hv, 1)
        for text, km in (("Stations", 7e5), ("Large", 2.4e6), ("Saturne", 2.2e5)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, v=km: self.saturn.set_extent(v))
            bar_row.addWidget(b)
        tl.addLayout(bar_row)
        self.saturn = SaturnView(win.k)
        self.saturn.clicked.connect(self._saturn_click)
        tl.addWidget(self.saturn, 1)
        left.addWidget(top)
        bot = QWidget()
        bl = QVBoxLayout(bot)
        row = QHBoxLayout()
        row.addWidget(QLabel("Vaisseau :"))
        self.cb_ship = QComboBox()
        self.cb_ship.currentIndexChanged.connect(self._ship_changed)
        row.addWidget(self.cb_ship, 1)
        b = QPushButton("👁 Vue du tireur")
        b.clicked.connect(lambda: self.ship3d.view_from_shooter())
        row.addWidget(b)
        b = QPushButton("Réinitialiser")
        b.clicked.connect(lambda: self.ship3d.reset_view())
        row.addWidget(b)
        bl.addLayout(row)
        self.ship3d = ShipView(win.k)
        self.ship3d.clicked.connect(self._ship3d_click)
        bl.addWidget(self.ship3d, 1)
        left.addWidget(bot)
        left.setSizes([360, 420])
        split.addWidget(left)

        # ---------------------------------------------------------------- colonne droite : commandes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(540)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        scroll.setWidget(panel)
        split.addWidget(scroll)
        split.setSizes([700, 640])

        hint = QLabel("① choisir la cible   ② choisir une station qui la voit   ③ calculer la visée   ④ tirer")
        hint.setStyleSheet(f"color:{theme.ACCENT}")
        hint.setWordWrap(True)
        pl.addWidget(hint)

        g = QGroupBox("① Composants du vaisseau (cliquez une ligne ou la vue 3D)")
        gl = QVBoxLayout(g)
        self.t_comp = new_table(["#", "Composant", "Intégrité", "Blindage", "Vu du tireur"], stretch=4)
        self.t_comp.setMinimumHeight(190)
        self.t_comp.itemSelectionChanged.connect(self._comp_selected)
        gl.addWidget(self.t_comp)
        pl.addWidget(g)

        g = QGroupBox("② Tireur")
        gl = QVBoxLayout(g)
        self.cb_shooter = QComboBox()
        self.cb_shooter.currentIndexChanged.connect(self._shooter_changed)
        gl.addWidget(self.cb_shooter)
        self.l_limits = QLabel()
        self.l_limits.setWordWrap(True)
        self.l_limits.setStyleSheet(f"color:{theme.DIM}")
        gl.addWidget(self.l_limits)
        self.t_vis = new_table(["Station", "Distance (km)", "Visibilité de la cible"], stretch=2, select=False)
        self.t_vis.setMaximumHeight(170)
        gl.addWidget(self.t_vis)
        pl.addWidget(g)

        g = QGroupBox("Projectile")
        gg = QGridLayout(g)
        self.cb_ammo = QComboBox()
        self.cb_ammo.currentIndexChanged.connect(self._ammo_changed)
        self.sp_mass = spin(1e-6, 2e5, 1.0, 6, 0.1, " kg")
        self.sp_len = spin(1e-3, 100, 0.3, 4, 0.05, " m")
        self.sp_rad = spin(1e-4, 2.0, 0.012, 5, 0.002, " m")
        self.sp_speed = spin(0.01, 299792.0, 70.0, 4, 1.0, " % c")
        self.l_speed_unit = QLabel()
        self.l_energy = QLabel()
        self.l_cost = QLabel()
        self.l_ammo = QLabel()
        self.l_ammo.setWordWrap(True)
        self.l_ammo.setStyleSheet(f"color:{theme.DIM}")
        rows = (("Munition", self.cb_ammo), ("", self.l_ammo), ("Masse", self.sp_mass), ("Longueur", self.sp_len),
                ("Rayon", self.sp_rad), ("Vitesse", self.sp_speed), ("Énergie", self.l_energy), ("Coût du tir", self.l_cost))
        for i, (t, w) in enumerate(rows):
            gg.addWidget(QLabel(t), i, 0)
            gg.addWidget(w, i, 1)
        self.sp_mass.editingFinished.connect(self._mass_edited)
        self.sp_len.editingFinished.connect(self._geom_edited)
        self.sp_rad.editingFinished.connect(self._geom_edited)
        self.sp_speed.editingFinished.connect(self._speed_edited)
        pl.addWidget(g)

        g = QGroupBox("③ Visée (repère écliptique)")
        gg = QGridLayout(g)
        self.sp_lon = spin(0, 360, 0, 7, 0.0001, " °", 140)
        self.sp_lat = spin(-90, 90, 0, 7, 0.0001, " °", 140)
        self.sp_lon.editingFinished.connect(self._aim_edited)
        self.sp_lat.editingFinished.connect(self._aim_edited)
        gg.addWidget(QLabel("Longitude"), 0, 0)
        gg.addWidget(self.sp_lon, 0, 1)
        gg.addWidget(QLabel("Latitude"), 1, 0)
        gg.addWidget(self.sp_lat, 1, 1)
        self.b_solve = QPushButton("🧮 Ordinateur de bord (150 cr)")
        self.b_solve.setObjectName("accent")
        self.b_solve.clicked.connect(self.solve)
        self.b_data = QPushButton("📐 Données pour calculer")
        self.b_data.clicked.connect(self.show_data)
        gg.addWidget(self.b_solve, 0, 2)
        gg.addWidget(self.b_data, 1, 2)
        pl.addWidget(g)

        g = QGroupBox("Calculatrice")
        gl = QVBoxLayout(g)
        self.calc_in = QLineEdit()
        self.calc_in.setPlaceholderText("ex : atan2(P[1]+V[1]*tau-S[1], P[0]+V[0]*tau-S[0])   (P, V, S, d, tau, vp, c)")
        self.calc_in.returnPressed.connect(self.calc)
        self.calc_out = QLabel("")
        self.calc_out.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.calc_out.setStyleSheet(f"color:{theme.GOOD}")
        gl.addWidget(self.calc_in)
        gl.addWidget(self.calc_out)
        pl.addWidget(g)

        row = QHBoxLayout()
        self.b_fire = QPushButton("⚡ FEU")
        self.b_fire.setObjectName("fire")
        self.b_fire.clicked.connect(self.fire)
        row.addWidget(self.b_fire, 2)
        for text, dt in (("+1 s", 1), ("+5 s", 5), ("+20 s", 20), ("+1 min", 60), ("+10 min", 600)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, d=dt: self.step(d))
            row.addWidget(b)
        pl.addLayout(row)

        g = QGroupBox("④ Journal du combat")
        gl = QVBoxLayout(g)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMinimumHeight(170)
        gl.addWidget(self.log)
        pl.addWidget(g)
        pl.addStretch(1)
        self._lock = False

    # ------------------------------------------------------------------ accès
    @property
    def k(self):
        return self.win.k

    def battle(self):
        f = self.k.focus
        return f.op.battle if f is not None and isinstance(f.op, DefenseOp) else None

    def selected_ship(self):
        b = self.battle()
        if not b:
            return None
        sid = self.cb_ship.currentData()
        return next((s for s in b.ships if s.id == sid), b.ships[0] if b.ships else None)

    def _vp(self):
        return C_KMS if self.k.launcher_of().kind == "beam" else self.k.speed

    # ------------------------------------------------------------------ interactions
    def _ship_changed(self):
        if self._lock:
            return
        s = self.selected_ship()
        if s is not None:
            idx = self.k.target_sel[1] if self.k.target_sel and self.k.target_sel[0] == s.id else None
            self.k.target_sel = (s.id, idx) if idx is not None else None
        self.refresh()

    def _comp_selected(self):
        if self._lock:
            return
        r = self.t_comp.currentRow()
        s = self.selected_ship()
        if r >= 0 and s is not None:
            self.k.target_sel = (s.id, r)
            self.ship3d.set_ship(s, r)
            self._refresh_vis()
            self._refresh_numbers()

    def _ship3d_click(self, x, y):
        i = self.ship3d.pick(x, y)
        if i is not None:
            self.t_comp.selectRow(i)

    def _saturn_click(self, x, y):
        hit = self.saturn.pick(x, y)
        if not hit:
            return
        _, kind, ident = hit
        if kind == "station":
            if self.win.guard(self.k.use, ident)[0]:
                self.win.after_action()
        else:
            i = self.cb_ship.findData(ident)
            if i >= 0:
                self.cb_ship.setCurrentIndex(i)

    def _shooter_changed(self):
        if self._lock or self.cb_shooter.currentData() is None:
            return
        if self.win.guard(self.k.use, self.cb_shooter.currentData())[0]:
            self.win.after_action()

    def _ammo_changed(self):
        if self._lock or not self.cb_ammo.currentData():
            return
        if self.win.guard(self.k.set_ammo, self.cb_ammo.currentData())[0]:
            self.refresh()

    def _mass_edited(self):
        self.win.guard(self.k.set_mass, self.sp_mass.value())
        self.refresh()

    def _geom_edited(self):
        self.k.length, self.k.radius = self.sp_len.value(), self.sp_rad.value()
        self.refresh()

    def _speed_edited(self):
        v = self.sp_speed.value()
        self.k.speed = v / 100.0 * C_KMS if self._pct else v
        if self.k.speed >= C_KMS:
            self.k.speed = C_KMS * (1 - 1e-9)
        self.refresh()

    def _aim_edited(self):
        self.k.lon, self.k.lat = self.sp_lon.value() % 360.0, self.sp_lat.value()
        self._refresh_numbers()

    def step(self, dt):
        self.win.pause()
        self.k.advance(dt, interruptible=True)
        self.win.after_action()

    def solve(self):
        ok, res = self.win.guard(self.k.solve_aim)
        if ok:
            lon, lat, tau, dist, fee = res
            self.log.appendPlainText(f"Ordinateur de bord (-{fee:.0f} cr) : lon {lon:.7f}°, lat {lat:+.7f}° "
                                     f"| vol {tau:.4f} s | distance {dist:,.1f} km".replace(",", " "))
            self.win.after_action()

    def show_data(self):
        s = self.selected_ship()
        if s is None or not self.k.target_sel:
            self.win.status("Désignez d'abord un composant.", error=True)
            return
        k = self.k
        origin, _ = k.shooter.rel_state(k.t)
        pos, vel = s.state(k.t)
        cen = pos + s.axes(vel) @ (s.comps[k.target_sel[1]].center / 1000.0)
        d = float(np.linalg.norm(cen - origin))
        vp = self._vp()
        self.log.appendPlainText(
            f"── Données ({s.name} / {s.comps[k.target_sel[1]].name}) ──\n"
            f"P (cible, km)  = ({cen[0]:.4f}, {cen[1]:.4f}, {cen[2]:.4f})\n"
            f"V (km/s)       = ({vel[0]:.5f}, {vel[1]:.5f}, {vel[2]:.5f})\n"
            f"S (tireur, km) = ({origin[0]:.4f}, {origin[1]:.4f}, {origin[2]:.4f})\n"
            f"d = {d:,.2f} km ; tau = d / vp = {d / vp:.7f} s ; anticipation V·tau = {np.linalg.norm(vel) * d / vp * 1000:,.1f} m\n"
            f"Point visé A = P + V·tau ; lon = atan2(Ay-Sy, Ax-Sx) ; lat = asin((Az-Sz)/|A-S|)".replace(",", " "))

    def calc(self):
        try:
            self.calc_out.setStyleSheet(f"color:{theme.GOOD}")
            self.calc_out.setText(evaluate(self.k, self.calc_in.text()))
        except Exception as e:  # noqa: BLE001
            self.calc_out.setStyleSheet(f"color:{theme.BAD}")
            self.calc_out.setText(f"Erreur : {e}")

    def fire(self):
        self.win.pause()
        ok, rep = self.win.guard(self.k.fire)
        if not ok:
            return
        for line in rep["lines"]:
            self.log.appendPlainText(line)
        if "origin" in rep:
            self.saturn.flash(rep["origin"], rep["end"], "#ffb703" if rep.get("hit") else "#8794b3")
        if rep.get("hit"):
            self.ship3d.flash_hit(rep.get("comp_index"))
        self.log.appendPlainText(f"Coût du tir : {money(rep['cost'])}\n")
        self.win.after_action()

    # ------------------------------------------------------------------ rafraîchissement
    def _refresh_vis(self):
        k, s = self.k, self.selected_ship()
        self.t_vis.setRowCount(0)
        if s is None or not k.target_sel or k.target_sel[0] != s.id:
            return
        rows = []
        for sh in k.shooters:
            from ...combat.launchers import effective, LAUNCHERS
            lau = effective(LAUNCHERS[sh.launcher], k.upgrades)
            vp = C_KMS if lau.kind == "beam" else float(np.clip(k.speed, lau.v_min_kms, lau.v_max_kms))
            r, _ = sh.rel_state(k.t)
            pos, _ = s.state(k.t)
            dist = float(np.linalg.norm(pos - r))
            try:
                ok, why = eng.visibility(r, s, k.target_sel[1], k.t, vp)
            except Exception:  # noqa: BLE001
                ok, why = False, "?"
            if not sh.online:
                ok, why = False, "hors service"
            elif dist > lau.max_range_km:
                ok, why = False, "hors de portée"
            rows.append((sh, dist, ok, why))
        self.t_vis.setRowCount(len(rows))
        for i, (sh, dist, ok, why) in enumerate(rows):
            self.t_vis.setItem(i, 0, cell(("▶ " if sh.id == k.use_idx else "") + sh.name, theme.ACCENT if sh.id == k.use_idx else None))
            self.t_vis.setItem(i, 1, cell(f"{dist:,.0f}".replace(",", " "), None, "r"))
            self.t_vis.setItem(i, 2, cell(("✔ " if ok else "✘ ") + why, theme.GOOD if ok else theme.BAD))

    def _refresh_numbers(self):
        k = self.k
        E = k.kinetic_energy()
        self.l_energy.setText(f"{E:.3e} J  ({E / 4.184e15:.4g} Mt)")
        co = k.cost_preview()
        self.l_cost.setText(f"{money(co['total'])}  (munition {money(co['munition'])} + énergie {money(co['energie'])})")
        self.l_ammo.setText(AMMO[k.ammo].desc if k.ammo in AMMO else "")

    def refresh(self):
        k = self.k
        self._lock = True
        self.saturn.k = self.ship3d.k = k
        b = self.battle()
        ships = b.ships if b else []
        cur = self.cb_ship.currentData()
        self.cb_ship.clear()
        for s in ships:
            self.cb_ship.addItem(f"{s.name} — {s.spec.name} [{s.status}]", s.id)
        want = k.target_sel[0] if k.target_sel else cur
        i = self.cb_ship.findData(want)
        self.cb_ship.setCurrentIndex(i if i >= 0 else 0)
        s = self.selected_ship()
        # en-tête
        if b:
            eta = ""
            alive = [x for x in b.ships if not x.neutralized]
            if alive:
                d = min(np.linalg.norm(x.state(k.t)[0]) for x in alive)
                eta = f"  ·  vaisseau le plus proche : {d:,.0f} km de Saturne (objectif ≤ {b.objective_km:,.0f} km)".replace(",", " ")
            self.l_head.setText(f"{k.focus.title}  ·  état : {b.state}")
            self.l_sub.setText(eta.lstrip(" ·"))
        else:
            self.l_head.setText("Aucune attaque sélectionnée")
            self.l_sub.setText("Ouvrez un événement ⚠ depuis le Tableau de bord (« Travailler dessus »).")
        # composants
        self.t_comp.setRowCount(len(s.comps) if s else 0)
        sel = k.target_sel[1] if (k.target_sel and s and k.target_sel[0] == s.id) else None
        origin = k.shooter.rel_state(k.t)[0]
        if s:
            for i, c in enumerate(s.comps):
                if c.alive:
                    try:
                        ok, why = eng.visibility(origin, s, i, k.t, max(self._vp(), 1.0))
                    except Exception:  # noqa: BLE001
                        ok, why = False, "?"
                else:
                    ok, why = False, "détruit"
                self.t_comp.setItem(i, 0, cell(i + 1, None, "c"))
                self.t_comp.setItem(i, 1, cell(c.name + ("  ★" if c.critical else ""), theme.WARN if c.critical else None))
                self.t_comp.setItem(i, 2, hp_cell(max(c.hp, 0) / c.hp_max))
                self.t_comp.setItem(i, 3, cell(f"{c.armor_m:.2f} m", None, "r"))
                self.t_comp.setItem(i, 4, cell(("✔ " if ok else "✘ ") + why, theme.GOOD if ok else theme.DIM))
            if sel is not None:
                self.t_comp.selectRow(sel)
        self.ship3d.set_ship(s, sel)
        # tireur
        self.cb_shooter.clear()
        for sh in k.shooters:
            lau = k.launcher_of(sh)
            self.cb_shooter.addItem(f"{sh.id} · {sh.name} — {lau.name}" + ("" if sh.online else "  [HORS SERVICE]"), sh.id)
        self.cb_shooter.setCurrentIndex(max(self.cb_shooter.findData(k.use_idx), 0))
        lau = k.launcher_of()
        fast = lau.v_max_kms > 1000
        self._pct = fast
        vtxt = f"{lau.v_min_kms / C_KMS:.2f}c – {lau.v_max_kms / C_KMS:.3f}c" if fast else f"{lau.v_min_kms:g} – {lau.v_max_kms:g} km/s"
        self.l_limits.setText(f"Vitesse {vtxt} · masse ≤ {lau.max_mass_kg:.3g} kg · portée {lau.max_range_km:,.0f} km · "
                              f"recharge {lau.reload_s:.0f} s".replace(",", " "))
        # projectile
        self.cb_ammo.clear()
        for key in lau.ammo:
            self.cb_ammo.addItem(AMMO[key].name, key)
        self.cb_ammo.setCurrentIndex(max(self.cb_ammo.findData(k.ammo), 0))
        beam = lau.kind == "beam"
        for w in (self.sp_mass, self.sp_len, self.sp_rad):
            w.setEnabled(not beam)
        self.sp_speed.setEnabled(not beam)
        self.sp_mass.setValue(k.mass_kg())
        self.sp_len.setValue(k.length)
        self.sp_rad.setValue(k.radius)
        self.sp_speed.setSuffix(" % c" if fast else " km/s")
        self.sp_speed.setRange(0.01, 99.9999999 if fast else 299792.0)
        self.sp_speed.setValue(k.speed / C_KMS * 100 if fast else k.speed)
        self.sp_lon.setValue(k.lon)
        self.sp_lat.setValue(k.lat)
        self.b_fire.setEnabled(b is not None and k.focus.state == "active")
        self.b_solve.setEnabled(b is not None and bool(k.target_sel))
        self._lock = False
        self._refresh_vis()
        self._refresh_numbers()
        self.saturn.update()

    def tick(self):
        self.saturn.update()
        s = self.selected_ship()
        if s is not None:
            self.ship3d.update()
