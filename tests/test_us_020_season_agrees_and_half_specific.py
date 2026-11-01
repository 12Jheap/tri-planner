"""US-020: Season and plan agree; half workouts are race-specific (v0)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from planner.adherence import LogRow, write_log
from planner.export import to_fit
from planner.profile import Profile
from planner.service import Workspace
from planner.sessions import build_week_sessions
from planner.solver import Placement
from planner.targets import weekly_targets
from planner.workouts import workout_for

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"
FIT = Profile(run_5k="20:00", swim_css="1:40", ftp=230, threshold_hr=178)


def _ws(tmp_path: Path, race: str = "half") -> Workspace:
    text = EXAMPLE.read_text().replace("race: sprint", f"race: {race}", 1)
    (tmp_path / "athlete.yaml").write_text(text)
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def test_ac_092_planning_a_week_matches_what_season_shows(tmp_path, monkeypatch):
    """AC-092 [e2e-test]: Planning any week targets the same volume the Season view shows for it (one shared rule); weeks planned far ahead say they assume you complete the weeks before, and a past week you didn't log holds volume flat instead of growing it"""
    ws = _ws(tmp_path)
    monkeypatch.setattr(ws, "now", lambda: datetime(2026, 11, 2, 9))
    season = {w.week: w for w in ws.season(date(2026, 11, 2))}
    for wk in (date(2026, 11, 2), date(2026, 11, 16), date(2027, 1, 18), date(2027, 4, 12)):
        res = ws.plan_week(wk)
        assert abs(sum(res.targets.values()) - season[wk].projected_min) <= 10, wk
    far = ws.plan_week(date(2027, 3, 1))
    assert any("Planned ahead" in n for n in far.notes)
    assert not any("Planned ahead" in n for n in ws.plan_week(date(2026, 11, 9)).notes)
    assert season[date(2027, 3, 1)].projected_min > 2 * season[date(2026, 11, 2)].projected_min

    # Logged well: grow from what you did. Barely logged: hold flat, don't grow.
    week = date(2026, 11, 2)
    rows = [LogRow(on=week, week=week, session_id=f"s{i}", discipline="run", slot_key="k",
                   planned_min=60, status="done" if i < 8 else "", actual_min=60)
            for i in range(10)]
    write_log(ws.log_path, rows)
    monkeypatch.setattr(ws, "now", lambda: datetime(2026, 11, 9, 9))
    chain = {c.week: c for c in ws.volume_chain(date(2026, 11, 9), date(2026, 11, 16))}
    assert chain[date(2026, 11, 9)].prev == 8 * 60  # what you did
    write_log(ws.log_path, [r.model_copy(update={"status": "no_response"}) if i > 2 else r
                            for i, r in enumerate(rows)])
    chain = {c.week: c for c in ws.volume_chain(date(2026, 11, 9), date(2026, 11, 16))}
    held = chain[date(2026, 11, 9)].prev
    assert held is not None and held <= chain[date(2026, 11, 2)].projected


def test_ac_093_half_workouts_are_built_for_the_half(tmp_path):
    """AC-093 [unit-test]: Half workouts differ from Olympic ones: race-effort blocks (76–83% FTP) in the long ride, a half-marathon-pace finish to the long run, longer CSS reps, long sweet-spot intervals and a brick that runs at half-marathon effort, with the same targets on the watch"""
    def by_kind(race: str) -> dict[str, object]:
        t = weekly_targets(race, "build", 3000, weekly_hours=14)  # type: ignore[arg-type]
        return {f"{s.discipline}-{s.kind}": s
                for s in build_week_sessions(t, race, "build")}  # type: ignore[arg-type]

    half, oly = by_kind("half"), by_kind("olympic")
    ride = workout_for(half["bike-long"], FIT)  # type: ignore[arg-type]
    race_steps = [st for st in ride.flat() if st.zone == "race"]
    assert len(race_steps) >= 2 and "175–191 W" in race_steps[0].target
    assert not any(st.zone == "race" for st in workout_for(oly["bike-long"], FIT).flat())  # type: ignore[arg-type]
    run = workout_for(half["run-long"], FIT)  # type: ignore[arg-type]
    assert any(st.label == "Half-marathon effort" for st in run.flat())
    css = workout_for(half["swim-css"], FIT)  # type: ignore[arg-type]
    assert any(st.metres == 200 and st.zone == "threshold" for st in css.flat())
    assert any(st.metres == 100 and st.zone == "threshold"
               for st in workout_for(oly["swim-css"], FIT).flat())  # type: ignore[arg-type]
    tempo = workout_for(half["bike-tempo"], FIT)  # type: ignore[arg-type]
    assert max(st.seconds for st in tempo.flat() if st.zone == "tempo") >= 20 * 60
    brick = workout_for(half["bike-brick"], FIT)  # type: ignore[arg-type]
    assert any(st.zone == "race" and st.label.startswith("Run") for st in brick.flat())

    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    cfg_ws = _ws(tmp_path)
    cfg_ws.plan_week(date(2027, 4, 12))
    plan = cfg_ws.plan(date(2027, 4, 12))
    assert plan is not None
    long_ride = next(p for p in plan.placements if p.session.id == "bike-long")
    fit = FitFile.from_file(str(to_fit(long_ride, tmp_path / "r.fit", FIT)))
    steps = [r.message for r in fit.records if isinstance(r.message, WorkoutStepMessage)]
    race = [s for s in steps if s.workout_step_name == "Half race effort"]
    assert race and (race[0].custom_target_value_low, race[0].custom_target_value_high) == \
        (1000 + round(230 * 0.76), 1000 + round(230 * 0.83))
    assert isinstance(long_ride, Placement)


@pytest.mark.parametrize("race", ["sprint", "olympic"])
def test_ac_093_shorter_races_keep_their_own_sessions(race):
    """AC-093 [unit-test]: (shorter races keep their own workouts: no half race-effort blocks)"""
    t = weekly_targets(race, "build", 3000, weekly_hours=10)  # type: ignore[arg-type]
    for s in build_week_sessions(t, race, "build"):  # type: ignore[arg-type]
        assert not any(st.zone == "race" for st in workout_for(s, FIT).flat()), s.id
