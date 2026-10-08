"""Fenêtre principale : en-tête (date, crédits, temps), alertes, onglets."""
import os

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel,
                               QMainWindow, QMessageBox, QProgressBar, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from ..career import Career, GameError
from ..timeutils import format_date, parse_duration
from ..ui.formatting import money
from . import theme
from .tabs.combat_tab import CombatTab
from .tabs.console_tab import ConsoleTab
from .tabs.dashboard import DashboardTab
from .tabs.economy_tab import EconomyTab
from .tabs.strike_tab import StrikeTab
from .tabs.system_tab import SystemTab
from .workers import Worker

SPEEDS = [("1 s/s", 1), ("10 s/s", 10), ("1 min/s", 60), ("10 min/s", 600), ("1 h/s", 3600), ("6 h/s", 21600),
          ("1 j/s", 86400), ("10 j/s", 864000)]
HELP = """<h3>Comment jouer</h3>
<p><b>📋 Contrats</b> : acceptez des contrats ; les événements ⚠ prioritaires (attaques, astéroïdes) ne se refusent pas.<br>
<b>⚔ Combat</b> : choisissez un composant du vaisseau (clic sur la vue 3D), une station qui le voit, calculez la visée
(la cible bouge : visez <i>P + V·tau</i>) ou payez l'ordinateur de bord, puis tirez.<br>
<b>🎯 Tir interplanétaire</b> : frappes, flottes (bombes à détonation de proximité) et astéroïdes ; « Chercher des fenêtres »
utilise <i>votre</i> vitesse et votre projectile, « Corriger » vise le point exact.<br>
<b>🛠 Économie</b> : réparations, améliorations, nouveaux lanceurs, sauvegarde.<br>
<b>⌨ Console</b> : toutes les commandes du mode terminal.</p>
<p>Barre d'espace : lecture / pause du temps. Les vues 3D se tournent à la souris, la molette zoome.</p>"""


class MainWindow(QMainWindow):
    def __init__(self, career: Career, saves_dir="saves"):
        super().__init__()
        self.k = career
        self.saves_dir = saves_dir
        self.pool = QThreadPool.globalInstance()
        self._workers = []
        self.setWindowTitle("Saturn Gauss — commandement orbital")
        self.resize(1560, 940)
        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(8, 6, 8, 4)

        # ---- en-tête
        head = QFrame()
        head.setStyleSheet(f"QFrame {{ background:{theme.PANEL}; border:1px solid {theme.BORDER}; border-radius:8px; }}"
                           "QLabel { border:none; }")
        h = QHBoxLayout(head)
        brand = QLabel("◉ SATURN GAUSS")
        brand.setStyleSheet(f"color:{theme.ACCENT}; font-size:15pt; font-weight:bold;")
        h.addWidget(brand)
        h.addSpacing(18)
        self.l_date, self.l_credits, self.l_rank = QLabel(), QLabel(), QLabel()
        for w in (self.l_date, self.l_credits, self.l_rank):
            w.setStyleSheet("font-size:12pt; font-weight:bold; color:white;")
            h.addWidget(w)
            h.addSpacing(14)
        h.addStretch(1)
        for text, dt in (("+1 h", 3600), ("+1 j", 86400), ("+7 j", 7 * 86400), ("+30 j", 30 * 86400)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, d=dt: self.advance(d))
            h.addWidget(b)
        b = QPushButton("Aller à…")
        b.clicked.connect(self.advance_dialog)
        h.addWidget(b)
        self.b_play = QPushButton("▶ Lecture")
        self.b_play.setCheckable(True)
        self.b_play.setObjectName("accent")
        self.b_play.toggled.connect(self._play_toggled)
        h.addWidget(self.b_play)
        self.cb_speed = QComboBox()
        for text, s in SPEEDS:
            self.cb_speed.addItem(text, s)
        self.cb_speed.setCurrentIndex(4)
        h.addWidget(self.cb_speed)
        v.addWidget(head)

        # ---- bandeau d'alerte
        self.banner_box = QFrame()
        bb = QHBoxLayout(self.banner_box)
        bb.setContentsMargins(0, 0, 0, 0)
        self.banner = QLabel()
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        bb.addWidget(self.banner, 1)
        self.b_banner_go = QPushButton("Voir")
        self.b_banner_go.clicked.connect(self._banner_go)
        b2 = QPushButton("✕")
        b2.clicked.connect(self.banner_box.hide)
        bb.addWidget(self.b_banner_go)
        bb.addWidget(b2)
        self.banner_box.hide()
        v.addWidget(self.banner_box)

        # ---- onglets
        self.tabs = QTabWidget()
        self.dashboard = DashboardTab(self)
        self.system_tab = SystemTab(self)
        self.combat = CombatTab(self)
        self.strike = StrikeTab(self)
        self.economy = EconomyTab(self)
        self.console = ConsoleTab(self)
        self._tab_index = {}
        for key, w, title in (("dash", self.dashboard, "📋 Contrats"), ("system", self.system_tab, "🌌 Système solaire"),
                              ("combat", self.combat, "⚔ Combat"), ("strike", self.strike, "🎯 Tir interplanétaire"),
                              ("eco", self.economy, "🛠 Stations && économie"), ("console", self.console, "⌨ Console")):
            self._tab_index[key] = self.tabs.addTab(w, title)
        self.tabs.currentChanged.connect(lambda _: self.refresh_all())
        v.addWidget(self.tabs, 1)

        # ---- barre d'état, menus, minuterie
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setMaximumWidth(160)
        self.busy.hide()
        self.statusBar().addPermanentWidget(self.busy)
        self._build_menus()
        QShortcut(QKeySequence(Qt.Key_Space), self, activated=lambda: self.b_play.toggle())
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._tick)
        self._ticks = 0
        self.refresh_all()

    # ------------------------------------------------------------------ menus / dialogues
    def _build_menus(self):
        m = self.menuBar().addMenu("&Fichier")
        for text, fn, key in (("Nouvelle partie…", self.new_game_dialog, None), ("Charger…", self.load_dialog, "Ctrl+O"),
                              ("Sauvegarder…", self.save_dialog, "Ctrl+S"), ("Quitter", self.close, "Ctrl+Q")):
            a = QAction(text, self)
            a.triggered.connect(lambda _=False, f=fn: f())
            if key:
                a.setShortcut(key)
            m.addAction(a)
        m = self.menuBar().addMenu("&Aide")
        a = QAction("Comment jouer", self)
        a.triggered.connect(lambda: QMessageBox.information(self, "Comment jouer", HELP))
        m.addAction(a)

    def save_dialog(self):
        os.makedirs(self.saves_dir, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder", os.path.join(self.saves_dir, "partie.pkl"), "Parties (*.pkl)")
        if path:
            self.k.save(path)
            self.status(f"Partie sauvegardée : {path}")

    def load_dialog(self):
        os.makedirs(self.saves_dir, exist_ok=True)
        path, _ = QFileDialog.getOpenFileName(self, "Charger", self.saves_dir, "Parties (*.pkl)")
        if path:
            self.set_career(Career.load(path))
            self.status(f"Partie chargée : {path}")

    def new_game_dialog(self):
        seed, ok = QInputDialog.getInt(self, "Nouvelle partie", "Graine du hasard :", 0, 0, 10 ** 6)
        if ok:
            assist = QMessageBox.question(self, "Nouvelle partie", "Activer l'ordinateur de visée interplanétaire ?") == QMessageBox.Yes
            self.set_career(Career(seed=seed, assist=assist))

    def advance_dialog(self):
        text, ok = QInputDialog.getText(self, "Faire passer le temps", "Durée (ex : 3d, 12h, 45m, 2y) :", text="1d")
        if ok:
            try:
                self.advance(parse_duration(text))
            except ValueError as e:
                self.status(str(e), error=True)

    # ------------------------------------------------------------------ état et messages
    def status(self, text, error=False):
        self.statusBar().setStyleSheet(f"color:{theme.BAD if error else theme.DIM}")
        self.statusBar().showMessage(text, 12000)
        if error:
            self.console.log(f"✘ {text}")

    def log(self, text):
        self.console.log(text)

    def date_text(self):
        return format_date(self.k.t)

    def guard(self, fn, *args):
        try:
            return True, fn(*args)
        except (GameError, ValueError, KeyError, IndexError) as e:
            self.status(str(e), error=True)
            return False, None

    def _flush_messages(self):
        msgs = self.k.pop_messages()
        urgent = False
        for m in msgs:
            self.console.log(m)
            self.status(m, error=("⚠" in m or "ÉCHEC" in m or "CATASTROPHE" in m))
            if "PRIORITAIRE" in m or "RIPOSTE" in m:
                urgent = True
                self.banner.setText(m)
                self.banner_box.show()
        if urgent:
            self.pause()
            f = self.k.focus
            if f is not None and f.kind == "defense":
                self.goto("combat")

    def after_action(self, flush=True):
        if flush:
            self._flush_messages()
        self.refresh_all()

    def refresh_all(self):
        k = self.k
        self.l_date.setText(f"📅 {format_date(k.t)}")
        self.l_credits.setText(f"💰 {money(k.credits)}")
        self.l_rank.setText(f"★ rang {k.rank}")
        cur = self.tabs.currentWidget()
        for tab in (self.dashboard, self.system_tab, self.combat, self.strike, self.economy):
            if tab is cur or tab is self.dashboard:      # les onglets cachés se rafraîchissent à l'ouverture
                tab.refresh()
        self._update_banner()

    def _update_banner(self):
        pri = [c for c in self.k.board if c.priority and c.state == "active"]
        if not pri:
            self.banner_box.hide()

    def _banner_go(self):
        f = self.k.focus
        self.goto("combat" if f is not None and f.kind == "defense" else "dash")

    def goto(self, key):
        self.tabs.setCurrentIndex(self._tab_index[key])

    def goto_for(self, ct):
        self.goto("combat" if ct.kind == "defense" else "strike")

    # ------------------------------------------------------------------ temps
    def advance(self, dt):
        self.pause()
        self.k.advance(dt, interruptible=True)
        self.after_action()

    def pause(self):
        if self.b_play.isChecked():
            self.b_play.setChecked(False)

    def _play_toggled(self, on):
        self.b_play.setText("⏸ Pause" if on else "▶ Lecture")
        if on:
            self.timer.start()
        else:
            self.timer.stop()

    def _battle_close(self):
        try:
            return self.k._battle_close()
        except Exception:  # noqa: BLE001
            return False

    def _tick(self):
        dt = self.cb_speed.currentData() * 0.1
        if self._battle_close():
            dt = min(dt, 120.0)
        self.k.advance(dt, interruptible=True)
        self._ticks += 1
        if self.k.messages:
            self._flush_messages()
            self.refresh_all()
            return
        self.l_date.setText(f"📅 {format_date(self.k.t)}")
        self.system_tab.view.update()
        self.combat.tick()
        if self._ticks % 10 == 0:
            self.refresh_all()

    # ------------------------------------------------------------------ calculs en tâche de fond
    def run_async(self, fn, done, label="Calcul en cours…", guard=False):
        self.pause()
        self.tabs.setEnabled(False)
        self.busy.show()
        self.status(label)
        w = Worker(fn)

        def finish():
            self.tabs.setEnabled(True)
            self.busy.hide()
            if w in self._workers:
                self._workers.remove(w)

        def ok(res):
            finish()
            done(res)

        def bad(msg):
            finish()
            self.status(msg.split(": ", 1)[-1], error=True)
            self.after_action()

        w.signals.progress.connect(lambda m: self.status(m))
        w.signals.done.connect(ok)
        w.signals.failed.connect(bad)
        self._workers.append(w)
        self.pool.start(w)

    def set_career(self, k: Career):
        self.pause()
        self.k = k
        self.console.shell = None
        self.system_tab.view.k = self.combat.saturn.k = self.combat.ship3d.k = self.strike.view.k = k
        self.refresh_all()

    def closeEvent(self, e):
        self.timer.stop()
        self.pool.waitForDone(3000)
        super().closeEvent(e)
