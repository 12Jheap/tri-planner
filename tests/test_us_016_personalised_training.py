"""US-016: Personalised sessions planned into your availability (v0)."""

from __future__ import annotations

import re
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path

import pytest
from conftest import make_config

from planner.config import calendar_for_week
from planner.export import to_fit, to_ics
from planner.profile import ZONES, Profile
from planner.service import Workspace
from planner.sessions import BIKE_KIT, SWIM_KIT, Session, build_week_sessions
from planner.solver import fill_slots, plan_week
from planner.targets import is_recovery_week, weekly_targets
from planner.web import create_app
from planner.workouts import workout_for

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"
FIT = Profile(run_5k="20:00", swim_css="1:40", ftp=230, threshold_hr=178)


def _joe(tmp_path: Path, **profile: object) -> Workspace:
    text = EXAMPLE.read_text()
    if profile:
        lines = "".join(f"  {k}: {v!r}\n" for k, v in profile.items())
        text = text.replace("profile:\n", "profile:\n" + lines, 1)
    (tmp_path / "athlete.yaml").write_text(text)
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def test_ac_071_fitness_numbers_give_personal_non_overlapping_zones():
    """AC-071 [unit-test]: A 5k time, swim CSS (or 400m + 200m time trials), FTP and threshold or max HR give personal run pace, swim pace, bike power and HR zones that don't overlap; missing numbers fall back to effort; impossible numbers are rejected"""
    p = FIT
    assert p.run_threshold_pace == pytest.approx(240 * 1.06)  # 4:00/km 5k pace
    assert p.target("run", "threshold") == "4:09–4:22/km · HR 169–178"
    assert p.bike_power("threshold") == (218, 242)  # 95–105% FTP
    assert p.swim_pace("threshold") == (99, 102)  # CSS 1:40 −1/+2 s
    for name in ("run_pace", "bike_power", "swim_pace", "hr"):
        get = getattr(p, name)
        bands = [get(z) for z in ZONES if get(z)]
        if name in ("run_pace", "swim_pace"):  # paces: smaller = faster, so flip them
            bands = [(-slow, -fast) for fast, slow in bands]
        for lower, upper in pairwise(bands):  # each zone sits above the last
            assert upper[0] >= lower[1] - 1e-9, (name, lower, upper)
    assert Profile(swim_400="7:20", swim_200="3:30").swim_css == 115  # (440 − 210) / 2
    assert Profile(max_hr=200).hr("easy") == (130, 144)
    nothing = Profile()
    assert nothing.target("run", "threshold").startswith("effort 7–8/10")
    assert nothing.known == [] and FIT.known == ["run", "bike", "swim", "hr"]
    yaml_seconds = Profile(run_5k=1290)  # unquoted 21:30 in YAML arrives as 1290
    assert yaml_seconds.run_5k == 21 * 60 + 30
    for bad in ({"run_5k": "5:00"}, {"ftp": 2000}, {"swim_400": "3:00", "swim_200": "3:30"},
                {"threshold_hr": 40}):
        with pytest.raises(ValueError):
            Profile(**bad)  # type: ignore[arg-type]


def test_ac_072_every_phase_has_the_right_quality_work_and_recovery_weeks():
    """AC-072 [unit-test]: Base has tempo, sweet-spot and CSS work; build adds threshold Key sessions plus VO2 and a brick; taper keeps short race-pace openers; every 4th week before the race is a lighter recovery week with no hard sessions"""
    def kinds(phase: str, recovery: bool = False) -> dict[str, Session]:
        t = weekly_targets("sprint", phase, 1500, weekly_hours=9,  # type: ignore[arg-type]
                           recovery=recovery)
        return {f"{s.discipline}-{s.kind}": s for s in
                build_week_sessions(t, "sprint", phase, recovery)}  # type: ignore[arg-type]

    base = kinds("base")
    assert {"run-tempo", "bike-tempo", "swim-css"} <= set(base)
    assert all(base[k].key and base[k].intensity == 3 for k in ("run-tempo", "bike-tempo"))
    build = kinds("build")
    assert all(build[k].key and build[k].hard for k in ("run-threshold", "bike-threshold",
                                                         "swim-css"))
    assert {"run-vo2", "bike-brick"} <= set(build)
    assert build["bike-brick"].requires[1]  # a brick needs bike AND run kit
    taper = kinds("taper")
    assert {"run-openers", "bike-openers", "swim-race_pace"} <= set(taper)
    assert max(s.duration_min for s in taper.values()) <= 45
    recovery = kinds("base", recovery=True)
    assert recovery and not any(s.hard or s.intensity >= 3 for s in recovery.values())
    race = date(2027, 6, 27)
    weeks_out = {n: date.fromordinal(race.toordinal() - 7 * n) for n in range(1, 20)}
    recovery_weeks = [n for n, wk in weeks_out.items() if is_recovery_week(wk, race)]
    assert recovery_weeks == [5, 9, 13, 17]  # 3 loading weeks, 1 easier; none in the run-in
    assert sum(weekly_targets("sprint", "base", 1500, weekly_hours=9, recovery=True).values()) \
        < 0.75 * sum(weekly_targets("sprint", "base", 1500, weekly_hours=9).values())


def test_ac_073_structured_workouts_with_targets_on_screen_calendar_and_watch(tmp_path):
    """AC-073 [integration-test]: Every session is a structured workout (warm-up, main set, cool-down) that adds up to its planned length, with targets from your zones, and the same steps and targets go into the calendar event and the .FIT file"""
    for phase in ("base", "build", "taper"):
        t = weekly_targets("olympic", phase, 1500, weekly_hours=10)  # type: ignore[arg-type]
        for s in build_week_sessions(t, "olympic", phase):  # type: ignore[arg-type]
            w = workout_for(s, FIT)
            if s.discipline != "swim":  # swims are sets in metres, sized to the time
                assert abs(w.seconds - s.duration_min * 60) <= 2, s.id
            else:
                assert abs(w.seconds - s.duration_min * 60) <= 6 * 60 and w.metres >= 800
            assert len(w.blocks) >= 1 and w.summary
    thr = Session(id="run-threshold", discipline="run", kind="threshold", duration_min=45,
                  intensity=4, requires=[], key=True)
    w = workout_for(thr, FIT)
    assert [b.steps[0].label for b in w.blocks][:2] == ["Warm-up", "Threshold"]
    assert w.blocks[1].reps >= 3 and "4:09–4:22/km" in w.summary
    assert workout_for(thr).blocks[1].steps[0].target.startswith("effort")

    cfg = make_config([{"day": "mon", "start": "16:15", "end": "18:15", "location": "Home"}])
    from conftest import MONDAY
    plan = plan_week([thr], calendar_for_week(cfg, MONDAY), cfg)
    ics = to_ics(plan, tmp_path / "p.ics", profile=FIT).read_text()
    assert "Threshold" in ics and "4:09–4:22/km" in ics.replace("\r\n ", "")

    from fit_tool.fit_file import FitFile
    from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
    fit = FitFile.from_file(str(to_fit(plan.placements[0], tmp_path / "r.fit", FIT)))
    steps = [r.message for r in fit.records if isinstance(r.message, WorkoutStepMessage)]
    reps = [s for s in steps if s.workout_step_name == "Threshold"]
    assert len(reps) == w.blocks[1].reps
    fast, slow = FIT.run_pace("threshold")  # type: ignore[misc]
    assert reps[0].custom_target_value_low == pytest.approx(1000 / slow, abs=0.01)
    assert reps[0].custom_target_value_high == pytest.approx(1000 / fast, abs=0.01)
    ride = Session(id="bike-threshold", discipline="bike", kind="threshold", duration_min=60,
                   intensity=4, requires=[], key=True)
    bplan = plan_week([ride], calendar_for_week(cfg, MONDAY), cfg)
    bfit = FitFile.from_file(str(to_fit(bplan.placements[0], tmp_path / "b.fit", FIT)))
    bsteps = [r.message for r in bfit.records if isinstance(r.message, WorkoutStepMessage)]
    work = next(s for s in bsteps if s.workout_step_name == "Threshold")
    assert (work.custom_target_value_low, work.custom_target_value_high) == (1218, 1242)


def test_ac_074_availability_drives_the_plan_and_spare_slot_time_is_used(monday):
    """AC-074 [unit-test]: Sessions are fitted into your free slots and aerobic sessions grow into spare slot time up to the week's budget, never past a session's maximum, the next session, or a facility's opening hours; volume grows from what you train now and what you actually did"""
    cfg = make_config(
        [
            {"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"},
            {"day": "tue", "start": "16:00", "end": "18:00", "location": "School"},
        ]
    )
    long_ride = Session(id="bike-long", discipline="bike", kind="long", duration_min=60,
                        intensity=2, requires=[BIKE_KIT], key=True, min_min=60, max_min=120)
    swim = Session(id="swim-endurance", discipline="swim", kind="endurance", duration_min=30,
                   intensity=2, requires=[SWIM_KIT], key=False, min_min=25, max_min=60)
    tempo = Session(id="bike-tempo", discipline="bike", kind="tempo", duration_min=45,
                    intensity=3, requires=[BIKE_KIT], key=True, max_min=75)
    plan = plan_week([long_ride, swim, tempo], calendar_for_week(cfg, monday), cfg)
    filled, added = fill_slots(plan, cfg, {"bike": 200, "swim": 200})
    got = {p.session.id: p for p in filled.placements}
    assert got["bike-long"].session.duration_min == 120  # grew to its maximum
    assert got["bike-tempo"].session.duration_min == 45  # intervals keep their shape
    swim_end = got["swim-endurance"].end  # School pool shuts at 19:00, slot ends 18:00
    assert swim_end <= got["swim-endurance"].slot.end
    assert sum(p.session.duration_min for p in filled.placements
               if p.session.discipline == "bike") <= 45 + 120
    assert added > 0
    capped, _ = fill_slots(plan, cfg, {"bike": 150, "swim": 30})
    assert sum(p.session.duration_min for p in capped.placements
               if p.session.discipline == "bike") == 150  # stops at the sport's budget
    # Volume: starts from what you train now, then grows ≤10% on what you actually did.
    first = sum(weekly_targets("sprint", "base", 3000, weekly_hours=6).values())
    assert first <= 360
    after = sum(weekly_targets("sprint", "base", 3000, previous_week_minutes=400).values())
    assert 400 < after <= 440
    huge = weekly_targets("sprint", "base", 3000, weekly_hours=6)
    assert sum(huge.values()) < 0.2 * 3000  # 50h free still isn't a 40h plan


def test_ac_075_coaching_rules_hold_across_a_real_season(tmp_path):
    """AC-075 [e2e-test]: Across a real season: no hard session on the same day as a long one, long ride and long run on different days, nothing on race day, and a packed exam week keeps its most valuable sessions instead of failing"""
    ws = _joe(tmp_path)
    for week in (date(2026, 11, 9), date(2027, 3, 1), date(2027, 5, 3), date(2027, 5, 17)):
        res = ws.plan_week(week)
        by_day: dict[date | None, list[Session]] = {}
        for p in res.plan.placements:
            by_day.setdefault(p.slot.on, []).append(p.session)
        for day, sessions in by_day.items():
            longs = [s for s in sessions if s.kind == "long"]
            assert len(longs) <= 1, (week, day)
            if longs:
                assert not any(s.hard for s in sessions), (week, day)
            assert sum(s.hard for s in sessions) <= 1
    race = ws.plan_week(date(2027, 6, 21))
    assert race.plan.placements and all(p.slot.on < date(2027, 6, 27)
                                        for p in race.plan.placements)
    assert race.notes and "Race week" in race.notes[0]
    assert race.filled_min == 0  # a taper isn't padded out
    exams = ws.plan_week(date(2027, 5, 31))  # 3 short slots in exam season
    assert exams.plan.placements and any("Busy week" in n for n in exams.notes)


def test_ac_076_profile_and_session_pages_show_personal_targets_without_emoji(tmp_path):
    """AC-076 [e2e-test]: The profile page asks for current fitness and shows your zones; each session page shows why, a zone timeline and every step with your targets; the interface uses no emoji"""
    ws = _joe(tmp_path, run_5k="20:00", ftp=230, threshold_hr=178)
    app = create_app(ws, now=lambda: datetime(2026, 11, 10, 19, 0))
    client = app.test_client()
    profile = client.get("/setup").get_data(as_text=True)
    assert "Current fitness" in profile and "Your zones" in profile
    assert "4:09–4:22" in profile and "218–242" in profile
    token = re.search(r'name="token" value="([^"]+)"', profile).group(1)  # type: ignore[union-attr]
    client.post("/week/plan", data={"token": token, "week": "2026-11-09"})
    plan = ws.plan(date(2026, 11, 9))
    assert plan is not None
    tempo = next(p for p in plan.placements if p.session.kind == "tempo"
                 and p.session.discipline == "run")
    page = client.get(f"/s/2026-11-09/{tempo.session.id}").get_data(as_text=True)
    assert "comfortably hard" in page and 'class="timeline"' in page
    assert "Warm-up" in page and "Cool-down" in page and "/km" in page
    emoji = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]")
    for url in ("/", "/week", "/replan", "/progress", "/setup", f"/s/2026-11-09/{tempo.session.id}"):
        html = client.get(url).get_data(as_text=True)
        assert not emoji.findall(html), (url, emoji.findall(html)[:3])
