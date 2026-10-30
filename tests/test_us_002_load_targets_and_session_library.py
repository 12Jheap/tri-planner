"""US-002: Load targets and session library (v0)."""

from datetime import time

import pytest

from planner.config import Facility, Location
from planner.sessions import Session, build_week_sessions
from planner.targets import weekly_targets


def test_ac_005_returns_weekly_minutes_per_discipline_for_a_sprint_or_olympi():
    """AC-005 [e2e-test]: Returns weekly minutes per discipline for a sprint or Olympic template given phase (base/build/taper) and available hours"""
    sprint = weekly_targets("sprint", "base", available_minutes=600)
    olympic = weekly_targets("olympic", "base", available_minutes=600)
    assert set(sprint) == {"swim", "bike", "run", "strength"}
    assert sum(sprint.values()) <= 480  # never plans more than 80% of free time
    assert olympic["bike"] > sprint["bike"]  # olympic is more bike-heavy
    assert sprint["swim"] > olympic["swim"]
    taper = weekly_targets("sprint", "taper", available_minutes=600)
    assert sum(taper.values()) < sum(sprint.values())
    assert taper["strength"] == 0
    assert all(v % 5 == 0 for v in sprint.values())
    with pytest.raises(ValueError):
        weekly_targets("ironman", "base", 600)  # type: ignore[arg-type]


def test_ac_006_caps_week_on_week_load_increase_at_a_configurable_ramp_defau():
    """AC-006 [unit-test]: Caps week-on-week load increase at a configurable ramp (default 10%)"""
    capped = weekly_targets("sprint", "base", available_minutes=900, previous_week_minutes=300)
    assert sum(capped.values()) <= 330
    wider = weekly_targets(
        "sprint", "base", available_minutes=900, previous_week_minutes=300, ramp=0.25
    )
    assert 330 < sum(wider.values()) <= 375
    uncapped = weekly_targets("sprint", "base", available_minutes=900)
    assert sum(uncapped.values()) > 375


def test_ac_007_each_session_has_type_duration_intensity_required_facilities():
    """AC-007 [e2e-test]: Each session has type, duration, intensity, required facilities, and a Key or Flex flag"""
    for phase in ("base", "build", "taper"):
        targets = weekly_targets("olympic", phase, available_minutes=600)  # type: ignore[arg-type]
        sessions = build_week_sessions(targets, "olympic", phase)  # type: ignore[arg-type]
        assert sessions
        assert any(s.key for s in sessions) and any(not s.key for s in sessions)
        for s in sessions:
            assert isinstance(s, Session)
            assert s.kind and s.duration_min >= 20 and 1 <= s.intensity <= 5
            assert s.value > 0
            assert isinstance(s.requires, list)
        assert len({s.id for s in sessions}) == len(sessions)
    build = build_week_sessions(weekly_targets("olympic", "build", 600), "olympic", "build")
    assert any(s.hard and s.key for s in build)  # threshold work is Key


def test_ac_008_session_library_includes_indoor_substitutes_wattbike_for_roa():
    """AC-008 [unit-test]: Session library includes indoor substitutes (wattbike for road bike, treadmill for outdoor run)"""
    sessions = build_week_sessions(weekly_targets("sprint", "base", 600), "sprint", "base")
    bike = next(s for s in sessions if s.discipline == "bike")
    run = next(s for s in sessions if s.discipline == "run")
    indoor = Location(name="Gym", facilities=["wattbike", "treadmill"])
    outdoor = Location(name="Home", facilities=["road_bike", "outdoor_run"])
    nothing = Location(name="Hotel", facilities=["gym"])
    t0, t1 = time(7), time(8)
    for loc in (indoor, outdoor):
        assert bike.fits(loc, "mon", t0, t1)
        assert run.fits(loc, "mon", t0, t1)
    assert not bike.fits(nothing, "mon", t0, t1)
    assert Facility.WATTBIKE in bike.requires[0] and Facility.ROAD_BIKE in bike.requires[0]
    assert Facility.TREADMILL in run.requires[0] and Facility.OUTDOOR_RUN in run.requires[0]
