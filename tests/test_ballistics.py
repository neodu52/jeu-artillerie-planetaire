import numpy as np
import pytest

from saturn_gauss.ballistics.cannon import add_velocity
from saturn_gauss.ballistics.kepler2b import propagate
from saturn_gauss.ballistics.lambert import lambert
from saturn_gauss.ballistics.projectile import (Rod, gamma_minus_1, mass_for_energy, radius_for_mass,
                                                speed_for_energy, speed_for_gamma_minus_1)
from saturn_gauss.constants import C_KMS, DAY_S, GM_SUN
from saturn_gauss.guidance import asymptote_direction, launch_velocity_for_asymptote
from saturn_gauss.solarsystem.system import SolarSystem
from saturn_gauss.timeutils import format_date, parse_date, parse_duration

sysm = SolarSystem()


def test_rod_mass_energy_penetration():
    rod = Rod(10.0, 0.3)
    assert rod.mass_kg == pytest.approx(54_428, rel=1e-3)
    assert rod.energy_j(20.0) == pytest.approx(0.5 * rod.mass_kg * 4e8, rel=1e-6)   # limite newtonienne
    assert rod.penetration_m(2800.0) == pytest.approx(10 * np.sqrt(19250 / 2800))
    assert radius_for_mass(rod.mass_kg, 10.0) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        Rod(500.0, 0.3).validate()


def test_relativistic_energy():
    assert gamma_minus_1(0.6 * C_KMS) == pytest.approx(0.25)            # gamma = 1.25
    assert gamma_minus_1(0.8 * C_KMS) == pytest.approx(2 / 3)
    for beta in (1e-6, 0.1, 0.5, 0.9, 0.999999):
        x = gamma_minus_1(beta * C_KMS)
        assert speed_for_gamma_minus_1(x) == pytest.approx(beta * C_KMS, rel=1e-9)
    with pytest.raises(ValueError):
        gamma_minus_1(C_KMS)
    m = mass_for_energy(5e12, 0.3 * C_KMS)
    assert Rod(1, 1).energy_j(1) > 0
    assert speed_for_energy(5e12, m) == pytest.approx(0.3 * C_KMS, rel=1e-9)


def test_relativistic_velocity_addition():
    V = np.array([20.0, 0, 0])
    u = np.array([0.9 * C_KMS, 0, 0])
    exp = (0.9 * C_KMS + 20) / (1 + 0.9 * 20 / C_KMS)
    assert add_velocity(V, u)[0] == pytest.approx(exp, rel=1e-12)
    perp = add_velocity(V, np.array([0, 0.9 * C_KMS, 0]))
    assert np.linalg.norm(perp) < C_KMS
    assert np.allclose(add_velocity(np.zeros(3), u), u)
    assert np.linalg.norm(add_velocity(np.array([100.0, 0, 0]), np.array([C_KMS * (1 - 1e-9), 0, 0]))) < C_KMS


@pytest.mark.parametrize("tof_days", [120, 250, 400, 700])
def test_lambert_conserves_two_body_invariants(tof_days):
    t0 = 1e9
    r1 = sysm.position("Terre", t0)
    r2 = sysm.position("Mars", t0 + tof_days * DAY_S)
    v1, v2 = lambert(r1, r2, tof_days * DAY_S, GM_SUN)
    e1 = 0.5 * v1 @ v1 - GM_SUN / np.linalg.norm(r1)
    e2 = 0.5 * v2 @ v2 - GM_SUN / np.linalg.norm(r2)
    assert e1 == pytest.approx(e2, rel=1e-8)
    assert np.allclose(np.cross(r1, v1), np.cross(r2, v2), rtol=1e-8)


def test_kepler_propagation_roundtrip_and_energy():
    mu = 3.79e7
    rng = np.random.default_rng(2)
    for _ in range(30):
        r = rng.normal(size=3)
        r *= rng.uniform(2e5, 2e6) / np.linalg.norm(r)
        v = rng.normal(size=3)
        v *= rng.uniform(5, 60) / np.linalg.norm(v)
        dt = rng.uniform(-8e4, 8e4)
        r2, v2 = propagate(r, v, dt, mu)
        e0 = 0.5 * v @ v - mu / np.linalg.norm(r)
        e1 = 0.5 * v2 @ v2 - mu / np.linalg.norm(r2)
        assert e1 == pytest.approx(e0, rel=1e-9)
        r3, _ = propagate(r2, v2, -dt, mu)
        assert np.allclose(r3, r, rtol=1e-8, atol=1e-4)


def test_hyperbolic_launch_matches_asymptote():
    rng = np.random.default_rng(3)
    mu = 3.79e7
    found = 0
    for _ in range(100):
        r = rng.normal(size=3)
        r *= 3e5 / np.linalg.norm(r)
        u = rng.normal(size=3)
        u /= np.linalg.norm(u)
        vinf = rng.uniform(2, 12)
        v = launch_velocity_for_asymptote(r, mu, vinf * u, 6e4)
        if v is None:
            continue
        found += 1
        assert np.allclose(asymptote_direction(r, v, mu), u, atol=1e-6)
        assert 0.5 * v @ v - mu / np.linalg.norm(r) == pytest.approx(0.5 * vinf ** 2, rel=1e-8)
    assert found > 50


def test_time_helpers():
    assert parse_duration("3d") == 3 * DAY_S
    assert parse_duration("12h") == 43_200
    assert parse_duration("1,5d") == 1.5 * DAY_S
    with pytest.raises(ValueError):
        parse_duration("abc")
    assert format_date(parse_date("2155-03-04 12:30")) == "2155-03-04 12:30"
