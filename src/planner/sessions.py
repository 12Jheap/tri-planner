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

# Longest sensible session (minutes) by race, discipline and kind. Sprint racing is
# ~1h15 total with a 5k run, so a 2h long run builds nothing but fatigue.
# Anything above the cap spills into extra Flex sessions instead.
CAPS: dict[str, dict[str, dict[str, int]]] = {
    "sprint": {
        "swim": {"technique": 60, "threshold": 60, "race_pace": 45, "endurance": 60},
        "bike": {"long": 120, "threshold": 75, "openers": 45, "endurance": 75},
        "run": {"long": 60, "threshold": 50, "openers": 30, "easy": 45},
    },
    "olympic": {
        "swim": {"technique": 70, "threshold": 75, "race_pace": 50, "endurance": 70},
        "bike": {"long": 150, "threshold": 90, "openers": 60, "endurance": 90},
        "run": {"long": 80, "threshold": 60, "openers": 35, "easy": 50},
    },
}


def cap_for(race: str, discipline: str, kind: str) -> int:
    return CAPS.get(race, CAPS["sprint"]).get(discipline, {}).get(kind, MAX_EASY)


# What to actually do, in plain words. Effort uses a 1–5 scale you can feel:
# 1–2 = can chat in full sentences, 3 = short phrases, 4 = a few words, 5 = flat out.
HOW: dict[str, str] = {
    "technique": "Drills plus easy swimming: catch, body position, breathing both sides. "
    "Rest as long as you need between lengths.",
    "endurance": "Steady and relaxed: you could hold a conversation.",
    "easy": "Genuinely easy, chatty pace. If in doubt, slow down.",
    "long": "Your longest of the week at an easy, steady effort. Take a drink; "
    "eat something if it's over 90 minutes.",
    "threshold": "After the warm-up: repeats at 'comfortably hard' (effort 4/5) with "
    "short easy recoveries. The .FIT file has the reps.",
    "race_pace": "Short efforts at race pace with full recovery. Stay sharp, not tired.",
    "openers": "Mostly easy with a few 30–60 second race-pace pickups. Finish feeling fresh.",
    "strength": "Bodyweight circuit: squats, lunges, glute bridges, plank, press-ups, "
    "calf raises. 2–3 rounds, stop before form breaks.",
    "substitute": "Stands in for a session you can't do right now. Keep it easy to steady.",
}


def how_to(s: Session) -> str:
    return HOW.get(s.kind, "Steady effort.")


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
        kind = "" if self.kind == self.discipline else f" {self.kind.replace('_', ' ')}"
        return f"{self.discipline.title()}{kind} {self.duration_min}' [{tag}]"

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
    """Concrete sessions for the week, each capped at a race-appropriate length."""
    sessions: list[Session] = []
    for disc in ("swim", "bike", "run"):
        total = targets.get(disc, 0)
        if total < MIN_SESSION:
            continue
        used = 0
        for kind, intensity, share, key in PLAN[disc][phase]:
            mins = min(_round5(total * share), cap_for(race, disc, kind))
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
        kind = REMAINDER_KIND[disc]
        for i, mins in enumerate(_split(total - used, cap_for(race, disc, kind)), start=1):
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
