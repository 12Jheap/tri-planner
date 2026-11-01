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

from planner.profile import Profile
from planner.sessions import how_to
from planner.solver import Placement, Plan
from planner.workouts import Step, workout_for

FIT_SPORTS = {"swim", "bike", "run"}


def _describe(p: Placement, profile: Profile | None = None) -> str:
    s = p.session
    w = workout_for(s, profile)
    lines = [f"{s.title} · {s.duration_min} min · intensity {s.intensity}/5", how_to(s), ""]
    for b in w.blocks:
        lines.append(f"• {b.summary()}")
        notes = {st.note for st in b.steps if st.note}
        lines += [f"   {n}" for n in notes]
    lines += ["", "Key session: protected when the week changes" if s.key
              else "Flex session: moves first if life happens"]
    if p.reason:
        lines.append(f"Moved: {p.reason.replace('_', ' ')}")
    if not p.facility_ok:
        lines.append("WARNING: facility not available here (time-only experiment week)")
    return "\n".join(lines)


def to_ics(plan: Plan, path: str | Path, tz: str = "Europe/London",
           profile: Profile | None = None) -> Path:
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
        ev.add("description", _describe(p, profile))
        ev.add("dtstamp", dt.datetime.now(tz=zone))
        cal.add_component(ev)
    out = Path(path)
    out.write_bytes(cal.to_ical())
    return out


HR_ZONE = {"recovery": 1, "easy": 2, "steady": 2, "race": 3, "tempo": 3, "threshold": 4, "vo2": 5,
           "sprint": 5}
STEP_KIND = {"Warm-up": "warmup", "Cool-down": "cooldown"}
MAX_STEPS = 60


def _fit_step(step: Step, discipline: str, profile: Profile) -> object:
    """One FIT workout step with the most useful target this athlete has numbers for."""
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import Intensity, WorkoutStepDuration, WorkoutStepTarget

    st = WorkoutStepMessage()
    st.workout_step_name = step.label[:30]
    kind = STEP_KIND.get(step.label, "recovery" if step.zone == "recovery" else "active")
    st.intensity = {"warmup": Intensity.WARMUP, "cooldown": Intensity.COOLDOWN,
                    "recovery": Intensity.RECOVERY, "active": Intensity.ACTIVE}[kind]
    if step.metres:
        st.duration_type = WorkoutStepDuration.DISTANCE
        st.duration_distance = float(step.metres)
    else:
        st.duration_type = WorkoutStepDuration.TIME
        st.duration_time = float(step.seconds)
    notes = " · ".join(x for x in (step.target, step.note) if x)
    if notes:
        st.notes = notes[:100]
    pace = profile.run_pace(step.zone) if discipline == "run" else None
    watts = profile.bike_power(step.zone) if discipline == "bike" else None
    hr = profile.hr(step.zone) if discipline in ("run", "bike") else None
    if pace:  # FIT wants speed in m/s: faster pace = higher speed
        st.target_type = WorkoutStepTarget.SPEED
        st.target_value = 0
        st.custom_target_speed_low = round(1000 / pace[1], 3)
        st.custom_target_speed_high = round(1000 / pace[0], 3)
    elif watts:  # FIT: values above 1000 are watts + 1000
        st.target_type = WorkoutStepTarget.POWER
        st.target_value = 0
        st.custom_target_power_low = watts[0] + 1000
        st.custom_target_power_high = watts[1] + 1000
    elif hr:  # FIT: values above 100 are bpm + 100
        st.target_type = WorkoutStepTarget.HEART_RATE
        st.target_value = 0
        st.custom_target_heart_rate_low = hr[0] + 100
        st.custom_target_heart_rate_high = hr[1] + 100
    elif discipline in ("run", "bike"):
        st.target_type = WorkoutStepTarget.HEART_RATE
        st.target_hr_zone = HR_ZONE[step.zone]
    else:
        st.target_type = WorkoutStepTarget.OPEN
    return st


def to_fit(p: Placement, path: str | Path, profile: Profile | None = None) -> Path | None:
    """Write a structured workout .FIT file. Returns None for unsupported sessions."""
    if p.session.discipline not in FIT_SPORTS:
        return None
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer, Sport

    profile = profile or Profile()
    sport = {"swim": Sport.SWIMMING, "bike": Sport.CYCLING, "run": Sport.RUNNING}
    fid = FileIdMessage()
    fid.type = FileType.WORKOUT
    fid.manufacturer = Manufacturer.DEVELOPMENT.value
    fid.product = 0
    fid.time_created = round(dt.datetime.now(tz=dt.UTC).timestamp() * 1000)
    fid.serial_number = 0x7A1C0001

    workout = workout_for(p.session, profile)
    flat = workout.flat()[:MAX_STEPS]
    discipline = p.session.discipline
    steps = []
    for st in flat:
        # A brick's run-off-the-bike step targets run pace / HR even inside a ride.
        d = "run" if p.session.kind == "brick" and st.label.startswith("Run") else discipline
        steps.append(_fit_step(st, d, profile))

    wk = WorkoutMessage()
    wk.workout_name = f"{p.session.title} {p.session.duration_min}'"[:40]
    wk.sport = sport[discipline]
    wk.num_valid_steps = len(steps)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    builder.add(fid)
    builder.add(wk)
    builder.add_all(steps)
    out = Path(path)
    builder.build().to_file(str(out))
    return out


def export_week(plan: Plan, out_dir: str | Path, tz: str = "Europe/London",
                profile: Profile | None = None) -> dict[str, list[Path]]:
    """Write plan.ics plus one .FIT per supported session into `out_dir`."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.fit"):  # a re-plan must not leave workouts for moved sessions
        old.unlink()
    ics = to_ics(plan, out / "plan.ics", tz, profile)
    fits = []
    for p in plan.placements:
        f = to_fit(p, out / f"{p.slot.on}_{p.session.id}.fit", profile)
        if f is not None:
            fits.append(f)
    return {"ics": [ics], "fit": fits}
