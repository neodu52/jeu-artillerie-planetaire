"""Calculatrice de visée (mêmes variables que la commande « calc » du terminal)."""
import math

import numpy as np

from ..constants import C_KMS
from ..contracts import DefenseOp


def calc_env(k):
    env = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "asin", "acos", "atan", "atan2",
                                          "degrees", "radians", "pi", "log", "exp", "hypot")}
    env.update(norm=lambda v: float(np.linalg.norm(v)), dot=lambda a, b: float(np.dot(a, b)),
               cross=lambda a, b: np.cross(a, b), vec=lambda *a: np.array(a, float), c=C_KMS, vp=k.speed)
    if k.target_sel and k.focus and isinstance(k.focus.op, DefenseOp):
        ship = next((s for s in k.focus.op.battle.ships if s.id == k.target_sel[0]), None)
        if ship is not None:
            origin, _ = k.shooter.rel_state(k.t)
            pos, vel = ship.state(k.t)
            cen = pos + ship.axes(vel) @ (ship.comps[k.target_sel[1]].center / 1000.0)
            vp = C_KMS if k.launcher_of().kind == "beam" else k.speed
            d = float(np.linalg.norm(cen - origin))
            env.update(P=cen, V=vel, S=origin, d=d, vp=vp, tau=d / vp)
    return env


def evaluate(k, text):
    res = eval(text, {"__builtins__": {}}, calc_env(k))        # noqa: S307  (jeu local, environnement restreint)
    if hasattr(res, "__len__"):
        return np.array2string(np.asarray(res), precision=9)
    return f"{res:.12g}"
