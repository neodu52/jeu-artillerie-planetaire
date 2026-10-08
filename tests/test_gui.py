"""Tests de l'interface graphique (Qt hors écran). Ignorés si PySide6 est absent."""
import os

import numpy as np
import pytest

pytest.importorskip("PySide6")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from saturn_gauss.career import Career  # noqa: E402
from saturn_gauss.contracts import new_asteroid, new_fleet_contract  # noqa: E402
from saturn_gauss.gui.app import make_app  # noqa: E402
from saturn_gauss.gui.main_window import MainWindow  # noqa: E402

app = make_app()


def make(seed=3, quiet=False):
    k = Career(seed=seed)
    if quiet:
        k.next_attack = k.next_offer = k.next_asteroid = 1e30
    w = MainWindow(k)
    w.resize(1500, 900)
    w.show()
    return k, w


def wait_idle(w, timeout=60000):
    """Attend la fin d'un calcul en tâche de fond."""
    import time
    t0 = time.time()
    while not w.tabs.isEnabled() and time.time() - t0 < timeout / 1000:
        app.processEvents()
        time.sleep(0.02)                 # libère le GIL pour le thread de calcul (QTest.qWait ne le fait pas)
    assert w.tabs.isEnabled(), "calcul trop long"


def test_window_builds_and_all_tabs_render(tmp_path):
    k, w = make()
    for key in ("dash", "system", "combat", "strike", "eco", "console"):
        w.goto(key)
        app.processEvents()
        assert not w.grab().isNull()
    assert w.tabs.count() == 6
    assert w.dashboard.table.rowCount() == 6            # 6 contrats de frappe


def test_dashboard_accept_refuse_and_focus():
    k, w = make(quiet=True)
    w.dashboard.table.selectRow(0)
    w.dashboard.accept()
    assert k.contract(1).state == "active" and k.focus.id == 1
    assert w.tabs.currentIndex() == w._tab_index["strike"]
    w.goto("dash")
    w.dashboard.table.selectRow(1)
    w.dashboard.refuse()
    assert k.contract(2).state == "refused"


def test_time_controls_and_priority_banner():
    k, w = make(seed=3)
    w.advance(10 * 86400)                               # interrompu par l'attaque prioritaire
    assert k.t < k.board[0].t_created + 3 * 86400
    assert w.banner_box.isVisible() or not w.banner_box.isHidden()
    assert w.tabs.currentIndex() == w._tab_index["combat"]
    w.b_play.setChecked(True)
    t0 = k.t
    QTest.qWait(450)
    w.b_play.setChecked(False)
    assert k.t > t0


def test_combat_defense_through_the_widgets():
    k, w = make(seed=3, quiet=True)
    k.next_attack = k.t + 10.0
    k.advance(60.0, interruptible=True)
    w.after_action()
    ship = k.focus.op.battle.ships[0]
    while np.linalg.norm(ship.state(k.t)[0]) > 6e5:
        k.advance(300.0)
    w.after_action()
    c = w.combat
    assert c.cb_ship.count() == 1
    ri = [i for i, x in enumerate(ship.comps) if x.role == "reactor"][0]
    c.t_comp.selectRow(ri)
    assert k.target_sel == (ship.id, ri)
    assert c.t_vis.rowCount() == len(k.shooters)
    # choix de munition / masse / vitesse par les widgets
    c.cb_ammo.setCurrentIndex(c.cb_ammo.findData("ferrite"))
    c.sp_mass.setValue(3.0)
    c.sp_mass.editingFinished.emit()
    c.sp_speed.setValue(70.0)
    c.sp_speed.editingFinished.emit()
    assert k.ammo == "ferrite" and k.mass_kg() == pytest.approx(3.0, rel=1e-3)
    assert k.speed == pytest.approx(0.7 * 299792.458, rel=1e-6)
    # calculatrice
    c.calc_in.setText("tau*2")
    c.calc()
    assert c.calc_out.text() and "Erreur" not in c.calc_out.text()
    for _ in range(12):
        if ship.neutralized:
            break
        k.shooter.ready_at = 0.0
        c.solve()
        c.fire()
    assert ship.neutralized
    assert "TOUCHÉ" in c.log.toPlainText()
    assert k.credits < 60_000 + 7000                    # frais payés, prime encaissée plus tard
    k.advance(60.0)
    w.after_action()
    assert k.rank == 1


def test_ship_view_picking_selects_component():
    k, w = make(seed=3, quiet=True)
    k.next_attack = k.t + 10.0
    k.advance(60.0, interruptible=True)
    w.after_action()
    w.goto("combat")
    app.processEvents()
    v = w.combat.ship3d
    assert v.ship is not None and v._polys
    _, poly, idx = sorted(v._polys, key=lambda t: t[0])[0]
    c = poly.boundingRect().center()
    assert v.pick(c.x(), c.y()) is not None
    w.combat._ship3d_click(c.x(), c.y())
    assert k.target_sel is not None


@pytest.mark.slow
def test_strike_tab_search_plan_refine_fire_with_workers():
    k, w = make(seed=0, quiet=True)
    k.accept(1)
    k.set_focus(1)
    k.set_ammo("rod")
    from saturn_gauss.ballistics.projectile import mass_for_energy
    k.speed = 0.3 * 299792.458
    k.length = 0.05
    k.set_mass(mass_for_energy(5e12, k.speed))
    w.goto("strike")
    s = w.strike
    s.refresh()
    s.search()
    wait_idle(w)
    assert s._windows and s.t_win.rowCount() == len(s._windows)
    s.t_win.selectRow(0)
    s.load_plan()
    wait_idle(w)
    assert k.plan is not None
    s.refine()
    wait_idle(w)
    assert k.plan.refined and k.plan.residual_km < 5
    s.fire()
    wait_idle(w)
    assert "MISSION ACCOMPLIE" in s.result.toPlainText()
    assert s.view.trajectories and k.contract(1).state == "done"


@pytest.mark.slow
def test_strike_tab_fleet_and_asteroid_flows():
    k, w = make(seed=5, quiet=True)
    c = new_fleet_contract(k.system, k.t, 3, k.rng, k._new_id())
    k.board.append(c)
    k.accept(c.id)
    k.set_focus(c.id)
    k.set_ammo("antimatter")
    k.length = 0.6
    k.set_mass(20.0)
    k.speed = 0.7 * 299792.458
    w.goto("strike")
    s = w.strike
    s.search(); wait_idle(w)
    s.t_win.selectRow(0); s.load_plan(); wait_idle(w)
    s.refine(); wait_idle(w)
    s.fire(); wait_idle(w)
    assert c.state == "done"


def test_console_tab_runs_terminal_commands():
    k, w = make(quiet=True)
    w.goto("console")
    w.console.inp.setText("board")
    w.console.run()
    assert "Prise de contact" in w.console.out.toPlainText()
    w.console.inp.setText("goto 2150-01-05")
    w.console.run()
    assert k.t > 4 * 86400 * 0.9


def test_economy_tab_buy_and_repair():
    k, w = make(quiet=True)
    k.credits = 500_000
    w.goto("eco")
    e = w.economy
    e.t_up.selectRow(0)
    e.buy()
    assert k.upgrades.get("vmax") == 1
    st = k.shooters[2]
    st.take_damage(st.shield_max + 0.5 * st.hp_max)
    w.refresh_all()
    e.t_sh.selectRow(2)
    e.repair_sel()
    assert st.hp == st.hp_max
    e.t_l.selectRow(1)
    e.unlock()
    assert "rail" in k.unlocked


def test_save_load_through_window(tmp_path):
    k, w = make(quiet=True)
    k.credits = 4242.0
    p = str(tmp_path / "a.pkl")
    k.save(p)
    w.set_career(Career.load(p))
    assert w.k.credits == 4242.0
    assert "4 242" in w.l_credits.text()
