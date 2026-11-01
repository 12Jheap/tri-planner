"""US-019: Half distance (1.9km / 90km / 21.1km) (v0)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

from planner.service import Workspace
from planner.sessions import Session, build_week_sessions
from planner.targets import MAX_HOURS, phase_for, weekly_targets
from planner.web import create_app
from planner.wizard import run_wizard
from planner.workouts import workout_for

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"


def _half(tmp_path: Path, hours: int = 12) -> Workspace:
    text = EXAMPLE.read_text().replace("race: sprint", "race: half", 1)
    text = text.replace("  current_hours: 8", f"  current_hours: {hours}", 1)
    (tmp_path / "athlete.yaml").write_text(text)
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def test_ac_089_half_distance_is_a_race_option_with_bigger_training(tmp_path):
    """AC-089 [e2e-test]: Half distance is a race option (Profile and init) with bike-heavy splits, more volume (10h default, ramping to a 16h ceiling), a 12-week build, and a clear note that half-iron races need you to be 18"""
    base = weekly_targets("half", "base", 3000, weekly_hours=10)
    assert 590 <= sum(base.values()) <= 600 and base["bike"] > base["run"] > base["swim"]
    grown = weekly_targets("half", "base", 3000, previous_week_minutes=15 * 60)
    assert sum(grown.values()) <= MAX_HOURS["half"] * 60 == 960
    assert sum(weekly_targets("sprint", "base", 3000, previous_week_minutes=15 * 60).values()) \
        <= 11 * 60
    race = date(2027, 6, 27)
    assert phase_for(date(2027, 4, 5), race, "half") == "build"  # 12 weeks out
    assert phase_for(date(2027, 4, 5), race, "sprint") == "base"
    ws = _half(tmp_path)
    assert ws.cfg.race == "half"
    page = create_app(ws, now=lambda: datetime(2026, 11, 10, 19)).test_client().get("/setup")
    html = page.get_data(as_text=True)
    assert 'value="half" selected' in html and "18 on race day" in html
    said: list[str] = []
    answers = iter(["Jo", "half", "", "", *[""] * 6, "", "3,5", "", "7-8", *[""] * 6])
    data = run_wizard(lambda _p: next(answers), said.append)
    assert data["race"] == "half" and any("18 on race day" in s for s in said)


def test_ac_090_half_sessions_are_long_course_sessions(tmp_path):
    """AC-090 [unit-test]: Half sessions go long-course: long rides up to 4h, long runs up to 2h with fuelling notes, a long brick as a Key build session with a proper run off the bike, and race-pace (tempo) work rather than sprint-style VO2"""
    t = weekly_targets("half", "build", 3000, weekly_hours=15)
    build = {f"{s.discipline}-{s.kind}": s for s in build_week_sessions(t, "half", "build")}
    assert build["bike-long"].max_min == 240 and build["run-long"].max_min == 120
    assert build["bike-long"].duration_min >= 180 and build["run-long"].duration_min >= 90
    assert build["bike-brick"].key and build["bike-tempo"].key and build["run-tempo"].key
    assert "run-vo2" not in build
    counts: dict[str, int] = defaultdict(int)
    for s in build_week_sessions(t, "half", "build"):
        counts[s.discipline] += 1
    assert counts["swim"] >= 3 and counts["bike"] >= 4 and counts["run"] == 4  # never 5
    brick = workout_for(build["bike-brick"])
    leg = sum(st.seconds for b in brick.blocks for st in b.steps if st.label.startswith("Run"))
    assert leg >= 25 * 60  # settle in, then run at half-marathon effort
    assert any(st.zone == "race" for b in brick.blocks for st in b.steps)
    long_run = Session(id="run-long", discipline="run", kind="long", duration_min=105,
                       intensity=2, requires=[], key=True)
    notes = [st.note for b in workout_for(long_run).blocks for st in b.steps]
    assert any("gel" in n for n in notes)


def test_ac_091_half_weeks_use_double_days_within_the_rules(tmp_path):
    """AC-091 [e2e-test]: A half week on a school timetable uses double days when it needs to, never two sessions of the same sport in a day (a brick counts as a run), keeps the long ride and long run on different days and puts them at the weekend when the slots allow"""
    ws = _half(tmp_path)
    for week in (date(2026, 11, 16), date(2027, 4, 5)):
        res = ws.plan_week(week)
        by_day: dict[date, list[Session]] = defaultdict(list)
        for p in res.plan.placements:
            assert p.slot.on is not None
            by_day[p.slot.on].append(p.session)
        assert sum(1 for ss in by_day.values() if len(ss) >= 2) >= 2  # double days used
        assert res.plan.planned_minutes >= 11 * 60
        for day, ss in by_day.items():
            sports = [s.discipline for s in ss if s.discipline != "strength"]
            sports += ["run" for s in ss if s.kind == "brick"]
            assert len(sports) == len(set(sports)), (week, day, sports)
            assert sum(s.kind == "long" for s in ss) <= 1
        longs = {s.discipline: d for d, ss in by_day.items() for s in ss if s.kind == "long"}
        assert longs["bike"] != longs["run"]
        assert longs["bike"].weekday() >= 5 and longs["run"].weekday() >= 5  # the weekend
