"""Plain-English inputs for the CLI, so nobody has to type a slot uid.

    --week next            --week this            --week 2026-11-09
    --injury run           (7 days)  run:10  (10 days)  run:2026-11-20  (until that date)
    --unavailable thu      (all of Thursday)  thu-pm  thu-am  "thu 16:30"  2026-11-12
"""

from __future__ import annotations

import re
from datetime import date, time, timedelta

from planner.config import DAYS, Slot, week_start
from planner.replan import Injury
from planner.solver import slot_uid

INJURABLE = ("swim", "bike", "run")
DEFAULT_INJURY_DAYS = 7
_TIME = re.compile(r"^(\d{1,2})(?::?(\d{2}))?$")


def parse_time(text: str) -> time:
    """'7', '7:30', '07:30' or '0730' -> time."""
    m = _TIME.match(text.strip())
    if not m:
        raise ValueError(f"'{text}' isn't a time (try 07:30)")
    h, mins = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mins > 59:
        raise ValueError(f"'{text}' isn't a time (try 07:30)")
    return time(h, mins)


def parse_week(text: str, today: date) -> date:
    """'this', 'next', 'last' or any date in the week -> that week's Monday."""
    t = text.strip().lower()
    shifts = {"this": 0, "next": 7, "last": -7}
    if t in shifts:
        return week_start(today + timedelta(days=shifts[t]))
    try:
        return week_start(date.fromisoformat(t))
    except ValueError:
        raise ValueError(f"'{text}' isn't a week (use this, next, last or a date like 2026-11-09)") from None


def parse_injury(text: str, today: date) -> Injury:
    """'run' (7 days), 'run:10' (10 days) or 'run:2026-11-20' (until then, inclusive)."""
    disc, _, until = text.strip().lower().partition(":")
    if disc not in INJURABLE:
        raise ValueError(f"injury discipline '{disc}' must be one of {', '.join(INJURABLE)}")
    until = until.removesuffix("d")
    if not until:
        end = today + timedelta(days=DEFAULT_INJURY_DAYS)
    elif until.isdigit():
        end = today + timedelta(days=int(until))
    else:
        try:
            end = date.fromisoformat(until)
        except ValueError:
            raise ValueError(f"'{text}': use run, run:10 (days) or run:2026-11-20") from None
    return Injury(discipline=disc, until=end)


def _matches(spec: str, slot: Slot) -> bool:
    s = spec.strip().lower()
    if "|" in s:
        return s == slot_uid(slot).lower()
    s = s.replace("@", " ")
    try:
        return date.fromisoformat(s) == slot.on
    except ValueError:
        pass
    parts = re.split(r"[\s\-]+", s, maxsplit=1)
    day = parts[0][:3]
    if day not in DAYS:
        raise ValueError(f"'{spec}' isn't a day or slot (try thu, thu-pm or \"thu 16:30\")")
    if slot.day != day:
        return False
    if len(parts) == 1:
        return True
    rest = parts[1]
    if rest in ("am", "morning"):
        return slot.start < time(12)
    if rest in ("pm", "afternoon", "evening"):
        return slot.start >= time(12)
    t = parse_time(rest)
    return slot.start <= t < slot.end


def resolve_slots(specs: list[str], slots: list[Slot]) -> list[str]:
    """Turn friendly slot specs into slot uids for this week's calendar."""
    uids: list[str] = []
    for spec in specs:
        hits = [slot_uid(k) for k in slots if _matches(spec, k)]
        if not hits:
            options = ", ".join(f"{k.day} {k.start:%H:%M}" for k in slots)
            raise ValueError(f"no slot this week matches '{spec}'. Slots: {options}")
        uids.extend(h for h in hits if h not in uids)
    return uids
