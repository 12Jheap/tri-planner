"""Shared fixtures: a small config builder and a session factory."""

from __future__ import annotations

from datetime import date

import pytest

from planner.config import AthleteConfig, parse_config
from planner.sessions import REQUIRES, Session

MONDAY = date(2026, 11, 2)
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def make_config(slots: list[dict], locations: list[dict] | None = None) -> AthleteConfig:
    return parse_config(
        {
            "athlete": "test",
            "race": "sprint",
            "locations": locations
            or [
                {
                    "name": "School",
                    "facilities": [
                        "wattbike",
                        "treadmill",
                        "gym",
                        {"name": "pool", "windows": [{"start": "16:00", "end": "19:00"}]},
                    ],
                },
                {"name": "Home", "facilities": ["road_bike", "outdoor_run"]},
            ],
            "templates": {"t": {"slots": slots}},
            "default_template": "t",
        }
    )


def make_session(
    sid: str, discipline: str = "bike", minutes: int = 45, intensity: int = 2, key: bool = True
) -> Session:
    return Session(
        id=sid,
        discipline=discipline,  # type: ignore[arg-type]
        kind="threshold" if intensity >= 4 else "endurance",
        duration_min=minutes,
        intensity=intensity,
        requires=REQUIRES[discipline],
        key=key,
    )


@pytest.fixture
def monday() -> date:
    return MONDAY


@pytest.fixture(autouse=True)
def _no_real_garmin(tmp_path_factory, monkeypatch):
    """Tests never see your real Garmin key, so nothing ever syncs your real account."""
    from planner import garmin

    monkeypatch.setattr(garmin, "KEY_FILE", tmp_path_factory.mktemp("garmin") / "no-key")
    monkeypatch.delenv(garmin.KEY_ENV, raising=False)
