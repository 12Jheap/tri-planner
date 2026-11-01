"""US-018: Strength opt-out, auto-sync, recovery check, Garmin heart rates, effort check (v0)."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from planner.adherence import LogRow
from planner.profile import Profile
from planner.service import PlannerError, Workspace, effort_note
from planner.sessions import REQUIRES, Session
from planner.targets import weekly_targets
from planner.web import create_app
from planner.wellness import Wellness, heart_rates_from_garmin, parse_wellness, readiness

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"
WEEK = date(2026, 11, 9)

# Shaped like Garmin Connect's responses for these endpoints.
SLEEP = {"dailySleepDTO": {"sleepTimeSeconds": 5 * 3600 + 40 * 60,
                           "sleepScores": {"overall": {"value": 52, "qualifierKey": "POOR"}}}}
HRV = {"hrvSummary": {"lastNightAvg": 48, "status": "LOW",
                      "baseline": {"balancedLow": 55, "balancedUpper": 72}}}
HEART = {"restingHeartRate": 58, "lastSevenDaysAvgRestingHeartRate": 51}
GOOD = ({"dailySleepDTO": {"sleepTimeSeconds": 8 * 3600, "sleepScores": {"overall":
                                                                         {"value": 84}}}},
        {"hrvSummary": {"lastNightAvg": 66, "status": "BALANCED", "baseline": {
            "balancedLow": 55}}},
        {"restingHeartRate": 50, "lastSevenDaysAvgRestingHeartRate": 51})


def getter(sleep: Any = SLEEP, hrv: Any = HRV, heart: Any = HEART, zones: Any = None,
           settings: Any = None):
    calls: list[str] = []

    def get(requests):
        out = []
        for path, _params in requests:
            calls.append(path)
            out.append({"/sleep-service/sleep/dailySleep": sleep,
                        "/wellness-service/wellness/dailyHeartRate": heart,
                        "/biometric-service/heartRateZones/v2": zones,
                        "/userprofile-service/userprofile/settings": settings,
                        }.get(path, hrv if path.startswith("/hrv-service/") else None))
        return out

    get.calls = calls  # type: ignore[attr-defined]
    return get


def _joe(tmp_path: Path, extra: str = "", profile: str = "") -> Workspace:
    text = EXAMPLE.read_text()
    if extra:
        text = text.replace("timezone: Europe/London\n", f"timezone: Europe/London\n{extra}\n", 1)
    if profile:
        text = text.replace("profile:\n", f"profile:\n  {profile}\n", 1)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "athlete.yaml").write_text(text)
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def _token(client) -> str:
    html = client.get("/setup").get_data(as_text=True)
    return re.search(r'name="token" value="([^"]+)"', html).group(1)  # type: ignore[union-attr]


def test_ac_083_you_can_opt_out_of_strength_sessions(tmp_path):
    """AC-083 [e2e-test]: Profile lets you opt out of strength sessions; none are planned and their time goes to swim, bike and run, so the week isn't shorter"""
    with_s = weekly_targets("sprint", "base", 1500, weekly_hours=8)
    without = weekly_targets("sprint", "base", 1500, weekly_hours=8, strength=False)
    assert without["strength"] == 0 and with_s["strength"] > 0
    assert abs(sum(without.values()) - sum(with_s.values())) <= 10
    assert all(without[d] >= with_s[d] for d in ("swim", "bike", "run"))
    ws = _joe(tmp_path, "strength: false")
    res = ws.plan_week(WEEK)
    assert not any(p.session.discipline == "strength" for p in res.plan.placements)
    assert res.plan.planned_minutes >= 0.9 * _joe(tmp_path / "b").plan_week(WEEK).plan.planned_minutes
    app = create_app(ws, now=lambda: datetime(2026, 11, 10, 19))
    html = app.test_client().get("/setup").get_data(as_text=True)
    assert "Don't give me strength sessions" in html
    assert re.search(r'name="no_strength" value="1" checked', html)


def test_ac_084_opening_the_app_syncs_with_garmin_at_most_every_30_minutes(tmp_path):
    """AC-084 [e2e-test]: Opening Today syncs with Garmin in the background at most every 30 minutes (activities and this morning's recovery data); the time of the last sync is shown, and a failed sync never breaks the page"""
    ws = _joe(tmp_path)
    ws.plan_week(WEEK)
    clock = {"now": datetime(2026, 11, 10, 7, 0)}
    fetches: list[tuple[date, date]] = []

    def fetch(start, end):
        fetches.append((start, end))
        return []

    get = getter()
    app = create_app(ws, now=lambda: clock["now"], garmin_fetch=fetch, garmin_get=get,
                     background=False)
    client = app.test_client()
    page = client.get("/").get_data(as_text=True)
    assert len(fetches) == 1 and "Synced 07:00" in page
    assert ws.wellness(date(2026, 11, 10)) is not None
    clock["now"] += timedelta(minutes=20)
    client.get("/")
    assert len(fetches) == 1  # too soon
    clock["now"] += timedelta(minutes=15)
    client.get("/")
    assert len(fetches) == 2

    def broken(start, end):
        raise RuntimeError("network down")

    bad = create_app(ws, now=lambda: clock["now"] + timedelta(hours=2), garmin_fetch=broken,
                     garmin_get=get, background=False)
    assert bad.test_client().get("/").status_code == 200  # still works


def test_ac_085_recovery_check_reads_sleep_hrv_and_resting_hr(tmp_path):
    """AC-085 [unit-test]: The recovery check reads last night's sleep, HRV and resting heart rate from Garmin and applies three plain rules (2+ flags = low, 1 = watch, 0 = good); missing data is "not available", never an alarm"""
    day = date(2026, 11, 10)
    w = parse_wellness(day, SLEEP, HRV, HEART)
    assert (w.sleep_score, w.sleep_hours, w.hrv, w.hrv_status, w.hrv_low) == (52, 5.7, 48, "LOW",
                                                                             55)
    assert (w.resting_hr, w.resting_hr_usual) == (58, 51)
    low = readiness(w)
    assert low.level == "low" and len(low.flags) == 3
    good = readiness(parse_wellness(day, *GOOD))
    assert good.level == "good" and not good.flags and len(good.fine) == 3
    one = readiness(Wellness(day=day, sleep_hours=5.5, hrv=70, hrv_low=55))
    assert one.level == "watch"
    assert readiness(None).level == "unknown"
    assert readiness(parse_wellness(day, None, None, None)).level == "unknown"
    assert readiness(parse_wellness(day, {"unexpected": True}, [], {})).level == "unknown"
    only_hr = readiness(parse_wellness(day, None, None, HEART))
    assert only_hr.level == "watch"  # one flag from the one thing we know


def test_ac_086_on_a_low_day_it_offers_to_make_a_hard_session_easy(tmp_path):
    """AC-086 [e2e-test]: On a low-recovery day with a quality session planned, Today offers to make it easy (same time, place and sport, easy effort); nothing changes unless you press it, and logged or already-easy sessions can't be eased"""
    ws = _joe(tmp_path)
    ws.plan_week(WEEK)
    plan = ws.plan(WEEK)
    assert plan is not None
    quality = next(p for p in plan.placements if p.session.intensity >= 3
                   and p.session.discipline != "strength")
    day = quality.slot.on
    assert day is not None
    now = datetime.combine(day, datetime.min.time()).replace(hour=6)
    app = create_app(ws, now=lambda: now, garmin_fetch=lambda s, e: [], garmin_get=getter(),
                     background=False)
    client = app.test_client()
    page = client.get("/").get_data(as_text=True)
    assert "You look under-recovered" in page and "not a diagnosis" in page
    assert f"Make {quality.session.title.lower()} easy" in page
    assert ws.plan(WEEK).placement(quality.session.id).session.kind == quality.session.kind  # type: ignore[union-attr]
    client.post("/ease", data={"token": _token(client), "week": str(WEEK),
                               "session": quality.session.id, "next": "/"})
    eased = ws.plan(WEEK).placement(quality.session.id)  # type: ignore[union-attr]
    assert eased is not None and eased.session.intensity <= 2 and not eased.session.key
    assert (eased.slot.on, eased.start, eased.session.duration_min) == (
        quality.slot.on, quality.start, quality.session.duration_min)
    assert eased.session.kind in ("easy", "endurance") and eased.reason == "made_easy"
    with pytest.raises(PlannerError, match="already easy"):
        ws.ease_session(WEEK, quality.session.id)
    other = next(p for p in ws.plan(WEEK).placements  # type: ignore[union-attr]
                 if p.session.intensity >= 3 and p.session.id != quality.session.id
                 and p.session.discipline != "strength")
    ws.log_session(WEEK, other.session.id, "done")
    with pytest.raises(PlannerError, match="already logged"):
        ws.ease_session(WEEK, other.session.id)
    # A well-recovered morning: reassurance, and no offer to change anything.
    gws = _joe(tmp_path / "good")
    gws.plan_week(WEEK)
    gpage = create_app(gws, now=lambda: now, garmin_fetch=lambda s, e: [],
                       garmin_get=getter(*GOOD), background=False).test_client().get("/")
    html = gpage.get_data(as_text=True)
    assert "You look recovered" in html and 'action="/ease"' not in html


def test_ac_087_heart_rates_from_garmin_are_confirmed_before_use(tmp_path):
    """AC-087 [e2e-test]: Your threshold, max and resting heart rate can be read from Garmin; they are shown next to your current values and only saved when you tick and confirm, and your zones follow"""
    zones = [{"sport": "DEFAULT", "trainingMethod": "LACTATE_THRESHOLD",
              "lactateThresholdHeartRateUsed": 181, "maxHeartRateUsed": 201,
              "restingHeartRateUsed": 49, "zone1Floor": 101}]
    assert heart_rates_from_garmin(zones, {}) == {"threshold_hr": 181, "max_hr": 201,
                                                  "resting_hr": 49}
    assert heart_rates_from_garmin(None, {"userData": {"lactateThresholdHeartRate": 178}}) == {
        "threshold_hr": 178}
    assert heart_rates_from_garmin({"maxHeartRateUsed": 999}) == {}  # nonsense ignored
    ws = _joe(tmp_path)
    app = create_app(ws, now=lambda: datetime(2026, 11, 10, 19),
                     garmin_get=getter(zones=zones), garmin_fetch=lambda s, e: [],
                     background=False)
    client = app.test_client()
    page = client.get("/garmin/heart-rates").get_data(as_text=True)
    assert "181 bpm" in page and "201 bpm" in page and "not set" in page
    assert ws.cfg.profile.threshold_hr is None  # looking changes nothing
    client.post("/garmin/heart-rates", data={"token": _token(client), "threshold_hr": "181",
                                             "max_hr": "201", "use_threshold_hr": "1"})
    ws.reload()
    assert ws.cfg.profile.threshold_hr == 181 and ws.cfg.profile.max_hr is None
    assert ws.cfg.profile.hr("threshold") == (172, 181)
    assert ws.cfg.athlete == "Joe" and ws.cfg.default_template == "term"  # rest kept


def test_ac_088_effort_check_flags_easy_sessions_done_too_hard(tmp_path):
    """AC-088 [e2e-test]: When your watch's average heart rate for an easy session was above your easy zone, the session says so; hard sessions and sessions without heart rate aren't flagged"""
    prof = Profile(threshold_hr=180)
    easy = Session(id="run-easy", discipline="run", kind="easy", duration_min=40, intensity=1,
                   requires=REQUIRES["run"], key=False)
    hard = easy.model_copy(update={"id": "run-threshold", "kind": "threshold", "intensity": 4})
    row = LogRow(on=WEEK, week=WEEK, session_id="run-easy", discipline="run", slot_key="k",
                 planned_min=40, status="done", actual_min=40, avg_hr=171)
    note = effort_note(easy, row, prof)
    assert note and "171" in note and str(prof.hr("steady")[1]) in note  # type: ignore[index]
    assert effort_note(hard, row, prof) is None
    assert effort_note(easy, row.model_copy(update={"avg_hr": 150}), prof) is None
    assert effort_note(easy, row.model_copy(update={"avg_hr": None}), prof) is None
    assert effort_note(easy, row, Profile()) is None  # no HR zones, no judgement
    ws = _joe(tmp_path, profile="threshold_hr: 180")
    ws.plan_week(WEEK)
    plan = ws.plan(WEEK)
    assert plan is not None
    target = next(p for p in plan.placements if p.session.kind in ("easy", "easy_strides",
                                                                   "endurance", "long")
                  and p.session.discipline != "swim")
    ws.log_session(WEEK, target.session.id, "done", minutes=45)
    log = ws.log()
    for i, r in enumerate(log):
        if r.session_id == target.session.id:
            log[i] = r.model_copy(update={"avg_hr": 175})
    from planner.adherence import write_log
    write_log(ws.log_path, log)
    app = create_app(ws, now=lambda: datetime(2026, 11, 15, 21))
    page = app.test_client().get(f"/s/{WEEK}/{target.session.id}").get_data(as_text=True)
    assert "Averaged 175 bpm, above easy" in page
