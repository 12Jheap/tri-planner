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


def scrape_setup_form(html: str) -> dict[str, list[str]]:
    """The Profile form as a browser would post it back unchanged."""
    import re

    data: dict[str, list[str]] = {}
    form = html.split('id="setup"', 1)[1].split("</form>", 1)[0]
    for tag in re.finditer(r'<(input|select)[^>]*name="([^"]+)"[^>]*>', form):
        name, el = tag.group(2), tag.group(0)
        if "__" in name or ('type="checkbox"' in el and "checked" not in el):
            continue
        value = re.search(r'value="([^"]*)"', el)
        if tag.group(1) == "select" and "data-value" in el:  # filled in by the page's script
            value = re.search(r'data-value="([^"]*)"', el)
        elif tag.group(1) == "select":
            chunk = form[tag.end(): form.index("</select>", tag.end())]
            picked = re.search(r"<option[^>]*\bselected\b[^>]*>([^<]*)<", chunk)
            value = picked and (re.search(r'value="([^"]*)"', picked.group(0)) or picked)
        data.setdefault(name, []).append(value.group(1).strip() if value else "")
    data["mode"] = ["form"]
    return data
