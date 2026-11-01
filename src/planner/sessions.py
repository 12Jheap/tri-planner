"""Session library: which sessions make a good week, and how long each should be (US-002).

Every session says what it needs as *any-of* facility groups, so indoor kit
substitutes for outdoor automatically: a bike session needs a wattbike OR a road
bike, a run needs outdoors OR a treadmill. A brick needs both, in the same place.

Each phase has a menu: Key sessions (the ones that make you faster, protected when
the week changes) and Flex sessions (aerobic volume, the first to move or drop).
Base builds the engine with one quality session per sport (tempo / sweet spot /
CSS); build adds threshold and VO2 work and bricks; taper keeps the intensity and
cuts the volume. Every 4th week before a race is a lighter recovery week.

Each session has an ideal length, a minimum (to squeeze into a short slot) and a
maximum (so filling a long slot never turns into a 3-hour run). What happens
*inside* a session (warm-up, intervals, targets) lives in workouts.py.
"""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, Field

from planner.config import Facility, Location
from planner.targets import Phase, Race

Discipline = Literal["swim", "bike", "run", "strength"]

BIKE_KIT = [Facility.WATTBIKE, Facility.ROAD_BIKE]
RUN_KIT = [Facility.OUTDOOR_RUN, Facility.TREADMILL]
SWIM_KIT = [Facility.POOL, Facility.OPEN_WATER]

# Each inner list is "any one of these"; all groups must be satisfied.
REQUIRES: dict[str, list[list[Facility]]] = {
    "swim": [SWIM_KIT],
    "bike": [BIKE_KIT],
    "run": [RUN_KIT],
    "strength": [],  # bodyweight works anywhere
}
BRICK_REQUIRES = [BIKE_KIT, RUN_KIT]

MIN_SESSION = 20  # minutes; shorter fragments are dropped
MAX_EASY = 75

# Longest sensible session (minutes) by race, discipline and kind. Sprint racing is
# ~1h15 total with a 5k run, so a 2h long run builds nothing but fatigue.
CAPS: dict[str, dict[str, dict[str, int]]] = {
    "sprint": {
        "swim": {"technique": 60, "endurance": 60, "css": 60, "speed": 45, "race_pace": 40},
        "bike": {"long": 120, "endurance": 75, "tempo": 75, "threshold": 75, "vo2": 60,
                 "brick": 75, "openers": 45},
        "run": {"long": 60, "easy": 45, "easy_strides": 45, "tempo": 50, "threshold": 50,
                "vo2": 45, "openers": 30},
    },
    "half": {
        "swim": {"technique": 75, "endurance": 80, "css": 75, "speed": 60, "race_pace": 50},
        "bike": {"long": 240, "endurance": 120, "tempo": 120, "threshold": 90, "vo2": 75,
                 "brick": 150, "openers": 60},
        "run": {"long": 120, "easy": 60, "easy_strides": 60, "tempo": 75, "threshold": 60,
                "vo2": 50, "openers": 35},
    },
    "olympic": {
        "swim": {"technique": 70, "endurance": 75, "css": 70, "speed": 55, "race_pace": 45},
        "bike": {"long": 150, "endurance": 90, "tempo": 90, "threshold": 90, "vo2": 75,
                 "brick": 90, "openers": 60},
        "run": {"long": 80, "easy": 50, "easy_strides": 50, "tempo": 60, "threshold": 60,
                "vo2": 50, "openers": 35},
    },
}


def cap_for(race: str, discipline: str, kind: str) -> int:
    if discipline == "strength":
        return 45
    return CAPS.get(race, CAPS["sprint"]).get(discipline, {}).get(kind, MAX_EASY)


TITLES: dict[tuple[str, str], str] = {
    ("swim", "technique"): "Technique swim", ("swim", "endurance"): "Endurance swim",
    ("swim", "css"): "CSS swim", ("swim", "speed"): "Speed swim",
    ("swim", "race_pace"): "Race-pace swim",
    ("bike", "long"): "Long ride", ("bike", "endurance"): "Endurance ride",
    ("bike", "tempo"): "Sweet-spot ride", ("bike", "threshold"): "Threshold ride",
    ("bike", "vo2"): "VO2 ride", ("bike", "brick"): "Brick: ride + run",
    ("bike", "openers"): "Openers ride",
    ("run", "long"): "Long run", ("run", "easy"): "Easy run",
    ("run", "easy_strides"): "Easy run + strides", ("run", "tempo"): "Tempo run",
    ("run", "threshold"): "Threshold run", ("run", "vo2"): "VO2 run",
    ("run", "openers"): "Openers run",
    ("strength", "strength"): "Strength",
}

# Why you're doing it, in one or two sentences.
PURPOSE: dict[str, str] = {
    "technique": "Drills and relaxed swimming to make every length cheaper. Efficiency is "
    "free speed in the water.",
    "endurance": "Aerobic base: lots of time at an easy, steady effort builds the engine "
    "everything else runs on.",
    "easy": "Easy volume that adds fitness without adding fatigue. If in doubt, slow down.",
    "easy_strides": "Easy aerobic running, then short relaxed strides to keep your legs "
    "quick without making it a hard day.",
    "long": "Your longest session of the sport. Steady, never hard: it builds the "
    "endurance to hold pace late in a race.",
    "css": "Repeats at your critical swim speed: the pace you could hold for about 1500m. "
    "The core of swim fitness.",
    "speed": "Short fast repeats with full rest. Sharpens your stroke at race speed.",
    "race_pace": "Short efforts at race pace to stay sharp while the volume drops.",
    "tempo": "Sustained 'comfortably hard' work. Raises how fast you can go aerobically "
    "and teaches pacing.",
    "threshold": "Repeats at the effort you could hold for about an hour. For sprint and "
    "Olympic racing this is the engine that matters most.",
    "vo2": "Hard 3-minute repeats near your maximum aerobic power. Lifts the ceiling. Go "
    "in fresh.",
    "brick": "A ride straight into a short run, so your legs learn to run off the bike. "
    "This is what race day feels like.",
    "openers": "Short, sharp efforts that wake the legs up before racing. You should "
    "finish feeling fresh, not tired.",
    "strength": "Bodyweight strength and stability. Makes you more robust and helps you "
    "hold form when tired.",
    "substitute": "Stands in for a session you can't do right now. Keep it easy to steady.",
}


class Session(BaseModel):
    id: str
    discipline: Discipline
    kind: str
    duration_min: int = Field(gt=0)
    intensity: int = Field(ge=1, le=5)
    requires: list[list[Facility]]
    key: bool  # Key sessions are protected; Flex sessions move or drop first
    value: float = 0.0
    min_min: int | None = None  # shortest useful version
    max_min: int | None = None  # longest sensible version (filling a long slot)
    race: str = ""  # what it's for: shapes the workout (a half's long ride ≠ a sprint's)
    phase: str = ""

    def model_post_init(self, _ctx: object) -> None:
        if self.value == 0.0:
            self.value = session_value(self.duration_min, self.intensity, self.key)

    @property
    def hard(self) -> bool:
        return self.intensity >= 4

    @property
    def title(self) -> str:
        if self.kind == "substitute":
            return f"{self.discipline.title()} (substitute)"
        return TITLES.get((self.discipline, self.kind), f"{self.discipline.title()} {self.kind}")

    @property
    def label(self) -> str:
        return f"{self.title} · {self.duration_min} min{' · key' if self.key else ''}"

    @property
    def extendable(self) -> bool:
        """Aerobic sessions can grow to fill a slot; interval sessions keep their shape."""
        return self.kind in ("long", "endurance", "easy", "easy_strides", "technique",
                             "substitute")

    def fits(self, location: Location, day: str, start: time, end: time) -> bool:
        """True if every facility requirement can be met at this place and time."""
        return all(any(location.has(f, day, start, end) for f in group) for group in self.requires)

    def resized(self, minutes: int) -> Session:
        data = self.model_dump(exclude={"value"})
        data["duration_min"] = minutes
        return Session(**data)


def how_to(s: Session) -> str:
    """Why this session is in your week."""
    return PURPOSE.get(s.kind, PURPOSE["endurance"])


def session_value(duration_min: int, intensity: int, key: bool) -> float:
    """Training value: longer and harder is worth more; Key sessions weighted 1.5×."""
    return round(duration_min / 60 * (1 + 0.25 * (intensity - 1)) * (1.5 if key else 1.0), 3)


def _round5(x: float) -> int:
    return int(5 * round(x / 5))


# (discipline, kind, intensity, key, ideal minutes, minimum minutes) for a sprint
# athlete. Olympic sessions are ~25% longer, within the caps above.
Spec = tuple[str, str, int, bool, int, int]
MENU: dict[str, list[Spec]] = {
    "base": [
        ("swim", "technique", 2, True, 45, 30), ("swim", "css", 3, True, 45, 30),
        ("swim", "endurance", 2, False, 40, 25),
        ("bike", "long", 2, True, 90, 60), ("bike", "tempo", 3, True, 60, 45),
        ("bike", "endurance", 2, False, 60, 40),
        ("run", "long", 2, True, 50, 40), ("run", "tempo", 3, True, 40, 30),
        ("run", "easy_strides", 2, False, 35, 25), ("run", "easy", 1, False, 30, 20),
    ],
    "build": [
        ("swim", "css", 4, True, 50, 35), ("swim", "technique", 2, False, 40, 30),
        ("swim", "speed", 4, False, 40, 30),
        ("bike", "threshold", 4, True, 60, 45), ("bike", "long", 2, True, 100, 60),
        ("bike", "brick", 3, False, 60, 40), ("bike", "endurance", 2, False, 50, 35),
        ("run", "threshold", 4, True, 45, 35), ("run", "long", 2, True, 55, 40),
        ("run", "vo2", 5, False, 40, 30), ("run", "easy_strides", 2, False, 35, 25),
    ],
    "taper": [
        ("swim", "race_pace", 3, True, 35, 25), ("swim", "endurance", 2, False, 30, 20),
        ("bike", "openers", 3, True, 40, 30), ("bike", "endurance", 2, False, 40, 30),
        ("run", "openers", 3, True, 25, 20), ("run", "easy", 1, False, 25, 20),
    ],
    "recovery": [
        ("swim", "technique", 2, True, 40, 30), ("swim", "endurance", 2, False, 35, 25),
        ("bike", "endurance", 2, True, 60, 40), ("bike", "endurance", 2, False, 45, 30),
        ("run", "easy_strides", 2, True, 35, 25), ("run", "easy", 1, False, 30, 20),
    ],
}
OLYMPIC_SCALE = 1.25

# Half distance gets its own menus rather than a scaled sprint week: more sessions
# (3 swims, 4 rides, 4 runs), much longer long sessions, race-pace work over VO2, and
# a long brick as a Key session in build. Same tuple layout as MENU.
HALF_MENU: dict[str, list[Spec]] = {
    "base": [
        ("swim", "technique", 2, True, 50, 35), ("swim", "css", 3, True, 55, 40),
        ("swim", "endurance", 2, False, 50, 35),
        ("bike", "long", 2, True, 150, 90), ("bike", "tempo", 3, True, 75, 45),
        ("bike", "endurance", 2, False, 75, 45), ("bike", "endurance", 2, False, 60, 40),
        ("run", "long", 2, True, 90, 60), ("run", "tempo", 3, True, 50, 35),
        ("run", "easy_strides", 2, False, 45, 30), ("run", "easy", 1, False, 40, 25),
    ],
    "build": [
        ("swim", "css", 4, True, 55, 40), ("swim", "endurance", 2, False, 50, 35),
        ("swim", "technique", 2, False, 40, 30),  # 3 swims beat 2 long ones
        ("bike", "long", 2, True, 210, 120), ("bike", "tempo", 3, True, 90, 45),
        ("bike", "brick", 3, True, 120, 75), ("bike", "threshold", 4, False, 75, 50),
        ("bike", "endurance", 2, False, 60, 40),
        ("run", "long", 2, True, 105, 70), ("run", "tempo", 3, True, 60, 35),
        ("run", "threshold", 4, False, 50, 35), ("run", "easy_strides", 2, False, 45, 30),
        # 4 runs max: extra run volume goes into longer easy runs, not a 5th run.
    ],
    "taper": [
        ("swim", "race_pace", 3, True, 40, 30), ("swim", "endurance", 2, False, 35, 25),
        ("bike", "openers", 3, True, 60, 40), ("bike", "endurance", 2, False, 60, 40),
        ("run", "openers", 3, True, 30, 20), ("run", "easy", 1, False, 35, 20),
    ],
    "recovery": [
        ("swim", "technique", 2, True, 50, 35), ("swim", "endurance", 2, False, 45, 30),
        ("bike", "endurance", 2, True, 90, 60), ("bike", "endurance", 2, False, 60, 40),
        ("run", "easy_strides", 2, True, 45, 30), ("run", "easy", 1, False, 40, 25),
    ],
}


def _requires(disc: str, kind: str) -> list[list[Facility]]:
    return BRICK_REQUIRES if kind == "brick" else REQUIRES[disc]


def build_week_sessions(
    targets: dict[str, int], race: Race, phase: Phase, recovery: bool = False
) -> list[Session]:
    """Concrete sessions for the week, sized to each sport's minutes.

    Key sessions come first at their ideal length (shrunk towards their minimum if
    the sport's budget is small); Flex sessions are added while budget remains.
    Leftover budget is used later to lengthen aerobic sessions in long slots.
    """
    menus = HALF_MENU if race == "half" else MENU
    menu = menus["recovery" if recovery and phase != "taper" else phase]
    scale = OLYMPIC_SCALE if race == "olympic" else 1.0
    sessions: list[Session] = []
    used_ids: set[str] = set()

    def make(spec: Spec, minutes: int) -> Session:
        disc, kind, intensity, key, _ideal, lo = spec
        sid = f"{disc}-{kind}"
        n = 2
        while sid in used_ids:
            sid, n = f"{disc}-{kind}-{n}", n + 1
        used_ids.add(sid)
        hi = cap_for(race, disc, kind)
        return Session(
            id=sid, discipline=disc, kind=kind,  # type: ignore[arg-type]
            duration_min=minutes, intensity=intensity, requires=_requires(disc, kind), key=key,
            min_min=min(_round5(lo * (1.15 if scale > 1 else 1)), minutes),
            max_min=max(hi, minutes), race=race, phase="recovery" if recovery else phase,
        )

    for disc in ("swim", "bike", "run"):
        budget = targets.get(disc, 0)
        if budget < MIN_SESSION:
            continue
        specs = [s for s in menu if s[0] == disc]
        keys = [s for s in specs if s[3]]
        ideal = {id(s): min(_round5(s[4] * scale), cap_for(race, disc, s[1])) for s in specs}
        key_total = sum(ideal[id(s)] for s in keys)
        squeeze = min(1.0, budget / key_total) if key_total else 1.0
        remaining = budget
        for s in keys:
            mins = max(min(s[5], ideal[id(s)]), _round5(ideal[id(s)] * squeeze))
            sessions.append(make(s, mins))
            remaining -= mins
        for s in specs:
            if s[3]:
                continue
            lo = _round5(s[5] * (1.15 if scale > 1 else 1))
            if remaining < max(lo, MIN_SESSION):
                continue
            mins = max(lo, min(ideal[id(s)], _round5(remaining)))
            sessions.append(make(s, mins))
            remaining -= mins

    strength = targets.get("strength", 0)
    if strength >= MIN_SESSION and phase != "taper":
        mins = min(_round5(strength), 45)
        sessions.append(
            Session(
                id="strength", discipline="strength", kind="strength", duration_min=mins,
                intensity=2, requires=REQUIRES["strength"], key=False, min_min=20, max_min=45,
            )
        )
    return sessions
