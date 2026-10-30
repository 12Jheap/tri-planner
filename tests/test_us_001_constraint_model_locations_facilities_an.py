"""US-001: Constraint model — locations, facilities and slots (v0)."""

from datetime import date, time
from pathlib import Path

import pytest

from planner.config import ConfigError, Facility, calendar_for_week, load_config, parse_config

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "joe.yaml"


def _base(slots=None, facilities=None):
    return {
        "athlete": "t",
        "race": "sprint",
        "locations": [
            {
                "name": "School",
                "facilities": facilities
                or [
                    "wattbike",
                    "treadmill",
                    "gym",
                    {"name": "pool", "windows": [{"start": "16:00", "end": "19:00"}]},
                ],
            },
            {"name": "Home", "facilities": ["road_bike", "outdoor_run"]},
        ],
        "templates": {
            "term": {
                "slots": slots
                or [
                    {"day": "mon", "start": "06:30", "end": "07:30", "location": "School"},
                    {"day": "mon", "start": "16:15", "end": "18:15", "location": "School"},
                    {"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"},
                ]
            },
            "holiday": {
                "slots": [{"day": "mon", "start": "08:00", "end": "10:00", "location": "Home"}]
            },
        },
        "default_template": "term",
    }


def test_ac_001_accepts_a_yaml_file_defining_locations_each_with_facilities_():
    """AC-001 [unit-test]: Accepts a YAML file defining locations, each with facilities (pool, wattbike, treadmill, road bike, gym) and per-facility opening windows (e.g. pool only after 16:00)"""
    cfg = load_config(EXAMPLE)
    school = cfg.location("School")
    assert {f.name for f in school.facilities} >= {
        Facility.POOL,
        Facility.WATTBIKE,
        Facility.TREADMILL,
        Facility.GYM,
    }
    assert {f.name for f in cfg.location("Home").facilities} >= {Facility.ROAD_BIKE}
    # Pool only after 16:00 on weekdays.
    assert not school.has(Facility.POOL, "mon", time(6, 30), time(7, 30))
    assert school.has(Facility.POOL, "mon", time(16, 15), time(17, 15))
    assert not school.has(Facility.POOL, "sat", time(16, 15), time(17, 15))
    # Facilities with no windows are always available.
    assert school.has(Facility.WATTBIKE, "mon", time(6, 30), time(7, 30))


def test_ac_002_accepts_a_weekly_calendar_mapping_each_day_to_a_location_and():
    """AC-002 [unit-test]: Accepts a weekly calendar mapping each day to a location and listing available time slots"""
    cfg = parse_config(_base())
    week = calendar_for_week(cfg, date(2026, 11, 2))  # a Monday
    assert [(s.day, s.location, s.minutes) for s in week] == [
        ("mon", "School", 60),
        ("mon", "School", 120),
        ("sat", "Home", 180),
    ]
    assert week[0].on == date(2026, 11, 2)
    assert week[-1].on == date(2026, 11, 7)
    assert week[0].key == "mon-06:30-07:30@School"


def test_ac_003_rejects_config_with_overlapping_slots_or_unknown_facility_na():
    """AC-003 [unit-test]: Rejects config with overlapping slots or unknown facility names, with a clear error"""
    overlapping = [
        {"day": "mon", "start": "16:00", "end": "17:30", "location": "School"},
        {"day": "mon", "start": "17:00", "end": "18:00", "location": "School"},
    ]
    with pytest.raises(ConfigError, match="overlapping slots on mon: 16:00-17:30 and 17:00-18:00"):
        parse_config(_base(slots=overlapping))
    with pytest.raises(ConfigError, match="unknown facility 'jacuzzi'"):
        parse_config(_base(facilities=["wattbike", "jacuzzi"]))
    bad_location = [{"day": "mon", "start": "06:30", "end": "07:30", "location": "Gym"}]
    with pytest.raises(ConfigError, match="unknown location 'Gym'"):
        parse_config(_base(slots=bad_location))


def test_ac_004_supports_date_range_overrides_holiday_block_exam_week_travel():
    """AC-004 [unit-test]: Supports date-range overrides (holiday block, exam week, travel)"""
    data = _base()
    data["overrides"] = [
        {"name": "Half term", "start": "2026-11-09", "end": "2026-11-15", "template": "holiday"}
    ]
    cfg = parse_config(data)
    normal = calendar_for_week(cfg, date(2026, 11, 2))
    half_term = calendar_for_week(cfg, date(2026, 11, 9))
    assert {s.location for s in normal} == {"School", "Home"}
    assert [(s.day, s.location) for s in half_term] == [("mon", "Home")]
    # Partial-week override applies day by day.
    data["overrides"] = [
        {"name": "Trip", "start": "2026-11-04", "end": "2026-11-20", "template": "holiday"}
    ]
    partial = calendar_for_week(parse_config(data), date(2026, 11, 2))
    assert [s.day for s in partial] == ["mon", "mon"]  # Mon from term; rest of week is holiday
    with pytest.raises(ConfigError, match="unknown template"):
        data["overrides"] = [{"name": "x", "start": "2026-11-04", "end": "2026-11-05", "template": "nope"}]
        parse_config(data)
