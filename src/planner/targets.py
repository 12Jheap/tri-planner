"""Weekly load targets per discipline from simple coaching rules (US-002).

Deliberately rules-based and transparent. Splits are typical age-group
sprint/Olympic distributions: bike carries the most volume, swim gets more
share in sprint (it's a bigger fraction of race time), strength stays small.
"""

from __future__ import annotations

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


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def weekly_targets(
    race: Race,
    phase: Phase,
    available_minutes: int,
    previous_week_minutes: int | None = None,
    ramp: float = 0.10,
) -> dict[str, int]:
    """Minutes per discipline for the coming week.

    Total = available time × phase utilisation, capped at last week's total ×
    (1 + ramp) when last week is known (default: +10% week on week).
    """
    if race not in SPLITS:
        raise ValueError(f"unknown race '{race}' (sprint or olympic)")
    if phase not in UTILISATION:
        raise ValueError(f"unknown phase '{phase}' (base, build or taper)")
    if available_minutes < 0 or ramp < 0:
        raise ValueError("available_minutes and ramp must be non-negative")

    total = available_minutes * UTILISATION[phase]
    if previous_week_minutes is not None:
        total = min(total, previous_week_minutes * (1 + ramp))

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
