"""Fitness tests: keep your zones honest.

Every pace, watt and heart-rate target comes from three numbers: your 5k time,
your swim CSS and your bike FTP. They go stale as you get fitter, and a plan aimed
at old numbers is too easy. So the planner schedules a test when a number is
missing, or every 8 weeks:

- run: a 5 km time trial,
- swim: a 400 m and a 200 m time trial (CSS = (T400 − T200) / 2 per 100 m),
- bike: a 20-minute test (FTP = 95% of the average power).

A test *replaces* that sport's quality session for the week, so it adds no load. At
most two tests land in one week, never in a recovery, taper, race or time-only
week, and never for a sport you can't measure (no pool, no power). Afterwards you
enter the result and every target updates.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from planner.config import AthleteConfig, Facility
from planner.profile import Profile, mmss, parse_duration
from planner.sessions import BIKE_KIT, RUN_KIT, Session

TEST_EVERY_WEEKS = 8
MAX_TESTS_PER_WEEK = 2
SPORTS = ("swim", "run", "bike")
NUMBER = {"run": "run_5k", "swim": "swim_css", "bike": "ftp"}
NAMES = {"run": "5k time", "swim": "Swim CSS", "bike": "Bike FTP"}
# The quality session a test stands in for, most intense first.
REPLACES = {"run": ("threshold", "tempo", "vo2"), "bike": ("threshold", "tempo"),
            "swim": ("css", "speed")}
MINUTES = {"run": (50, 40), "bike": (60, 45), "swim": (45, 35)}  # ideal, shortest


def _has(cfg: AthleteConfig, *facilities: Facility) -> bool:
    return any(f.name in facilities for loc in cfg.locations for f in loc.facilities)


def can_test(cfg: AthleteConfig, sport: str) -> bool:
    """Only test what you can measure: a pool for CSS, power for FTP."""
    if sport == "swim":
        return _has(cfg, Facility.POOL)
    if sport == "bike":
        return _has(cfg, Facility.WATTBIKE) or cfg.profile.ftp is not None
    return _has(cfg, *RUN_KIT)


def test_requires(cfg: AthleteConfig, sport: str) -> list[list[Facility]]:
    if sport == "swim":
        return [[Facility.POOL]]  # a measured length, not open water
    if sport == "bike":  # the wattbike measures power; otherwise your own bike's meter
        return [[Facility.WATTBIKE]] if _has(cfg, Facility.WATTBIKE) else [BIKE_KIT]
    return [RUN_KIT]


def last_tested(profile: Profile, sport: str, reference: date) -> date | None:
    """When the number was last measured. A number you typed in without a date counts
    from `reference` (your first week on the plan, or now if you've only just started)."""
    if sport in profile.tested:
        return profile.tested[sport]
    return reference if getattr(profile, NUMBER[sport]) is not None else None


def next_due(cfg: AthleteConfig, sport: str, reference: date) -> date | None:
    """The date a test becomes due; None = due now (there's no number yet)."""
    last = last_tested(cfg.profile, sport, reference)
    if last is None:
        return None
    return last + timedelta(weeks=TEST_EVERY_WEEKS)


def tests_due(cfg: AthleteConfig, week: date, reference: date | None,
              awaiting: set[str] | frozenset[str] = frozenset()) -> list[str]:
    """Sports to test in `week`: missing numbers first, then the stalest, at most two."""
    if not cfg.fitness_tests:
        return []
    reference = reference or week
    ranked: list[tuple[int, date, str]] = []
    for sport in SPORTS:
        if sport in awaiting or not can_test(cfg, sport):
            continue
        due = next_due(cfg, sport, reference)
        if due is None:
            ranked.append((0, date.min, sport))
        elif due <= week + timedelta(days=6):
            ranked.append((1, due, sport))
    return [sport for _, _, sport in sorted(ranked)][:MAX_TESTS_PER_WEEK]


def apply_tests(sessions: list[Session], due: list[str], cfg: AthleteConfig
                ) -> tuple[list[Session], list[str]]:
    """Swap each due sport's quality session for its test. Returns (sessions, notes)."""
    out = list(sessions)
    notes: list[str] = []
    for sport in due:
        target = next((s for kind in REPLACES[sport] for s in out
                       if s.discipline == sport and s.kind == kind), None)
        if target is None:
            continue  # no quality session to give up this week (tiny budget, busy week)
        ideal, shortest = MINUTES[sport]
        test = Session(
            id=f"{sport}-test", discipline=sport, kind="test",  # type: ignore[arg-type]
            duration_min=ideal, intensity=5, requires=test_requires(cfg, sport), key=True,
            min_min=shortest, max_min=ideal, race=target.race, phase=target.phase,
        )
        out[out.index(target)] = test
        why = "no number yet" if getattr(cfg.profile, NUMBER[sport]) is None \
            else f"last measured {TEST_EVERY_WEEKS}+ weeks ago"
        notes.append(f"Fitness test this week: {test.title} ({why}). It replaces your "
                     f"{target.title.lower()}. Enter the result afterwards and your zones update.")
    return out, notes


class FitnessChange(BaseModel):
    sport: str
    on: date
    before: str | None
    after: str
    zone_line: str

    @property
    def text(self) -> str:
        was = f"{self.before} → " if self.before and self.before != self.after else ""
        return f"{NAMES[self.sport]}: {was}{self.after}. {self.zone_line}"


def describe(profile: Profile, sport: str) -> str | None:
    """The current number in words, or None if there isn't one."""
    if sport == "run" and profile.run_5k:
        return mmss(profile.run_5k)
    if sport == "swim" and profile.swim_css:
        return f"{mmss(profile.swim_css)}/100m"
    if sport == "bike" and profile.ftp:
        return f"{profile.ftp} W"
    return None


def numeric(profile: Profile, sport: str) -> int | None:
    return getattr(profile, NUMBER[sport])


def result_changes(sport: str, values: Mapping[str, str]) -> tuple[dict[str, Any], list[str]]:
    """Profile fields to set and to drop for a test result. Raises ValueError with a
    plain message when something's missing or isn't a time / number."""
    def need(key: str, what: str) -> str:
        v = (values.get(key) or "").strip()
        if not v:
            raise ValueError(f"Enter your {what}.")
        return v

    if sport == "run":
        t = parse_duration(need("time", "5k time, like 22:40"))
        assert t is not None
        return {"run_5k": mmss(t)}, []
    if sport == "swim":
        t400 = parse_duration(need("t400", "400m time, like 7:20"))
        t200 = parse_duration(need("t200", "200m time, like 3:30"))
        assert t400 is not None and t200 is not None
        # CSS is worked out from the two times, so an older typed-in CSS is dropped.
        return {"swim_400": mmss(t400), "swim_200": mmss(t200)}, ["swim_css"]
    if sport == "bike":
        raw = need("p20", "average power for the 20 minutes, in watts")
        try:
            p20 = float(raw)
        except ValueError:
            raise ValueError(f"'{raw}' isn't a number of watts.") from None
        if not 60 <= p20 <= 600:
            raise ValueError(f"{raw} W looks wrong for a 20-minute average.")
        return {"ftp": round(0.95 * p20)}, []
    raise ValueError(f"unknown test '{sport}'")


class FitnessLog:
    """Every test result, appended to out/fitness.jsonl, for the Progress page."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def rows(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def append(self, on: date, sport: str, value: int, text: str,
               values: Mapping[str, str]) -> None:
        """Add a result. Entering the same test again (same sport, same day) corrects it."""
        rows = [r for r in self.rows() if (r["sport"], r["on"]) != (sport, on.isoformat())]
        rows.append({"on": on.isoformat(), "sport": sport, "value": value, "text": text,
                     "entered": dict(values)})
        rows.sort(key=lambda r: r["on"])
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        tmp.replace(self.path)
