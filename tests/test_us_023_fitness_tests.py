"""US-023: Fitness tests keep your zones current (v0)."""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from conftest import make_config, scrape_setup_form

from planner.config import Facility, load_config
from planner.export import to_fit
from planner.fitness import apply_tests, can_test
from planner.fitness import test_requires as needs_for
from planner.fitness import tests_due as due_tests
from planner.replan import Injury
from planner.service import PlannerError, Workspace
from planner.sessions import build_week_sessions
from planner.targets import is_recovery_week, phase_for, weekly_targets
from planner.web import create_app
from planner.workouts import workout_for

FIXTURE = Path(__file__).parent / "fixtures" / "short_weekday_slots.yaml"  # no swim CSS yet
START = date(2026, 11, 2)  # first week on the plan
WEEK = date(2026, 11, 23)


def _ws(tmp_path: Path, now: datetime | None = None) -> Workspace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, tmp_path / "athlete.yaml")
    ws = Workspace(tmp_path / "athlete.yaml", tmp_path / "out")
    if now is not None:
        ws.now = lambda: now  # type: ignore[method-assign]
    return ws


def _client(ws: Workspace, now: datetime):
    client = create_app(ws, now=lambda: now, background=False).test_client()
    html = client.get("/setup").get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)  # type: ignore[union-attr]
    return client, token


def test_ac_100_a_test_is_planned_when_a_number_is_missing_or_stale(tmp_path):
    """AC-100 [e2e-test]: A fitness test is planned when a number is missing or 8+ weeks old, in place of that sport's quality session; at most two in a week; never in a recovery, taper, race or time-only week, for a paused sport, for something you can't measure, or when switched off"""
    cfg = load_config(FIXTURE)
    assert due_tests(cfg, WEEK, START) == ["swim"]  # no CSS: due now; 5k and FTP are 3 weeks old
    stale = due_tests(cfg, START + timedelta(weeks=8), START)
    assert stale[0] == "swim" and len(stale) == 2  # missing first, then the oldest; two at most
    cfg.profile.swim_css = 105
    cfg.profile.tested = {"swim": WEEK, "run": date(2026, 12, 20)}
    assert due_tests(cfg, START + timedelta(weeks=8), START) == ["bike"]  # dated ones aren't due
    cfg.fitness_tests = False
    assert due_tests(cfg, START + timedelta(weeks=8), START) == []
    outdoors = make_config(
        [{"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"}],
        locations=[{"name": "Home", "facilities": ["road_bike", "outdoor_run", "open_water"]}])
    assert can_test(outdoors, "run") and not can_test(outdoors, "swim")  # no measured pool
    assert not can_test(outdoors, "bike")  # no power to measure
    assert due_tests(outdoors, WEEK, None) == ["run"]

    sessions = build_week_sessions(weekly_targets("half", "base", 1500, weekly_hours=9),
                                   "half", "base")
    cfg = load_config(FIXTURE)
    swapped, notes = apply_tests(sessions, ["swim"], cfg)
    ids = {s.id for s in swapped}
    assert "swim-test" in ids and "swim-css" not in ids and len(swapped) == len(sessions)
    assert notes and "CSS swim test" in notes[0] and "replaces" in notes[0]

    ws = _ws(tmp_path, datetime(2026, 11, 20, 18))
    res = ws.plan_week(WEEK)
    planned = {p.session.id for p in res.plan.placements}
    assert "swim-test" in planned and "swim-css" not in planned
    assert any("Fitness test this week" in n for n in res.notes)
    race = ws.cfg.race_date
    recovery = next(START + timedelta(weeks=i) for i in range(4, 30)
                    if is_recovery_week(START + timedelta(weeks=i), race))
    taper = next(START + timedelta(weeks=i) for i in range(4, 40)
                 if phase_for(START + timedelta(weeks=i), race, "half") == "taper")
    for quiet in (recovery, taper):
        assert not any(p.session.kind == "test" for p in ws.plan_week(quiet).plan.placements)
    time_only = ws.plan_week(WEEK, experiment_start=WEEK - timedelta(days=7))
    assert time_only.week_type == "time_only"
    assert not any(p.session.kind == "test" for p in time_only.plan.placements)
    ws.injuries().declare([Injury(discipline="swim", until=WEEK + timedelta(days=10))], [],
                          WEEK)
    assert not any(p.session.kind == "test" for p in ws.plan_week(WEEK).plan.placements)


def test_ac_101_test_sessions_are_proper_tests_in_the_right_place(tmp_path):
    """AC-101 [integration-test]: Test sessions are real protocols (a 5 km time trial as a distance step, a 20-minute all-out bike test, a 400 m + 200 m swim test) and only go where they can be measured: a pool for the swim, the wattbike for power"""
    cfg = load_config(FIXTURE)
    assert needs_for(cfg, "swim") == [[Facility.POOL]]
    assert needs_for(cfg, "bike") == [[Facility.WATTBIKE]]
    sessions, _ = apply_tests(
        build_week_sessions(weekly_targets("half", "base", 1500, weekly_hours=9), "half", "base"),
        ["swim", "run", "bike"], cfg)
    tests = {s.discipline: s for s in sessions if s.kind == "test"}
    assert set(tests) == {"swim", "run", "bike"} and all(t.key and t.hard for t in tests.values())
    run = workout_for(tests["run"], cfg.profile)
    trial = next(st for st in run.flat() if st.label == "Time trial")
    assert trial.metres == 5000 and "23:15" in trial.target  # last time, to beat
    bike = workout_for(tests["bike"], cfg.profile)
    assert any(st.seconds == 20 * 60 and "All-out" in st.label for st in bike.flat())
    swim = workout_for(tests["swim"], cfg.profile)
    assert [st.metres for st in swim.flat() if st.label == "Time trial"] == [400, 200]
    assert tests["run"].title == "5k time trial" and tests["bike"].title == "FTP test"

    ws = _ws(tmp_path, datetime(2026, 11, 20, 18))
    plan = ws.plan_week(WEEK).plan
    placed = plan.placement("swim-test")
    assert placed is not None and placed.slot.location == "School"  # the only pool
    assert placed.session.duration_min <= placed.slot.minutes == 45

    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    from fit_tool.profile.profile_type import WorkoutStepDuration
    run_plan = placed.model_copy(update={"session": tests["run"]})
    fit = FitFile.from_file(str(to_fit(run_plan, tmp_path / "tt.fit", cfg.profile)))
    steps = [r.message for r in fit.records if isinstance(r.message, WorkoutStepMessage)]
    tt = next(s for s in steps if s.workout_step_name == "Time trial")
    assert tt.duration_type == WorkoutStepDuration.DISTANCE.value and tt.duration_distance == 5000


def test_ac_102_entering_a_result_updates_zones_everywhere(tmp_path):
    """AC-102 [e2e-test]: After a test, Today asks for the result; saving it updates the number (CSS from the 400 m and 200 m times, FTP as 95% of the 20-minute power), the date measured, your zones, the history and this week's calendar and watch files; a bad result changes nothing; the next test is due 8 weeks later"""
    now = datetime(2026, 11, 27, 20)
    ws = _ws(tmp_path, now)
    ws.plan_week(WEEK)
    test = ws.plan(WEEK).placement("swim-test")  # type: ignore[union-attr]
    assert test is not None
    day = test.slot.on
    ics = ws.out / str(WEEK) / "plan.ics"
    assert "/100m" not in ics.read_text()  # swims are by feel until there's a CSS
    assert "swim" in ws.tests_due(WEEK + timedelta(days=7))  # not done yet: still due
    client, token = _client(ws, now)
    assert "Enter your result" not in client.get("/").get_data(as_text=True)
    ws.log_session(WEEK, "swim-test", "done")
    assert "swim" not in ws.tests_due(WEEK + timedelta(days=7))  # done: wait for the result
    home = client.get("/").get_data(as_text=True)
    assert "Enter your result" in home and "css swim test" in home
    page = client.get(f"/s/{WEEK}/swim-test").get_data(as_text=True)
    assert "Your result" in page and 'name="t400"' in page and 'name="t200"' in page

    before = ws.config_path.read_text()
    for bad in ({"t400": "abc", "t200": "3:30"}, {"t400": "3:00", "t200": "3:30"},
                {"t400": "7:10", "t200": ""}):
        res = client.post("/fitness/result", data={"token": token, "sport": "swim",
                                                   "on": str(day), **bad})
        assert res.status_code == 302 and ws.config_path.read_text() == before
    with pytest.raises(PlannerError):
        ws.record_test("bike", {"p20": "2000"}, day)

    res = client.post("/fitness/result", data={
        "token": token, "sport": "swim", "on": str(day), "t400": "7:10", "t200": "3:30",
        "next": f"/s/{WEEK}/swim-test"}, follow_redirects=True)
    saved = res.get_data(as_text=True)
    assert "Swim CSS" in saved and "1:50/100m" in saved and "Result saved" in saved
    prof = ws.cfg.profile
    assert prof.swim_css == (430 - 210) // 2 and prof.tested["swim"] == day
    assert prof.run_5k == 23 * 60 + 15 and prof.ftp == 220  # everything else untouched
    assert "/100m" in ics.read_text().replace("\r\n ", "")  # this week's swims now have paces
    assert ws.pending_results(now.date()) == []

    assert ws.record_test("bike", {"p20": "240"}, now.date()).after == "228 W"  # 95% of 240
    change = ws.record_test("run", {"time": "22:40"}, now.date())
    assert change.before == "23:15" and change.after == "22:40" and "/km" in change.zone_line
    assert ws.cfg.profile.run_5k == 22 * 60 + 40
    ws.record_test("run", {"time": "22:10"}, now.date())
    progress = client.get("/progress").get_data(as_text=True)
    assert "Fitness" in progress and "1:50/100m" in progress and "22:10" in progress
    assert "faster" in progress and "first test" in progress
    assert ws.tests_due(WEEK + timedelta(weeks=7)) == []  # nothing is due for 8 weeks
    assert ws.tests_due(WEEK + timedelta(weeks=8)) == ["swim", "bike"]  # oldest first, two at most


def test_ac_103_profile_edits_are_dated_and_tests_can_be_switched_off(tmp_path):
    """AC-103 [e2e-test]: Changing a fitness number on Profile counts as measuring it today (unchanged numbers keep their dates), and fitness tests can be switched off there"""
    now = datetime(2026, 11, 20, 18)
    ws = _ws(tmp_path, now)
    ws.record_test("bike", {"p20": "240"}, date(2026, 11, 10))
    client, token = _client(ws, now)
    form = scrape_setup_form(client.get("/setup").get_data(as_text=True))
    form["token"] = [token]
    assert client.post("/setup", data=form).status_code == 302  # saved unchanged
    ws.reload()
    assert ws.cfg.profile.tested == {"bike": date(2026, 11, 10)}  # nothing re-dated
    form["p-run_5k"] = ["22:30"]
    form["no_tests"] = ["1"]
    assert client.post("/setup", data=form).status_code == 302
    ws.reload()
    assert ws.cfg.profile.run_5k == 22 * 60 + 30
    assert ws.cfg.profile.tested == {"bike": date(2026, 11, 10), "run": now.date()}
    assert ws.cfg.fitness_tests is False
    html = client.get("/setup").get_data(as_text=True)
    assert re.search(r'name="no_tests" value="1" checked', html)
    assert not any(p.session.kind == "test" for p in ws.plan_week(WEEK).plan.placements)
    assert "switched off on Profile" in client.get("/progress").get_data(as_text=True)
