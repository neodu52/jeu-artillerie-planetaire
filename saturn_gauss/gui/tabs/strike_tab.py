"""Onglet Tir interplanétaire : frappes, flottes lointaines, astéroïdes (guidage, fenêtres, correction)."""
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit,
                               QPushButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

from ...briefing import brief_text
from ...combat.ammo import AMMO
from ...combat.launchers import LAUNCHERS, effective, energy_cap_j
from ...constants import C_KMS
from ...contracts import AsteroidOp, DefenseOp, FleetOp, StrikeOp
from ...timeutils import format_date
from ...ui.formatting import fmt_duration, money
from .. import theme
from ..charts import ShotCharts
from ..common import cell, new_table, spin
from ..reports import planetary_report
from ..system_view import SolarSystemView


class StrikeTab(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self._lock = False
        lay = QHBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        lay.addWidget(split)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(520)
        panel = QWidget()
        pl = QVBoxLayout(panel)
        scroll.setWidget(panel)
        split.addWidget(scroll)

        g = QGroupBox("Contrat sélectionné")
        gl = QVBoxLayout(g)
        self.brief = QPlainTextEdit()
        self.brief.setReadOnly(True)
        self.brief.setFixedHeight(190)
        gl.addWidget(self.brief)
        pl.addWidget(g)

        g = QGroupBox("Projectile (canon interplanétaire)")
        gg = QGridLayout(g)
        self.cb_ammo = QComboBox()
        self.cb_ammo.currentIndexChanged.connect(self._ammo)
        self.sp_len = spin(1e-3, 100, 10, 4, 0.5, " m")
        self.sp_rad = spin(1e-4, 2, 0.3, 5, 0.01, " m")
        self.sp_mass = spin(1e-6, 2e5, 1, 6, 1, " kg")
        self.sp_kms = spin(0.1, 299792.4, 15, 3, 1, " km/s")
        self.sp_pct = spin(0.0001, 99.99999, 5, 6, 1, " % c")
        self.l_energy = QLabel()
        self.l_cost = QLabel()
        self.l_pen = QLabel()
        rows = (("Munition", self.cb_ammo), ("Longueur", self.sp_len), ("Rayon", self.sp_rad), ("Masse", self.sp_mass),
                ("Vitesse (km/s)", self.sp_kms), ("Vitesse (% de c)", self.sp_pct), ("Énergie", self.l_energy),
                ("Pénétration", self.l_pen), ("Coût du tir", self.l_cost))
        for i, (t, w) in enumerate(rows):
            gg.addWidget(QLabel(t), i, 0)
            gg.addWidget(w, i, 1)
        self.sp_len.editingFinished.connect(self._geom)
        self.sp_rad.editingFinished.connect(self._geom)
        self.sp_mass.editingFinished.connect(self._mass)
        self.sp_kms.editingFinished.connect(self._kms)
        self.sp_pct.editingFinished.connect(self._pct)
        pl.addWidget(g)

        g = QGroupBox("Visée (repère écliptique héliocentrique)")
        gg = QGridLayout(g)
        self.sp_lon = spin(0, 360, 0, 7, 0.001, " °", 150)
        self.sp_lat = spin(-90, 90, 0, 7, 0.001, " °", 150)
        self.sp_lon.editingFinished.connect(self._aim)
        self.sp_lat.editingFinished.connect(self._aim)
        gg.addWidget(QLabel("Longitude"), 0, 0)
        gg.addWidget(self.sp_lon, 0, 1)
        gg.addWidget(QLabel("Latitude"), 1, 0)
        gg.addWidget(self.sp_lat, 1, 1)
        self.l_when = QLabel()
        gg.addWidget(self.l_when, 2, 0, 1, 2)
        pl.addWidget(g)

        g = QGroupBox("Ordinateur de bord (payant, facultatif)")
        gl = QVBoxLayout(g)
        r = QHBoxLayout()
        self.cb_auto = QCheckBox("Vitesse optimale (sinon : VOTRE vitesse)")
        self.sp_days = spin(0, 100000, 0, 1, 1, " j max")
        self.b_window = QPushButton("🔍 Chercher des fenêtres (400 cr)")
        self.b_window.setObjectName("accent")
        self.b_window.clicked.connect(self.search)
        r.addWidget(self.cb_auto, 1)
        r.addWidget(self.sp_days)
        gl.addLayout(r)
        gl.addWidget(self.b_window)
        self.t_win = new_table(["n", "Départ", "Arrivée", "Vol", "Vitesse", "Lon / lat", "Visib."], stretch=1)
        self.t_win.setFixedHeight(150)
        gl.addWidget(self.t_win)
        r = QHBoxLayout()
        self.b_plan = QPushButton("📅 Charger le plan")
        self.b_refine = QPushButton("🎯 Corriger par tirs d'essai (800 cr)")
        self.b_refine.setObjectName("accent")
        self.b_plan.clicked.connect(self.load_plan)
        self.b_refine.clicked.connect(self.refine)
        r.addWidget(self.b_plan)
        r.addWidget(self.b_refine, 1)
        gl.addLayout(r)
        self.l_note = QLabel("")
        self.l_note.setWordWrap(True)
        self.l_note.setStyleSheet(f"color:{theme.DIM}")
        gl.addWidget(self.l_note)
        pl.addWidget(g)

        self.b_fire = QPushButton("⚡ FEU")
        self.b_fire.setObjectName("fire")
        self.b_fire.clicked.connect(self.fire)
        pl.addWidget(self.b_fire)
        g = QGroupBox("Résultat")
        gl = QVBoxLayout(g)
        self.result = QPlainTextEdit()
        self.result.setReadOnly(True)
        self.result.setMinimumHeight(160)
        gl.addWidget(self.result)
        pl.addWidget(g)
        pl.addStretch(1)

        right = QSplitter(Qt.Vertical)
        top = QWidget()
        tl = QVBoxLayout(top)
        row = QHBoxLayout()
        row.addWidget(QLabel("Vue 3D :"))
        for text, au in (("Système complet", 32), ("12 UA", 12), ("Interne", 1.8)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, a=au: self.view.set_extent(a))
            row.addWidget(b)
        row.addStretch(1)
        tl.addLayout(row)
        self.view = SolarSystemView(win.k)
        self.view.extent_au = 12
        self.view.reset_view()
        tl.addWidget(self.view, 1)
        right.addWidget(top)
        self.charts = ShotCharts()
        right.addWidget(self.charts)
        right.setSizes([520, 280])
        split.addWidget(right)
        split.setSizes([520, 760])
        self._windows = []

    @property
    def k(self):
        return self.win.k

    def _active(self):
        f = self.k.focus
        return f is not None and not isinstance(f.op, DefenseOp)

    # ------------------------------------------------------------------ édition
    def _ammo(self):
        if not self._lock and self.cb_ammo.currentData():
            if self.win.guard(self.k.set_ammo, self.cb_ammo.currentData())[0]:
                self.refresh()

    def _geom(self):
        if not self._lock:
            self.k.length, self.k.radius = self.sp_len.value(), self.sp_rad.value()
            self.refresh()

    def _mass(self):
        if not self._lock:
            self.win.guard(self.k.set_mass, self.sp_mass.value())
            self.refresh()

    def _kms(self):
        if not self._lock:
            self.k.speed = min(self.sp_kms.value(), C_KMS * (1 - 1e-9))
            self.refresh()

    def _pct(self):
        if not self._lock:
            self.k.speed = self.sp_pct.value() / 100.0 * C_KMS
            self.refresh()

    def _aim(self):
        if not self._lock:
            self.k.lon, self.k.lat = self.sp_lon.value() % 360.0, self.sp_lat.value()

    # ------------------------------------------------------------------ assistance (threads)
    def search(self):
        k = self.k
        days = self.sp_days.value() or None
        auto = self.cb_auto.isChecked()
        self.l_note.setText("Recherche en cours…")
        self.win.run_async(lambda prog: k.find_windows(auto=auto, max_days=days, progress=prog), self._windows_done,
                           "Calcul des fenêtres de tir…")

    def _windows_done(self, res):
        wins, fee = res
        self._windows = wins
        self.t_win.setRowCount(len(wins))
        for i, p in enumerate(wins):
            lon, lat = p.lon_lat
            sp = f"{p.speed / C_KMS * 100:.4f} %c" if p.speed > 1000 else f"{p.speed:.3f} km/s"
            vals = (i + 1, format_date(p.t_launch), format_date(p.t_arrival), fmt_duration(p.flight_s), sp,
                    f"{lon:.3f} / {lat:+.3f}", f"{p.visibility:.2f}")
            for j, v in enumerate(vals):
                self.t_win.setItem(i, j, cell(v))
        if wins:
            self.t_win.selectRow(0)
            self.l_note.setText(f"{len(wins)} fenêtre(s) (frais {money(fee)}). Chargez-en une puis corrigez.")
        else:
            self.l_note.setText(self.k.guidance.last_note or "Aucune fenêtre trouvée (essayez d'attendre ou de changer de vitesse).")
        self.win.after_action()

    def load_plan(self):
        r = self.t_win.currentRow()
        if r < 0 or r >= len(self._windows):
            self.win.status("Cherchez d'abord des fenêtres.", error=True)
            return
        plan = self._windows[r]
        self.k.windows = self._windows
        self.win.run_async(lambda prog: self.k.apply_plan(plan), self._plan_done, "Avance jusqu'à la date de tir…",
                           guard=True)

    def _plan_done(self, _):
        self.l_note.setText(f"Plan chargé. Tir le {format_date(self.k.t)}, impact prévu {format_date(self.k.plan.t_arrival)}.")
        self.win.after_action()

    def refine(self):
        k = self.k
        from ...ballistics.cannon import direction_vector
        from ...guidance import Plan
        if k.plan is None:
            self.win.status("Chargez d'abord un plan de tir.", error=True)
            return
        plan = Plan(k.t, k.plan.t_arrival, k.speed * direction_vector(k.lon, k.lat), 0.0, 0.0, 1.0)
        self.l_note.setText("Tirs d'essai en cours…")
        self.win.run_async(lambda prog: k.refine(plan, progress=prog), self._refine_done, "Correction par tirs d'essai…")

    def _refine_done(self, new):
        if new.residual_km is None or new.residual_km > 25:
            self.l_note.setText(f"Correction non convergée (écart {new.residual_km:,.0f} km) : essayez une autre fenêtre.".replace(",", " "))
        else:
            self.k.apply_plan(new)
            self.l_note.setText(f"Correction terminée : écart résiduel {new.residual_km:.3f} km. Tir le {format_date(self.k.t)}.")
        self.win.after_action()

    def fire(self):
        k = self.k
        self.win.run_async(lambda prog: k.fire(), self._fire_done, "Simulation du vol…", guard=True)

    def _fire_done(self, rep):
        k = self.k
        self.result.setPlainText(planetary_report(k, rep) + f"\n\nCoût du tir : {money(rep['cost'])}")
        res = rep.get("result")
        op = k.focus.op if k.focus else None
        if res is not None:
            self.view.set_trajectory(res.positions)
            self.view.markers = [(res.final_pos, "impact / fin", theme.WARN)]
            planet = op.target.body if isinstance(op, StrikeOp) else (op.target.planet if isinstance(op, FleetOp) else None)
            radius = k.system.get(planet).radius if planet else None
            tgt = op.asteroid if isinstance(op, AsteroidOp) else (op.target if isinstance(op, FleetOp) else None)
            try:
                self.charts.show_result(k.system, res, planet=planet if isinstance(op, StrikeOp) else None,
                                        radius=radius if isinstance(op, StrikeOp) else None,
                                        target=None if isinstance(op, StrikeOp) else tgt)
            except Exception as e:  # noqa: BLE001
                self.win.log(f"(graphe indisponible : {e})")
        self.win.after_action()

    # ------------------------------------------------------------------ rafraîchissement
    def refresh(self):
        k = self.k
        self._lock = True
        self.view.k = k
        ok = self._active()
        self.brief.setPlainText(brief_text(k, k.focus) if ok else
                                "Sélectionnez un contrat de frappe, de flotte ou d'astéroïde dans le Tableau de bord\n"
                                "(bouton « Travailler dessus »).")
        lau = effective(LAUNCHERS["canon"], k.upgrades)
        self.cb_ammo.clear()
        for key in lau.ammo:
            self.cb_ammo.addItem(AMMO[key].name, key)
        self.cb_ammo.setCurrentIndex(max(self.cb_ammo.findData(k.ammo), 0))
        self.sp_len.setValue(k.length)
        self.sp_rad.setValue(k.radius)
        self.sp_mass.setValue(k.projectile.mass_kg)
        self.sp_kms.setValue(k.speed)
        self.sp_pct.setValue(k.speed / C_KMS * 100)
        self.sp_lon.setValue(k.lon)
        self.sp_lat.setValue(k.lat)
        E = k.projectile.energy_j(k.speed)
        txt = f"{E:.3e} J ({E / 4.184e15:.4g} Mt) — capacité {energy_cap_j(k.upgrades):.1e} J"
        style = f"color:{theme.GOOD}"
        if ok and isinstance(k.focus.op, StrikeOp):
            req = k.focus.op.energy_j
            dev = 100 * (E / req - 1)
            good = abs(dev) <= 100 * k.focus.op.energy_tol
            txt += f"\ncible {req:.3e} J → écart {dev:+.2f} %"
            style = f"color:{theme.GOOD if good else theme.BAD}"
            from ...solarsystem.bodies import Body  # noqa: F401
            pen = k.projectile.penetration_m(k.system.get(k.focus.op.target.body).surface_density)
            self.l_pen.setText(f"{pen:.1f} m" + (f" (min {k.focus.op.min_penetration_m:g} m)" if k.focus.op.min_penetration_m else ""))
        else:
            self.l_pen.setText("-")
        self.l_energy.setText(txt)
        self.l_energy.setStyleSheet(style)
        co = k.cost_preview() if k.launcher_of().key == "canon" else {"total": 0, "munition": 0, "energie": 0}
        self.l_cost.setText(f"{money(co['total'])} (munition {money(co['munition'])} + énergie {money(co['energie'])})")
        self.l_when.setText(f"Date de tir actuelle : {format_date(k.t)}" + (f"  ·  arrivée prévue : {format_date(k.plan.t_arrival)}" if k.plan else ""))
        usable = ok and k.shooter.launcher == "canon"
        self.b_fire.setEnabled(usable and k.focus.state == "active")
        for w in (self.b_window, self.b_plan, self.b_refine):
            w.setEnabled(usable and k.assist_enabled)
        if ok and not usable:
            self.l_note.setText("Le tireur actif n'est pas le canon interplanétaire : sélectionnez le contrat (focus).")
        self._lock = False
