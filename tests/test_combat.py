import numpy as np
import pytest

from saturn_gauss.ballistics.cannon import direction_vector
from saturn_gauss.combat import engagement as eng
from saturn_gauss.combat.ammo import AMMO, blast_energy_on_ship, penetration_m
from saturn_gauss.combat.battle import eta_to_objective, spawn_wave
from saturn_gauss.combat.damage import apply_blast, apply_hit
from saturn_gauss.combat.geometry import ray_box
from saturn_gauss.combat.launchers import LAUNCHERS, effective
from saturn_gauss.combat.ships import CLASSES, Ship, make_ship
from saturn_gauss.combat.stations import default_stations
from saturn_gauss.constants import C_KMS

MU = 3.79e7


def _ship(cls="destroyer"):
    return make_ship(cls, 1, "test", [1e6, 0, 0], [-30, 0, 0], 0.0, MU)


def test_ray_box_basic():
    A = np.eye(3)
    hit = ray_box(np.array([-10.0, 0, 0]), np.array([1.0, 0, 0]), np.zeros(3), A, np.array([1.0, 1, 1]))
    assert hit == pytest.approx((9.0, 11.0))
    assert ray_box(np.array([-10.0, 5, 0]), np.array([1.0, 0, 0]), np.zeros(3), A, np.array([1.0, 1, 1])) is None


def test_every_class_has_critical_reactor_and_bridge():
    for key in CLASSES:
        s = _ship(key)
        roles = {c.role for c in s.comps}
        assert {"hull", "bridge", "reactor", "shield"} <= roles
        assert any(c.critical for c in s.comps)
        assert s.status == "actif"


def test_solve_aim_hits_the_component_and_small_error_misses():
    ship = _ship()
    st = default_stations(MU)[2]
    t = 0.0
    origin, _ = st.rel_state(t)
    vp = 0.7 * C_KMS
    for idx in (1, 0):                                   # pont puis coque
        lon, lat, tau, dist = eng.solve_aim(origin, ship, idx, t, vp)
        hit = eng.locate_hit(origin, direction_vector(lon, lat), vp, [ship], t)
        assert hit is not None and hit[0] != "saturne"
        assert hit[2] == idx or ship.comps[hit[2]].role in ("bridge", "hull", "shield")   # peut être masqué
    ok, _ = eng.visibility(origin, ship, 1, t, vp)
    if ok:
        lon, lat, *_ = eng.solve_aim(origin, ship, 1, t, vp)
        d_bad = direction_vector(lon + 1e-3, lat)                  # 1e-3 deg = ~17 km à 1e6 km
        hit = eng.locate_hit(origin, d_bad, vp, [ship], t)
        assert hit is None
        rep = eng.miss_report(origin, d_bad, ship, 1, t, vp)
        assert rep["distance_m"] > 1000


def test_lead_matters():
    """Viser le point actuel (sans anticiper le mouvement) rate un vaisseau qui file à 30 km/s."""
    ship = make_ship("destroyer", 1, "t", [1e6, 0, 0], [0, 30, 0], 0.0, MU)   # file perpendiculairement à la visée
    origin, _ = default_stations(MU)[0].rel_state(0.0)
    vp = 0.5 * C_KMS
    pos, v = ship.state(0.0)
    cen = pos + Ship.axes(v) @ (ship.comps[0].center / 1000)
    naive = (cen - origin) / np.linalg.norm(cen - origin)
    assert eng.locate_hit(origin, naive, vp, [ship], 0.0) is None
    lon, lat, *_ = eng.solve_aim(origin, ship, 0, 0.0, vp)
    assert eng.locate_hit(origin, direction_vector(lon, lat), vp, [ship], 0.0) is not None


def test_shield_absorbs_then_hull():
    ship = _ship("corvette")
    rod = AMMO["rod"]
    r = apply_hit(ship, 0, rod, 1e15, 0.3, 1.0)           # petite énergie : tout absorbé
    assert r["shield_absorbed"] == 1.0 and ship.comps[0].hp == ship.comps[0].hp_max
    r = apply_hit(ship, 0, rod, 1e18, 1.0, 1.0)           # énorme : bouclier à zéro, coque touchée
    assert ship.shield == 0 and ship.comps[0].hp < ship.comps[0].hp_max


def test_ammo_roles_ferrite_vs_shield_and_ap_vs_hull():
    E, L = 3e16, 0.3
    s1, s2 = _ship(), _ship()
    apply_hit(s1, 0, AMMO["ferrite"], E, L, 1.0)
    apply_hit(s2, 0, AMMO["rod"], E, L, 1.0)
    assert s1.shield < s2.shield                          # la ferrite use plus le bouclier
    a, b = _ship(), _ship()
    a.shield = b.shield = 0.0
    ri = [i for i, c in enumerate(a.comps) if c.role == "reactor"][0]
    apply_hit(a, ri, AMMO["ap_he"], E, L, 1.0)
    apply_hit(b, ri, AMMO["ferrite"], E, L, 1.0)
    assert a.comps[ri].hp < b.comps[ri].hp                # perforant-explosif > ferrite sur la coque
    assert penetration_m(AMMO["ap_he"], L) > penetration_m(AMMO["rod"], L) > penetration_m(AMMO["ferrite"], L)
    assert penetration_m(AMMO["beam"], 1.0) == 0


def test_destroying_reactor_destroys_ship_and_bridge_disables():
    s = _ship()
    s.shield = 0.0
    ri = [i for i, c in enumerate(s.comps) if c.role == "reactor"][0]
    s.comps[ri].hp = 0
    assert s.destroyed and s.bounty == s.spec.value
    s2 = _ship()
    bi = [i for i, c in enumerate(s2.comps) if c.role == "bridge"][0]
    s2.comps[bi].hp = 0
    assert s2.disabled and not s2.destroyed and s2.firepower_j == 0 and s2.bounty == pytest.approx(0.7 * s2.spec.value)


def test_gas_captures_crew():
    s = _ship("transport")
    s.shield = 0.0
    for _ in range(6):
        apply_hit(s, 0, AMMO["gas"], 1e15, 0.5, 6.0)
    assert s.crew < 0.2 and s.neutralized and s.bounty == pytest.approx(1.5 * s.spec.value)


def test_blast_falls_off_with_distance():
    a = AMMO["antimatter"]
    Y = 1e18
    assert blast_energy_on_ship(a, Y, 1.0) == pytest.approx(blast_energy_on_ship(a, Y, 5.0))   # plateau
    assert blast_energy_on_ship(a, Y, 200.0) < 0.2 * blast_energy_on_ship(a, Y, 1.0)
    s = _ship("corvette")
    apply_blast(s, 1e19)
    assert s.destroyed or s.neutralized


def test_launcher_limits_and_upgrades():
    g = LAUNCHERS["gauss"]
    assert g.v_min_kms == pytest.approx(0.5 * C_KMS) and g.v_max_kms == pytest.approx(0.95 * C_KMS)
    up = effective(g, {"vmax": 2, "masse": 1, "cadence": 1})
    assert up.v_max_kms > g.v_max_kms and up.max_mass_kg == pytest.approx(1.5 * g.max_mass_kg) and up.reload_s < g.reload_s
    assert "nuke" in LAUNCHERS["canon"].ammo and "nuke" not in g.ammo


def test_wave_arrives_and_geometry_is_deterministic():
    rng = np.random.default_rng(11)
    b = spawn_wave(5, 0.0, rng, MU)
    t = eta_to_objective(b.ships, 0.0, b.objective_km)
    assert 1 * 3600 < t < 40 * 3600
    assert np.linalg.norm(b.ships[0].state(t)[0]) <= b.objective_km * 1.01
