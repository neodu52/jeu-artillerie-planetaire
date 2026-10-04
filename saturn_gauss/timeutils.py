"""Conversions entre dates calendaires et temps de simulation."""
import re
from datetime import datetime, timedelta

from .constants import DAY_S, J2000


def to_datetime(t: float) -> datetime:
    return J2000 + timedelta(seconds=float(t))


def from_datetime(dt: datetime) -> float:
    return (dt - J2000).total_seconds()


def format_date(t: float) -> str:
    return to_datetime(t).strftime("%Y-%m-%d %H:%M")


def parse_duration(text: str) -> float:
    """'3d', '12h', '45m', '2y', '1.5' (jours par défaut) -> secondes."""
    m = re.fullmatch(r"\s*(-?\d+(?:[.,]\d+)?)\s*([smhdjy]?)\s*", text.lower())
    if not m:
        raise ValueError(f"durée invalide : {text!r} (exemples : 3d, 12h, 45m, 2y)")
    value = float(m.group(1).replace(",", "."))
    unit = m.group(2) or "d"
    factor = {"s": 1.0, "m": 60.0, "h": 3600.0, "d": DAY_S, "j": DAY_S, "y": 365.25 * DAY_S}[unit]
    return value * factor


def parse_date(text: str) -> float:
    """'2155-03-04' ou '2155-03-04 12:30' -> temps de simulation."""
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return from_datetime(datetime.strptime(text.strip(), fmt))
        except ValueError:
            continue
    raise ValueError(f"date invalide : {text!r} (format AAAA-MM-JJ [HH:MM])")
