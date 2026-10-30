"""US-006: Export and experiment report (v0)."""

from conftest import make_config, make_session
from icalendar import Calendar

from planner.config import calendar_for_week
from planner.export import export_week, to_fit
from planner.solver import plan_week


def _plan(monday):
    cfg = make_config(
        [
            {"day": "mon", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "wed", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"},
        ]
    )
    sessions = [
        make_session("swim", "swim", 45),
        make_session("bike-thr", "bike", 60, 4),
        make_session("run", "run", 50),
        make_session("strength", "strength", 30, key=False),
    ]
    return plan_week(sessions, calendar_for_week(cfg, monday), cfg)


def test_ac_024_exports_the_week_as_an_ics_file_with_one_event_per_session_t(monday, tmp_path):
    """AC-024 [integration-test]: Exports the week as an .ics file with one event per session (title, duration, location, description)"""
    plan = _plan(monday)
    files = export_week(plan, tmp_path)
    cal = Calendar.from_ical(files["ics"][0].read_bytes())
    events = list(cal.walk("VEVENT"))
    assert len(events) == len(plan.placements) == 4
    by_uid = {str(e["uid"]): e for e in events}
    for pl in plan.placements:
        ev = by_uid[f"{pl.session.id}-{pl.slot.on}@tri-planner"]
        assert str(ev["summary"]) == pl.session.label
        assert ev.decoded("duration").total_seconds() == pl.session.duration_min * 60
        assert str(ev["location"]) == pl.slot.location
        assert "intensity" in str(ev["description"])
        assert ev.decoded("dtstart").replace(tzinfo=None) == pl.starts_at


def test_ac_025_exports_structured_workouts_as_fit_files_where_the_session_t(monday, tmp_path):
    """AC-025 [integration-test]: Exports structured workouts as .FIT files where the session type supports it"""
    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_message import WorkoutMessage
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage

    plan = _plan(monday)
    files = export_week(plan, tmp_path)
    assert len(files["fit"]) == 3  # swim, bike, run — strength isn't a FIT workout
    strength = plan.placement("strength")
    assert to_fit(strength, tmp_path / "s.fit") is None
    bike = plan.placement("bike-thr")
    fit = FitFile.from_file(str(to_fit(bike, tmp_path / "bike.fit")))
    msgs = [r.message for r in fit.records]
    workout = next(m for m in msgs if isinstance(m, WorkoutMessage))
    steps = [m for m in msgs if isinstance(m, WorkoutStepMessage)]
    assert workout.sport.name == "CYCLING" if hasattr(workout.sport, "name") else workout.sport == 2
    assert len(steps) == workout.num_valid_steps >= 4  # warm-up, reps, cool-down
    assert abs(sum(s.duration_time for s in steps) - 60 * 60) < 1


def test_ac_026_experiment_mode_alternates_facility_aware_and_time_only_week():
    """AC-026 [unit-test]: Experiment mode alternates facility-aware and time-only weeks on a fixed schedule"""
    raise NotImplementedError("Not implemented — AC-026 pending")


def test_ac_027_weekly_report_shows_completion_ratio_by_week_type_by_slot_an():
    """AC-027 [e2e-test]: Weekly report shows completion ratio by week type, by slot, and by discipline"""
    raise NotImplementedError("Not implemented — AC-027 pending")
