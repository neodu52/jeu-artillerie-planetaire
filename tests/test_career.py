import numpy as np
import pytest

from saturn_gauss.ballistics.cannon import V_MAX_KMS
from saturn_gauss.ballistics.projectile import mass_for_energy
from saturn_gauss.career import Career, GameError
from saturn_gauss.combat import engagement as eng
from saturn_gauss.constants import C_KMS, DAY_S
from saturn_gauss.contracts import new_asteroid, new_fleet_contract
from saturn_gauss.economy import UPGRADES, upgrade_cost


def quiet(seed=0):
    k = Career(seed=seed)
    k.next_attack = k.next_offer = k.next_asteroid = 1e30
    return k


def test_initial_board_and_priority_cannot_be_refused():
    k = quiet()
    assert len([c for c in k.board if c.kind == "strike"]) == 6
    k.next_attack = k.t + 1.0
    k.advance(10.0, interruptible=True)
    pri = [c for c in k.board if c.priority]
    assert pri and pri[0].state == "active"
    with pytest.raises(GameError):
        k.refuse(pri[0].id)
    k.refuse(1)                                      # un contrat optionnel se refuse
    assert k.contract(1).state == "refused"


def test_wait_is_interrupted_by_priority_event():
    k = Career(seed=1)
    done = k.advance(10 * DAY_S, interruptible=True)
    assert done < 3 * DAY_S
    assert any("PRIORITAIRE" in m for m in k.pop_messages())


def test_unattended_attack_costs_money():
    k = Career(seed=2)
    k.advance(4 * DAY_S)
    assert k.credits < 60_000
    assert any(c.kind == "defense" and c.state == "failed" for c in k.board)


def test_limits_cost_and_funds():
    k = quiet()
    k.accept(1)
    k.speed = 500.0
    k.length, k.radius = 100.0, 2.0
    with pytest.raises(GameError):
        k.fire()                                      # énergie > capacité du canon
    k.length, k.radius, k.speed = 10.0, 0.3, V_MAX_KMS * 2
    with pytest.raises(GameError):
        k.check_launcher()
    k.use(1)
    with pytest.raises(GameError):
        k.set_ammo("antimatter")                      # les stations ne tirent pas de bombes
    k.speed = 0.3 * C_KMS
    with pytest.raises(GameError):
        k.check_launcher()                            # sous 50 % de c


def test_defense_duel_end_to_end():
    k = quiet(3)
    k.next_attack = k.t + 10.0
    k.advance(60.0, interruptible=True)
    k.pop_messages()
    ct = k.focus
    ship = ct.op.battle.ships[0]
    while np.linalg.norm(ship.state(k.t)[0]) > 6e5:
        k.advance(300.0)
    ri = [i for i, c in enumerate(ship.comps) if c.role == "reactor"][0]
    k.use(1)
    k.set_ammo("ferrite")
    k.set_mass(3.0)
    k.speed = 0.7 * C_KMS
    credits0 = k.credits
    for _ in range(12):
        if ship.neutralized:
            break
        k.target_sel = (ship.id, ri)
        k.solve_aim()
        k.shooter.ready_at = 0.0
        rep = k.fire()
        assert rep["kind"] == "ship"
    assert ship.neutralized
    k.advance(60.0)
    assert ct.state == "done" and k.rank == 1
    assert k.credits > credits0 - 5000                # la prime dépasse largement les frais


def test_station_damage_and_repair():
    k = quiet()
    st = k.shooters[2]
    st.take_damage(st.shield_max + st.hp_max * 0.4)
    assert st.damage_fraction == pytest.approx(0.4, abs=1e-6)
    cost = st.repair_cost
    assert cost == pytest.approx(0.4 * st.value, rel=1e-6)
    c0 = k.credits
    k.repair(2)
    assert k.credits == pytest.approx(c0 - cost) and st.hp == st.hp_max
    st.hp = 0
    k.use(2) if False else None
    k.use_idx = 2
    with pytest.raises(GameError):
        k.check_launcher()                            # hors service


def test_upgrades_and_unlocks():
    k = quiet()
    c0 = k.credits
    k.buy("cadence")
    assert k.upgrades["cadence"] == 1 and k.credits == pytest.approx(c0 - upgrade_cost("cadence", 0))
    k.credits = 0
    with pytest.raises(GameError):
        k.buy("vmax")
    k.credits = 1e7
    for _ in range(UPGRADES["cadence"].max_level):
        try:
            k.buy("cadence")
        except GameError:
            break
    with pytest.raises(GameError):
        k.buy("cadence")                              # niveau max
    k.buy("laser")
    k.refit(3, "laser")
    assert k.shooters[3].launcher == "laser"
    k.use(3)
    assert k.ammo == "beam"
    with pytest.raises(GameError):
        k.refit(0, "gauss")


def test_save_load_roundtrip(tmp_path):
    k = quiet(4)
    k.advance(5 * DAY_S)
    k.credits = 12345.0
    path = str(tmp_path / "s.pkl")
    k.save(path)
    k2 = Career.load(path)
    assert k2.t == k.t and k2.credits == 12345.0 and len(k2.board) == len(k.board)


def test_assist_disabled():
    k = Career(seed=0, assist=False)
    k.accept(1)
    with pytest.raises(GameError):
        k.find_windows()


# --------------------------------------------------------------------------- bout en bout (lents)
@pytest.mark.slow
def test_strike_with_player_speed_window_refine_fire():
    k = quiet()
    k.accept(1)                                       # Olympus Mons, 5e12 J
    k.use(0)
    k.set_ammo("rod")
    k.speed = 0.3 * C_KMS                             # la vitesse du joueur est respectée
    k.length = 0.05
    k.set_mass(mass_for_energy(5e12, k.speed))
    wins, _ = k.find_windows()
    assert wins
    assert all(abs(p.speed - k.speed) < 1e-6 * k.speed for p in wins)
    k.apply_plan(wins[0])
    new = k.refine(wins[0])
    assert new.residual_km < 5.0
    assert new.speed == pytest.approx(k.speed, rel=1e-12)
    k.apply_plan(new)
    rep = k.fire()
    assert rep["hit"] and rep["miss_km"] < 1200 and rep["energy_ok"] and rep["success"]
    assert k.contract(1).state == "done"


@pytest.mark.slow
def test_fleet_strike_with_bomb():
    k = quiet(5)
    c = new_fleet_contract(k.system, k.t, 3, k.rng, k._new_id())
    k.board.append(c)
    k.accept(c.id)
    k.use(0)
    k.set_ammo("antimatter")
    k.length = 0.6
    k.set_mass(20.0)
    k.speed = 0.7 * C_KMS
    wins, _ = k.find_windows()
    assert wins and all(p.t_arrival <= c.deadline for p in wins)
    k.apply_plan(wins[0])
    k.apply_plan(k.refine(wins[0]))
    rep = k.fire()
    assert rep["miss_km"] < 20.0
    assert c.state == "done" and rep["survivors"] == 0


@pytest.mark.slow
def test_asteroid_deflection():
    k = quiet(9)
    c = new_asteroid(k.system, k.t, k.rng, k._new_id())
    k.board.append(c)
    k.focus = c
    k.use(0)
    k.set_ammo("rod")
    k.length = 3.0
    k.set_mass(30.0)
    k.speed = 0.8 * C_KMS
    wins, _ = k.find_windows()
    assert wins
    k.apply_plan(wins[0])
    k.apply_plan(k.refine(wins[0]))
    d0 = c.op.miss_km
    for _ in range(8):
        k.shooter.ready_at = 0.0
        rep = k.fire()
        if c.state == "done":
            break
    assert c.op.miss_km > d0 * 100
    assert c.state == "done"
