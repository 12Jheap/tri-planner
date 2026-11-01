"""`tri-plan init`: build an athlete config by answering a few questions.

No YAML knowledge needed. Asks for: name, race and date, weekly hours, where you
train (and what's there, and when the pool's open), and your free times each day.
The result is validated before it's written, and you can edit it later by hand.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from functools import partial
from itertools import pairwise
from typing import Any

import yaml

from planner.config import DAYS, ConfigError, Facility, parse_config
from planner.friendly import parse_time
from planner.targets import DEFAULT_HOURS

Ask = Callable[[str], str]
Say = Callable[[str], None]

FACILITY_NAMES: dict[Facility, str] = {
    Facility.POOL: "pool",
    Facility.OPEN_WATER: "open water (lake/sea)",
    Facility.ROAD_BIKE: "road bike (ride outside)",
    Facility.WATTBIKE: "indoor bike / turbo / wattbike",
    Facility.OUTDOOR_RUN: "run outside",
    Facility.TREADMILL: "treadmill",
    Facility.GYM: "gym",
}
FACILITIES = list(FACILITY_NAMES)
DAY_NAMES = dict(zip(DAYS, ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                            "Saturday", "Sunday"), strict=True))
DAY_GROUPS = {
    "daily": list(DAYS), "everyday": list(DAYS), "weekdays": list(DAYS[:5]),
    "weekends": list(DAYS[5:]), "weekend": list(DAYS[5:]),
}


class _QuotedTimes(yaml.SafeDumper):
    """Quote 'HH:MM' so YAML never reads a time as a base-60 number."""


def _str(dumper: yaml.SafeDumper, value: str) -> yaml.Node:
    style = '"' if re.fullmatch(r"\d{1,2}:\d{2}", value) else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_QuotedTimes.add_representer(str, _str)


def to_yaml(config: dict[str, Any]) -> str:
    return yaml.dump(config, Dumper=_QuotedTimes, sort_keys=False, allow_unicode=True)


def _hhmm(text: str) -> str:
    return f"{parse_time(text):%H:%M}"


def parse_days(text: str) -> list[str]:
    """'mon-fri', 'sat,sun', 'weekdays', 'tue thu' -> ['mon', ...]."""
    t = text.strip().lower()
    if t in DAY_GROUPS:
        return DAY_GROUPS[t]
    out: list[str] = []
    for part in re.split(r"[,\s]+", t):
        if not part:
            continue
        if "-" in part:
            a, b = (p[:3] for p in part.split("-", 1))
            if a not in DAYS or b not in DAYS:
                raise ValueError(f"'{part}' isn't a day range (try mon-fri)")
            i, j = DAYS.index(a), DAYS.index(b)
            out.extend(DAYS[i : j + 1] if i <= j else [*DAYS[i:], *DAYS[: j + 1]])
        elif part[:3] in DAYS:
            out.append(part[:3])
        else:
            raise ValueError(f"'{part}' isn't a day")
    return [d for d in DAYS if d in out]


def _range(text: str) -> tuple[str, str]:
    a, sep, b = text.partition("-")
    if not sep:
        raise ValueError(f"'{text}' isn't a time range (try 16:00-19:00)")
    start, end = _hhmm(a), _hhmm(b)
    if end <= start:
        raise ValueError(f"'{text}' ends before it starts")
    return start, end


def parse_windows(text: str) -> list[dict[str, Any]]:
    """'mon-fri 16:00-19:00; sat,sun 8-12' or just '16:00-19:00' (every day)."""
    out: list[dict[str, Any]] = []
    for chunk in filter(None, (c.strip() for c in text.split(";"))):
        m = re.match(r"^(.*?)\s*(\d{1,2}(?::?\d{2})?\s*-\s*\d{1,2}(?::?\d{2})?)$", chunk)
        if not m:
            raise ValueError(f"'{chunk}' should look like 'mon-fri 16:00-19:00'")
        start, end = _range(m.group(2).replace(" ", ""))
        w: dict[str, Any] = {"start": start, "end": end}
        if m.group(1).strip():
            w["days"] = parse_days(m.group(1))
        out.append(w)
    return out


def parse_facilities(text: str) -> list[Facility]:
    """'1,3,5' (menu numbers) or names like 'pool, treadmill'."""
    out: list[Facility] = []
    for part in filter(None, (p.strip().lower() for p in re.split(r"[,\s]+", text))):
        if part.isdigit() and 1 <= int(part) <= len(FACILITIES):
            out.append(FACILITIES[int(part) - 1])
            continue
        try:
            out.append(Facility(part))
        except ValueError:
            raise ValueError(f"'{part}' isn't on the list (use the numbers)") from None
    return list(dict.fromkeys(out))


def parse_slots(text: str, day: str, locations: list[str]) -> list[dict[str, str]]:
    """'06:30-07:30 school, 16:15-18:15 home' -> slot dicts for `day`.

    With one location you can leave the place off.
    """
    out: list[dict[str, str]] = []
    for chunk in filter(None, (c.strip() for c in text.split(","))):
        rng, _, place = chunk.partition(" ")
        start, end = _range(rng)
        place = place.strip()
        if not place:
            if len(locations) != 1:
                raise ValueError(f"'{chunk}': say where (one of {', '.join(locations)})")
            loc = locations[0]
        else:
            hits = [n for n in locations if n.lower().startswith(place.lower())]
            if len(hits) != 1:
                raise ValueError(f"'{place}' isn't one of your places ({', '.join(locations)})")
            loc = hits[0]
        out.append({"day": day, "start": start, "end": end, "location": loc})
    out.sort(key=lambda s: s["start"])
    for a, b in pairwise(out):
        if b["start"] < a["end"]:
            raise ValueError(f"{a['start']}-{a['end']} and {b['start']}-{b['end']} overlap")
    return out


def _ask_until_ok(ask: Ask, say: Say, prompt: str, parse: Callable[[str], Any]) -> Any:
    while True:
        try:
            return parse(ask(prompt))
        except (ValueError, ConfigError) as err:
            say(f"  ✗ {err}")


def run_wizard(ask: Ask, say: Say) -> dict[str, Any]:
    """Ask the questions and return a validated config dict."""
    say("Let's set up your training week. Press Enter to accept [defaults].\n")
    name = ask("Your name: ").strip() or "Athlete"

    def race_kind(t: str) -> str:
        t = t.strip().lower() or "sprint"
        if t not in ("sprint", "olympic"):
            raise ValueError("sprint or olympic")
        return t

    race = _ask_until_ok(ask, say, "Race distance, sprint or olympic [sprint]: ", race_kind)

    def race_day(t: str) -> date | None:
        return date.fromisoformat(t.strip()) if t.strip() else None

    race_date = _ask_until_ok(ask, say, "Race date, e.g. 2027-06-27 [skip]: ", race_day)

    default_h = DEFAULT_HOURS[race]

    def hours(t: str) -> float:
        h = float(t) if t.strip() else default_h
        if not 1 <= h <= 30:
            raise ValueError("pick something between 1 and 30")
        return h

    weekly_hours = _ask_until_ok(
        ask, say,
        f"Hours a week you want to train, in a normal week [{default_h:g}]: ", hours,
    )

    say("\nWhere do you train? Add each place: home, school, work, the gym…")
    menu = "\n".join(f"  {i}. {FACILITY_NAMES[f]}" for i, f in enumerate(FACILITIES, 1))
    locations: list[dict[str, Any]] = []
    while True:
        default = "" if locations else " [Home]"
        place = ask(f"\nPlace name{default} (Enter when done): ").strip()
        if not place:
            if locations:
                break
            place = "Home"
        if any(loc["name"].lower() == place.lower() for loc in locations):
            say("  ✗ you've already added that place")
            continue
        say(f"What can you use at {place}?\n{menu}")
        kit = _ask_until_ok(ask, say, "Numbers, e.g. 1,3,5: ", parse_facilities)
        facilities: list[Any] = []
        for f in kit:
            if f in (Facility.POOL, Facility.OPEN_WATER, Facility.GYM):
                windows = _ask_until_ok(
                    ask, say,
                    f"  When is the {f.value.replace('_', ' ')} open? e.g. "
                    "'mon-fri 16:00-19:00; weekends 8-12' [whenever I'm there]: ",
                    parse_windows,
                )
                facilities.append({"name": f.value, "windows": windows} if windows else f.value)
            else:
                facilities.append(f.value)
        locations.append({"name": place, "facilities": facilities})
    names = [loc["name"] for loc in locations]

    where = "" if len(names) == 1 else f" and where ({'/'.join(names)})"
    say(
        f"\nNow your free time each day{where}. Separate slots with commas, e.g. "
        f"'06:30-07:30 {names[0]}, 16:15-18:15 {names[-1]}'. Enter = no training that day."
    )
    slots: list[dict[str, str]] = []
    for day in DAYS:
        slots += _ask_until_ok(
            ask, say, f"{DAY_NAMES[day]}: ", partial(parse_slots, day=day, locations=names)
        )

    config: dict[str, Any] = {"athlete": name, "race": race}
    if race_date:
        config["race_date"] = race_date
    config |= {
        "weekly_hours": weekly_hours,
        "locations": locations,
        "templates": {"normal": {"slots": slots}},
        "default_template": "normal",
        "overrides": [],
    }
    parse_config(config)  # raises ConfigError with a readable message if anything's off
    if not slots:
        say("\nNo free time entered: add slots to the file before planning.")
    return config
