"""Session library: turns weekly targets into concrete sessions (US-002).

Every session says what it needs as *any-of* facility groups, so indoor kit
substitutes for outdoor automatically: a bike session needs a wattbike OR a road
bike, a run needs outdoors OR a treadmill.
"""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field

from planner.config import Facility, Location
from planner.targets import Phase, Race

Discipline = Literal["swim", "bike", "run", "strength"]

# Each inner list is "any one of these"; all groups must be satisfied.
REQUIRES: dict[str, list[list[Facility]]] = {
    "swim": [[Facility.POOL, Facility.OPEN_WATER]],
    "bike": [[Facility.WATTBIKE, Facility.ROAD_BIKE]],
    "run": [[Facility.OUTDOOR_RUN, Facility.TREADMILL]],
    "strength": [],  # bodyweight works anywhere
}

MIN_SESSION = 20  # minutes; shorter fragments are dropped
MAX_EASY = 75  # split easy volume into sessions no longer than this


class Session(BaseModel):
    id: str
    discipline: Discipline
    kind: str  # technique, endurance, long, threshold, easy, openers, race_pace, strength
    duration_min: int = Field(gt=0)
    intensity: int = Field(ge=1, le=5)
    requires: list[list[Facility]]
    key: bool  # Key sessions are protected; Flex sessions move or drop first
    value: float = 0.0

    def model_post_init(self, _ctx: object) -> None:
        if self.value == 0.0:
            self.value = session_value(self.duration_min, self.intensity, self.key)

    @property
    def hard(self) -> bool:
        return self.intensity >= 4

    @property
    def label(self) -> str:
        tag = "KEY" if self.key else "flex"
        return f"{self.discipline.title()} {self.kind.replace('_', ' ')} {self.duration_min}' [{tag}]"

    def fits(self, location: Location, day: str, start: time, end: time) -> bool:
        """True if every facility requirement can be met at this place and time."""
        return all(any(location.has(f, day, start, end) for f in group) for group in self.requires)


def session_value(duration_min: int, intensity: int, key: bool) -> float:
    """Training value: longer and harder is worth more; Key sessions weighted 1.5×."""
    return round(duration_min / 60 * (1 + 0.25 * (intensity - 1)) * (1.5 if key else 1.0), 3)


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


def _split(minutes: int, max_len: int = MAX_EASY) -> list[int]:
    if minutes < MIN_SESSION:
        return []
    n = -(-minutes // max_len)
    parts = [_round5(minutes / n)] * n
    return [p for p in parts if p >= MIN_SESSION]


# (kind, intensity, share of the discipline's minutes, key) per phase.
# The remainder after these becomes Flex easy/endurance sessions.
PLAN: dict[str, dict[str, list[tuple[str, int, float, bool]]]] = {
    "swim": {
        "base": [("technique", 2, 0.40, True)],
        "build": [("threshold", 4, 0.40, True)],
        "taper": [("race_pace", 3, 0.50, True)],
    },
    "bike": {
        "base": [("long", 2, 0.45, True)],
        "build": [("long", 2, 0.40, True), ("threshold", 4, 0.25, True)],
        "taper": [("openers", 3, 0.40, True)],
    },
    "run": {
        "base": [("long", 2, 0.40, True)],
        "build": [("long", 2, 0.35, True), ("threshold", 4, 0.25, True)],
        "taper": [("openers", 3, 0.40, True)],
    },
}
REMAINDER_KIND = {"swim": "endurance", "bike": "endurance", "run": "easy"}


def build_week_sessions(targets: dict[str, int], race: Race, phase: Phase) -> list[Session]:
    """Concrete sessions for the week. `race` is kept for future race-specific tweaks."""
    sessions: list[Session] = []
    for disc in ("swim", "bike", "run"):
        total = targets.get(disc, 0)
        if total < MIN_SESSION:
            continue
        used = 0
        for kind, intensity, share, key in PLAN[disc][phase]:
            mins = _round5(total * share)
            if mins < MIN_SESSION:
                continue
            sessions.append(
                Session(
                    id=f"{disc}-{kind}",
                    discipline=disc,  # type: ignore[arg-type]
                    kind=kind,
                    duration_min=mins,
                    intensity=intensity,
                    requires=REQUIRES[disc],
                    key=key,
                )
            )
            used += mins
        max_len = 60 if disc == "swim" else MAX_EASY
        for i, mins in enumerate(_split(total - used, max_len), start=1):
            kind = REMAINDER_KIND[disc]
            sessions.append(
                Session(
                    id=f"{disc}-{kind}-{i}",
                    discipline=disc,  # type: ignore[arg-type]
                    kind=kind,
                    duration_min=mins,
                    intensity=2 if disc != "run" else 1,
                    requires=REQUIRES[disc],
                    key=False,
                )
            )
    strength = min(targets.get("strength", 0), 45)
    if strength >= MIN_SESSION:
        sessions.append(
            Session(
                id="strength-1",
                discipline="strength",
                kind="strength",
                duration_min=_round5(strength),
                intensity=2,
                requires=REQUIRES["strength"],
                key=False,
            )
        )
    return sessions
