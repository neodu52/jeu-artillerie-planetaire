import numpy as np
import pytest

from saturn_gauss.constants import AU_KM, DAY_S
from saturn_gauss.solarsystem.rotation import (body_to_ecliptic, great_circle_km, latlon_from_vector,
                                               surface_unit_vector)
from saturn_gauss.solarsystem.system import SolarSystem

sysm = SolarSystem()


def test_earth_distance_at_j2000():
    r = np.linalg.norm(sysm.position("Terre", 0.0)) / AU_KM
    assert 0.98 < r < 1.02


@pytest.mark.parametrize("name", [b.name for b in sysm.bodies[1:]])
def test_orbit_radius_within_apsides(name):
    b = sysm.get(name)
    a, e = b.elements[0], b.elements[2]
    for t in np.linspace(0, 5e9, 25):
        r = np.linalg.norm(sysm.position(name, t)) / AU_KM
        assert a * (1 - e) * 0.995 <= r <= a * (1 + e) * 1.005


def test_velocity_matches_position_derivative():
    t, h = 3e9, 50.0
    _, v = sysm.states(t)
    num = (sysm.positions(t + h) - sysm.positions(t - h)) / (2 * h)
    assert np.abs(num - v).max() < 0.02          # km/s


def test_orbits_are_three_dimensional():
    ts = np.linspace(0, 88 * DAY_S, 50)
    z = [sysm.position("Mercure", t)[2] for t in ts]
    assert max(z) - min(z) > 1e7                  # Mercure : i = 7°


def test_mars_returns_after_one_period():
    t0 = 1e9
    p0 = sysm.position("Mars", t0)
    p1 = sysm.position("Mars", t0 + 686.98 * DAY_S)
    assert np.linalg.norm(p1 - p0) < 0.02 * np.linalg.norm(p0)


def test_rotation_periods_and_direction():
    for name, hours in (("Terre", 23.934), ("Mars", 24.623), ("Saturne", 10.656)):
        b = sysm.get(name)
        assert abs(abs(b.rotation_period_h) - hours) < 0.01
        M0 = body_to_ecliptic(b, 0.0)
        M1 = body_to_ecliptic(b, abs(b.rotation_period_h) * 3600.0)
        assert np.allclose(M0, M1, atol=1e-4)
    assert sysm.get("Vénus").rotation_period_h < 0       # rétrograde
    assert sysm.get("Uranus").rotation_period_h < 0


def test_surface_vector_roundtrip():
    b = sysm.get("Mars")
    for lat, lon in ((18.65, -133.8), (-42.4, 70.5), (89.0, 10.0)):
        n = surface_unit_vector(b, 1.234e9, lat, lon)
        la2, lo2 = latlon_from_vector(b, 1.234e9, n)
        assert abs(la2 - lat) < 1e-9 and abs(((lo2 - lon + 180) % 360) - 180) < 1e-9


def test_surface_point_moves_with_rotation():
    b = sysm.get("Terre")
    n0 = surface_unit_vector(b, 0.0, 10.0, 20.0)
    n1 = surface_unit_vector(b, 6 * 3600.0, 10.0, 20.0)
    assert np.degrees(np.arccos(np.clip(n0 @ n1, -1, 1))) > 10


def test_great_circle():
    assert abs(great_circle_km(0, 0, 0, 90, 1000.0) - 1000 * np.pi / 2) < 1e-6
