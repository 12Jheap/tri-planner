"""Constraint model: where you train, what's there, and when you're free (US-001).

A config file describes:
- locations, each with the facilities/kit available there and, optionally, the
  windows when a facility is open (e.g. the school pool only after 16:00),
- one or more weekly templates (e.g. "term", "holiday") listing time slots per day,
  each slot tied to a location,
- date-range overrides that swap in a different template (holiday block, exam
  week, travel).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ValidationError, field_validator, model_validator

DAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class ConfigError(ValueError):
    """Raised for any invalid athlete configuration, with a human-readable message."""


class Facility(str, Enum):
    POOL = "pool"
    OPEN_WATER = "open_water"
    WATTBIKE = "wattbike"
    ROAD_BIKE = "road_bike"
    TREADMILL = "treadmill"
    OUTDOOR_RUN = "outdoor_run"
    GYM = "gym"


def _check_day(day: str) -> str:
    d = day.lower()[:3]
    if d not in DAYS:
        raise ValueError(f"unknown day '{day}' (use one of {', '.join(DAYS)})")
    return d


def minutes_between(start: time, end: time) -> int:
    return (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)


class Window(BaseModel):
    """An opening window for a facility. `days=None` means every day."""

    start: time
    end: time
    days: list[str] | None = None

    @field_validator("days")
    @classmethod
    def _days(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else [_check_day(d) for d in v]

    @model_validator(mode="after")
    def _order(self) -> Window:
        if self.end <= self.start:
            raise ValueError(f"window ends ({self.end}) before it starts ({self.start})")
        return self

    def covers(self, day: str, start: time, end: time) -> bool:
        if self.days is not None and day not in self.days:
            return False
        return self.start <= start and end <= self.end


class FacilitySpec(BaseModel):
    """A facility at a location. No windows means it's available whenever you are."""

    name: Facility
    windows: list[Window] = []

    def open_for(self, day: str, start: time, end: time) -> bool:
        return not self.windows or any(w.covers(day, start, end) for w in self.windows)


class Location(BaseModel):
    name: str
    facilities: list[FacilitySpec]

    @field_validator("facilities", mode="before")
    @classmethod
    def _shorthand(cls, v: Any) -> Any:
        # Allow `- pool` as shorthand for `- {name: pool}`.
        return [{"name": f} if isinstance(f, str) else f for f in v]

    def has(self, facility: Facility, day: str, start: time, end: time) -> bool:
        return any(f.name == facility and f.open_for(day, start, end) for f in self.facilities)


class Slot(BaseModel):
    """A block of free time on a given weekday at a given location."""

    day: str
    start: time
    end: time
    location: str
    on: date | None = None  # filled in by calendar_for_week

    @field_validator("day")
    @classmethod
    def _day(cls, v: str) -> str:
        return _check_day(v)

    @model_validator(mode="after")
    def _order(self) -> Slot:
        if self.end <= self.start:
            raise ValueError(f"slot {self.day} {self.start}-{self.end} ends before it starts")
        return self

    @property
    def minutes(self) -> int:
        return minutes_between(self.start, self.end)

    @property
    def key(self) -> str:
        """Stable identity used by the adherence model: day × window × location."""
        return f"{self.day}-{self.start:%H:%M}-{self.end:%H:%M}@{self.location}"

    @property
    def starts_at(self) -> datetime:
        if self.on is None:
            raise ValueError("slot has no date; use calendar_for_week()")
        return datetime.combine(self.on, self.start)


class WeekTemplate(BaseModel):
    slots: list[Slot]

    @model_validator(mode="after")
    def _no_overlaps(self) -> WeekTemplate:
        for day in DAYS:
            day_slots = sorted((s for s in self.slots if s.day == day), key=lambda s: s.start)
            for a, b in zip(day_slots, day_slots[1:]):
                if b.start < a.end:
                    raise ValueError(
                        f"overlapping slots on {day}: {a.start:%H:%M}-{a.end:%H:%M} "
                        f"and {b.start:%H:%M}-{b.end:%H:%M}"
                    )
        return self


class Override(BaseModel):
    """Use a different weekly template between two dates (inclusive)."""

    name: str
    start: date
    end: date
    template: str


class AthleteConfig(BaseModel):
    athlete: str
    race: Literal["sprint", "olympic"]
    race_date: date | None = None
    locations: list[Location]
    templates: dict[str, WeekTemplate]
    default_template: str
    overrides: list[Override] = []

    @model_validator(mode="after")
    def _references(self) -> AthleteConfig:
        names = {loc.name for loc in self.locations}
        for tname, tmpl in self.templates.items():
            for s in tmpl.slots:
                if s.location not in names:
                    raise ValueError(
                        f"template '{tname}' uses unknown location '{s.location}' "
                        f"(known: {', '.join(sorted(names))})"
                    )
        if self.default_template not in self.templates:
            raise ValueError(f"default_template '{self.default_template}' is not defined")
        for o in self.overrides:
            if o.template not in self.templates:
                raise ValueError(f"override '{o.name}' uses unknown template '{o.template}'")
            if o.end < o.start:
                raise ValueError(f"override '{o.name}' ends before it starts")
        return self

    def location(self, name: str) -> Location:
        for loc in self.locations:
            if loc.name == name:
                return loc
        raise KeyError(name)

    def template_for(self, on: date) -> str:
        for o in self.overrides:
            if o.start <= on <= o.end:
                return o.template
        return self.default_template


def _friendly(err: ValidationError) -> str:
    parts = []
    for e in err.errors():
        loc = ".".join(str(p) for p in e["loc"])
        msg = e["msg"].removeprefix("Value error, ")
        if e["type"] == "enum":
            allowed = ", ".join(f.value for f in Facility)
            msg = f"unknown facility '{e.get('input')}' (allowed: {allowed})"
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts)


def parse_config(data: dict[str, Any]) -> AthleteConfig:
    try:
        return AthleteConfig.model_validate(data)
    except ValidationError as err:
        raise ConfigError(_friendly(err)) from None


def load_config(path: str | Path) -> AthleteConfig:
    with open(path, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")
    return parse_config(data)


def week_start(on: date) -> date:
    """Monday of the week containing `on`."""
    return on - timedelta(days=on.weekday())


def calendar_for_week(config: AthleteConfig, start: date) -> list[Slot]:
    """Dated slots for the 7 days from `start`, applying any overrides day by day."""
    out: list[Slot] = []
    for i in range(7):
        d = start + timedelta(days=i)
        day = DAYS[d.weekday()]
        tmpl = config.templates[config.template_for(d)]
        out.extend(s.model_copy(update={"on": d}) for s in tmpl.slots if s.day == day)
    return sorted(out, key=lambda s: (s.on, s.start))
