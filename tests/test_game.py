import numpy as np
import pytest

from saturn_gauss.game.missions import CAMPAIGN
from saturn_gauss.game.state import Game


def test_limits_are_enforced():
    g = Game()
    g.speed = 500.0
    with pytest.raises(ValueError):
        g.fire()
    g.speed, g.rod.radius_m = 90.0, 2.0
    g.rod.length_m = 100.0
    with pytest.raises(ValueError):                  # énergie > capacité du canon
        g.fire()


def test_projectile_gravity_is_bound_to_saturn_when_slow():
    g = Game()
    g.speed = 1.0
    rep = g.fire()                                   # reste lié au système, aucun impact
    assert rep.result.outcome in ("timeout", "impact")
    assert not rep.success


def test_shot_is_deterministic():
    g = Game()
    a = g.fire().result.final_pos
    b = g.fire().result.final_pos
    assert np.allclose(a, b)


@pytest.mark.slow
@pytest.mark.parametrize("idx", range(len(CAMPAIGN)))
def test_every_mission_is_solvable_with_guidance(idx):
    g = Game()
    g.select_mission(idx)
    wins = g.find_windows()
    assert wins, "aucune fenêtre trouvée"
    plan = g.refine(wins[0])
    assert plan.residual_km < 5.0
    g.apply_plan(plan, keep_rod_length=False)
    rep = g.fire()
    assert rep.hit_target_body
    assert rep.miss_km < CAMPAIGN[idx].tolerance_km
    assert rep.success
