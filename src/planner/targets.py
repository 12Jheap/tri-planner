"""Weekly load targets per discipline from simple coaching rules (US-002).

Deliberately rules-based and transparent. Splits are typical age-group
sprint/Olympic distributions: bike carries the most volume, swim gets more
share in sprint (it's a bigger fraction of race time), strength stays small.

Volume comes from the hours you *want* to train (`weekly_hours`), not from how
much free time you have: free time is only a ceiling. Having a free Saturday
doesn't mean you should train for all of it.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

Race = Literal["sprint", "olympic"]
Phase = Literal["base", "build", "taper"]

DISCIPLINES: tuple[str, ...] = ("swim", "bike", "run", "strength")

# Share of weekly training minutes per discipline.
SPLITS: dict[str, dict[str, float]] = {
    "sprint": {"swim": 0.22, "bike": 0.40, "run": 0.30, "strength": 0.08},
    "olympic": {"swim": 0.20, "bike": 0.45, "run": 0.28, "strength": 0.07},
}

# How much of the athlete's available time to fill, by phase. Never plan 100%:
# a plan that fills every free minute is a plan that won't be completed.
UTILISATION: dict[str, float] = {"base": 0.80, "build": 0.80, "taper": 0.50}

# Sensible base-phase weekly hours for a club-level athlete who sets no target.
DEFAULT_HOURS: dict[str, float] = {"sprint": 7.0, "olympic": 9.0}

# Volume relative to base hours: build adds a little, taper cuts ~40%.
PHASE_VOLUME: dict[str, float] = {"base": 1.0, "build": 1.1, "taper": 0.6}
RECOVERY_VOLUME = 0.7


def is_recovery_week(week: date, race_date: date | None) -> bool:
    """Every 4th week is lighter: 5, 9, 13… weeks out from the race (then taper)."""
    if race_date is None:
        return False
    weeks_out = (race_date - week).days // 7
    return weeks_out >= 5 and (weeks_out - 1) % 4 == 0


def phase_for(week: date, race_date: date | None) -> Phase:
    """Pick the phase from weeks to go: taper in the last 2 weeks, build for the
    8 weeks before that, base otherwise (and after the race)."""
    if race_date is None:
        return "base"
    days = (race_date - week).days
    if days < 0:
        return "base"
    if days < 14:
        return "taper"
    if days < 70:
        return "build"
    return "base"


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def weekly_targets(
    race: Race,
    phase: Phase,
    available_minutes: int,
    previous_week_minutes: int | None = None,
    ramp: float = 0.10,
    weekly_hours: float | None = None,
    recovery: bool = False,
) -> dict[str, int]:
    """Minutes per discipline for the coming week.

    Total = available time × phase utilisation, capped by:
    - what you did recently × (1 + ramp) when that's known (×0.6 in taper), else
    - what you train now (weekly_hours) × phase volume.
    Recovery weeks take 30% off. Free time is only ever a ceiling.
    """
    if race not in SPLITS:
        raise ValueError(f"unknown race '{race}' (sprint or olympic)")
    if phase not in UTILISATION:
        raise ValueError(f"unknown phase '{phase}' (base, build or taper)")
    if available_minutes < 0 or ramp < 0:
        raise ValueError("available_minutes and ramp must be non-negative")
    if weekly_hours is not None and weekly_hours <= 0:
        raise ValueError("weekly_hours must be positive")

    total = available_minutes * UTILISATION[phase]
    if previous_week_minutes is not None:
        # Progress from what you actually did: +ramp a week, or a cut for taper.
        grow = PHASE_VOLUME["taper"] if phase == "taper" else 1 + ramp
        total = min(total, previous_week_minutes * grow)
    elif weekly_hours is not None:
        total = min(total, weekly_hours * 60 * PHASE_VOLUME[phase])
    if recovery:
        total *= RECOVERY_VOLUME

    split = SPLITS[race]
    targets = {d: _round5(total * split[d]) for d in DISCIPLINES}
    if phase == "taper":
        targets["strength"] = 0
    # Rounding must never push the total over the cap.
    cap = int(total)
    while sum(targets.values()) > cap:
        biggest = max(targets, key=lambda d: targets[d])
        targets[biggest] -= 5
    return targets


def describe_targets(targets: dict[str, int]) -> str:
    """'swim 1h30 · bike 2h45 · …' for humans."""

    def hm(m: int) -> str:
        return f"{m // 60}h{m % 60:02d}" if m >= 60 else f"{m}'"

    parts = [f"{d} {hm(m)}" for d, m in targets.items() if m]
    return " · ".join(parts) + f"  (total {hm(sum(targets.values()))})"
