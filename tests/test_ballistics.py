import numpy as np
import pytest

from saturn_gauss.ballistics.lambert import lambert
from saturn_gauss.ballistics.projectile import Rod, radius_for_mass
from saturn_gauss.constants import DAY_S, GM_SUN
from saturn_gauss.guidance import asymptote_direction, launch_velocity_for_asymptote
from saturn_gauss.solarsystem.system import SolarSystem
from saturn_gauss.timeutils import format_date, parse_date, parse_duration

sysm = SolarSystem()


def test_rod_mass_energy_penetration():
    rod = Rod(10.0, 0.3)
    assert rod.mass_kg == pytest.approx(54_428, rel=1e-3)
    assert rod.energy_j(20.0) == pytest.approx(0.5 * rod.mass_kg * 4e8)
    assert rod.penetration_m(2800.0) == pytest.approx(10 * np.sqrt(19250 / 2800))
    assert radius_for_mass(rod.mass_kg, 10.0) == pytest.approx(0.3)
    with pytest.raises(ValueError):
        Rod(500.0, 0.3).validate()


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
