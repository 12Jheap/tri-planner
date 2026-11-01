"""Turn what your watch recorded into ticks on the plan, so you don't have to log by hand.

Activities arrive as .FIT files: synced from Garmin Connect (garmin.py), uploaded
on the website, read from the watch over USB, or from Connect's "Export original"
zip. Each one is matched to the planned session it most likely was:

- same sport (a bike activity can be a brick; a run straight after it is the run leg),
- same week, preferring the same day and the closest start time,
- only sessions you haven't logged yourself.

Same day -> "done"; another day that week -> "moved". Anything that doesn't match
is reported as an extra, not forced onto the plan. Each activity is imported once.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import BaseModel

from planner.adherence import LogRow, Source
from planner.config import week_start
from planner.solver import Placement, Plan

SPORTS = {1: "run", 2: "bike", 5: "swim"}  # FIT sport enum
TRAINING = 10  # FIT 'training'; strength_training is sub-sport 20
STRENGTH_SUB = 20
BRICK_GAP = timedelta(minutes=20)  # a run this soon after a ride is the brick's run leg


class Activity(BaseModel):
    activity_id: str
    start: datetime  # athlete's local time
    sport: str  # swim / bike / run / strength
    seconds: int
    distance_m: int | None = None
    avg_hr: int | None = None
    avg_power: int | None = None

    @property
    def minutes(self) -> int:
        return round(self.seconds / 60)

    @property
    def end(self) -> datetime:
        return self.start + timedelta(seconds=self.seconds)

    def describe(self) -> str:
        bits = [f"{self.start:%a %d %b %H:%M}", self.sport, f"{self.minutes} min"]
        if self.distance_m:
            bits.append(f"{self.distance_m / 1000:.1f} km")
        return " · ".join(bits)


class Match(BaseModel):
    activity: Activity
    week: date
    session_id: str
    moved: bool
    extra_minutes: int = 0  # a brick's run leg
    extra_ids: list[str] = []


class ImportResult(BaseModel):
    matched: list[Match] = []
    extras: list[Activity] = []  # recorded, but nothing planned to match
    duplicates: int = 0
    unreadable: list[str] = []


def _local(ms: float, tz: str) -> datetime:
    return datetime.fromtimestamp(ms / 1000, UTC).astimezone(ZoneInfo(tz)).replace(tzinfo=None)


def parse_fit(data: bytes, tz: str = "Europe/London", activity_id: str | None = None
              ) -> list[Activity]:
    """Sessions in a FIT activity file (a multisport file has several)."""
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.session_message import SessionMessage

    # Read in memory: a temp file can't be reopened while open on Windows.
    try:
        fit = FitFile.from_bytes(data)
    except Exception:  # noqa: BLE001 (some devices write a bad checksum or padding)
        fit = FitFile.from_bytes(data, check_crc=False, allow_trailing_bytes=True)
    out: list[Activity] = []
    for rec in fit.records:
        m = rec.message
        if not isinstance(m, SessionMessage) or m.start_time is None:
            continue
        sport_code = int(m.sport) if m.sport is not None else -1
        sport = SPORTS.get(sport_code)
        if sport is None and sport_code == TRAINING and m.sub_sport is not None \
                and int(m.sub_sport) == STRENGTH_SUB:
            sport = "strength"
        if sport is None:
            continue
        seconds = m.total_timer_time or m.total_elapsed_time or 0
        start = _local(m.start_time, tz)
        out.append(Activity(
            activity_id=f"{activity_id or 'fit'}:{start:%Y%m%dT%H%M}:{sport}",
            start=start, sport=sport, seconds=int(seconds),
            distance_m=int(m.total_distance) if m.total_distance else None,
            avg_hr=int(m.avg_heart_rate) if m.avg_heart_rate else None,
            avg_power=int(m.avg_power) if m.avg_power else None,
        ))
    return out


def read_activity_files(paths: list[Path], tz: str) -> tuple[list[Activity], list[str]]:
    """Read .fit files, .zip exports and folders of them. Returns (activities, unreadable)."""
    acts: list[Activity] = []
    bad: list[str] = []
    files: list[Path] = []
    for p in paths:
        files += sorted(p.rglob("*")) if p.is_dir() else [p]
    for f in files:
        if f.suffix.lower() not in (".fit", ".zip"):
            continue
        try:
            acts += read_bytes(f.name, f.read_bytes(), tz)
        except Exception:  # noqa: BLE001 (one bad file shouldn't stop the rest)
            bad.append(f.name)
    return acts, bad


def read_bytes(name: str, data: bytes, tz: str, activity_id: str | None = None
               ) -> list[Activity]:
    """One uploaded file: a .fit, or a .zip containing .fit files."""
    if name.lower().endswith(".zip") or data[:2] == b"PK":
        out: list[Activity] = []
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for inner in z.namelist():
                if inner.lower().endswith(".fit"):
                    out += parse_fit(z.read(inner), tz, activity_id)
        return out
    return parse_fit(data, tz, activity_id)


def match_activities(
    activities: list[Activity], plans: dict[date, Plan], log: list[LogRow]
) -> ImportResult:
    """Pair each activity with the planned session it most likely was."""
    seen = {r.activity_id for r in log if r.activity_id}
    for r in log:  # each part of a merged brick is also 'seen'
        seen.update(x for x in r.activity_id.split("+") if x)
    logged = {(r.week, r.session_id) for r in log if r.logged}
    result = ImportResult()
    taken: set[tuple[date, str]] = set()
    used: set[str] = set()

    todo = sorted({a.activity_id: a for a in activities}.values(), key=lambda a: a.start)
    result.duplicates = sum(1 for a in todo if a.activity_id in seen)
    todo = [a for a in todo if a.activity_id not in seen]

    def options(a: Activity) -> list[Placement]:
        plan = plans.get(week_start(a.start.date()))
        if plan is None:
            return []
        wk = week_start(a.start.date())
        return [p for p in plan.placements
                if p.session.discipline == a.sport and (wk, p.session.id) not in logged | taken]

    def score(a: Activity, p: Placement) -> tuple[int, float]:
        same_day = p.slot.on == a.start.date()
        return (0 if same_day else 1, abs((p.starts_at - a.start).total_seconds()))

    for a in todo:
        if a.activity_id in used:
            continue
        cands = options(a)
        if not cands:
            result.extras.append(a)
            continue
        best = min(cands, key=lambda p: score(a, p))
        wk = week_start(a.start.date())
        m = Match(activity=a, week=wk, session_id=best.session.id,
                  moved=best.slot.on != a.start.date())
        if best.session.kind == "brick":  # pick up the run straight off the bike
            leg = next((r for r in todo if r.sport == "run" and r.activity_id not in used
                        and timedelta(0) <= r.start - a.end <= BRICK_GAP), None)
            if leg:
                m.extra_minutes, m.extra_ids = leg.minutes, [leg.activity_id]
                used.add(leg.activity_id)
        taken.add((wk, best.session.id))
        used.add(a.activity_id)
        result.matched.append(m)
    return result


def apply_matches(log: list[LogRow], result: ImportResult, source: Source) -> list[LogRow]:
    """Write matched activities into the log rows they belong to."""
    by_key = {(m.week, m.session_id): m for m in result.matched}
    out = []
    for r in log:
        m = by_key.get((r.week, r.session_id))
        if m is None or r.logged:
            out.append(r)
            continue
        a = m.activity
        out.append(r.model_copy(update={
            "status": "moved" if m.moved else "done",
            "actual_min": a.minutes + m.extra_minutes,
            "avg_hr": a.avg_hr, "avg_power": a.avg_power, "distance_m": a.distance_m,
            "source": source, "activity_id": "+".join([a.activity_id, *m.extra_ids]),
        }))
    return out
