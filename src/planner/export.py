"""Get the plan onto your calendar and watch (US-006).

- .ics: one event per session; subscribe to the file or import it.
- .FIT: structured workouts for swim/bike/run that Garmin devices can load
  (copy into the watch's NewFiles folder over USB, or import via Garmin Connect).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from planner.solver import Placement, Plan

FIT_SPORTS = {"swim", "bike", "run"}


def _describe(p: Placement) -> str:
    s = p.session
    lines = [
        f"{s.kind.replace('_', ' ').title()} — {s.duration_min} min, intensity {s.intensity}/5",
        "KEY session (protected)" if s.key else "Flex session (moves first if life happens)",
        f"Needs: {', '.join('/'.join(f.value for f in g) for g in s.requires) or 'nothing'}",
    ]
    if p.reason:
        lines.append(f"Moved: {p.reason}")
    if not p.facility_ok:
        lines.append("WARNING: facility not available here (time-only experiment week)")
    return "\n".join(lines)


def to_ics(plan: Plan, path: str | Path, tz: str = "Europe/London") -> Path:
    zone = ZoneInfo(tz)
    cal = Calendar()
    cal.add("prodid", "-//tri-planner//v0//EN")
    cal.add("version", "2.0")
    cal.add("x-wr-calname", "Training plan")
    for p in plan.placements:
        ev = Event()
        ev.add("uid", f"{p.session.id}-{p.slot.on}@tri-planner")
        ev.add("summary", p.session.label)
        ev.add("dtstart", p.starts_at.replace(tzinfo=zone))
        ev.add("duration", dt.timedelta(minutes=p.session.duration_min))
        ev.add("location", p.slot.location)
        ev.add("description", _describe(p))
        ev.add("dtstamp", dt.datetime.now(tz=zone))
        cal.add_component(ev)
    out = Path(path)
    out.write_bytes(cal.to_ical())
    return out


def _steps(p: Placement) -> list[tuple[str, str, int, int]]:
    """(name, intensity, seconds, hr_zone) steps for a session."""
    s = p.session
    total = s.duration_min * 60
    wu = 600 if s.duration_min >= 40 else 300
    cd = 300
    main = total - wu - cd
    zone = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5}[s.intensity]
    steps: list[tuple[str, str, int, int]] = [("Warm up", "warmup", wu, 1)]
    if s.kind == "threshold" and main >= 900:
        reps = max(2, min(5, main // 720))
        work = (main - (reps - 1) * 180) // reps
        for i in range(reps):
            steps.append((f"Rep {i + 1}/{reps} threshold", "active", work, zone))
            if i < reps - 1:
                steps.append(("Recover easy", "recovery", 180, 1))
    else:
        steps.append((s.kind.replace("_", " ").title(), "active", main, zone))
    steps.append(("Cool down", "cooldown", cd, 1))
    return steps


def to_fit(p: Placement, path: str | Path) -> Path | None:
    """Write a structured workout .FIT file. Returns None for unsupported sessions."""
    if p.session.discipline not in FIT_SPORTS:
        return None
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import (
        FileType,
        Intensity,
        Manufacturer,
        Sport,
        WorkoutStepDuration,
        WorkoutStepTarget,
    )

    sport = {"swim": Sport.SWIMMING, "bike": Sport.CYCLING, "run": Sport.RUNNING}
    intensity = {
        "warmup": Intensity.WARMUP,
        "active": Intensity.ACTIVE,
        "recovery": Intensity.RECOVERY,
        "cooldown": Intensity.COOLDOWN,
    }
    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.time_created = round(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
    fid.serial_number = 0x7A1C0001

    steps = []
    for name, kind, seconds, hr_zone in _steps(p):
        st = WorkoutStepMessage()
        st.workout_step_name = name[:30]
        st.intensity = intensity[kind]
        st.duration_type = WorkoutStepDuration.TIME
        st.duration_time = float(seconds)
        st.target_type = WorkoutStepTarget.HEART_RATE
        st.target_hr_zone = hr_zone
        steps.append(st)

    wk = WorkoutMessage()
    wk.workout_name = p.session.label[:40]
    wk.sport = sport[p.session.discipline]
    wk.num_valid_steps = len(steps)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(fid)
    builder.add(wk)
    builder.add_all(steps)
    out = Path(path)
    builder.build().to_file(str(out))
    return out


def export_week(plan: Plan, out_dir: str | Path, tz: str = "Europe/London") -> dict[str, list[Path]]:
    """Write plan.ics plus one .FIT per supported session into `out_dir`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ics = to_ics(plan, out / "plan.ics", tz)
    fits = []
    for p in plan.placements:
        f = to_fit(p, out / f"{p.slot.on}_{p.session.id}.fit")
        if f is not None:
            fits.append(f)
    return {"ics": [ics], "fit": fits}
