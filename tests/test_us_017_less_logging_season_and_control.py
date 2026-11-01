"""US-017: Less logging, the season view, moving sessions and the experiment (v0)."""

from __future__ import annotations

import io
import re
import stat
import zipfile
from datetime import date, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from planner import cli, garmin
from planner.activities import read_bytes
from planner.config import load_config
from planner.service import PlannerError, Workspace
from planner.web import create_app

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"
WEEK = date(2026, 11, 9)
SPORT = {"run": 1, "bike": 2, "swim": 5, "strength": 10}


def make_fit(start: datetime, sport: str, minutes: float, *, km: float | None = None,
             hr: int | None = None, watts: int | None = None) -> bytes:
    """A minimal FIT activity file, as a watch would record it (start in London time)."""
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.session_message import SessionMessage
    from fit_tool.profile.profile_type import FileType, Manufacturer

    ms = int(start.replace(tzinfo=ZoneInfo("Europe/London")).timestamp() * 1000)
    fid = FileIdMessage()
    fid.type = FileType.ACTIVITY
    fid.manufacturer = Manufacturer.GARMIN.value
    fid.product = 0
    fid.time_created = ms
    fid.serial_number = 1
    s = SessionMessage()
    s.start_time = ms
    s.timestamp = ms + int(minutes * 60_000)
    s.sport = SPORT[sport]
    if sport == "strength":
        s.sub_sport = 20
    s.total_timer_time = minutes * 60
    s.total_elapsed_time = minutes * 60
    if km:
        s.total_distance = km * 1000
    if hr:
        s.avg_heart_rate = hr
    if watts:
        s.avg_power = watts
    b = FitFileBuilder(auto_define=True)
    b.add(fid)
    b.add(s)
    return b.build().to_bytes()


def _joe(tmp_path: Path) -> Workspace:
    (tmp_path / "athlete.yaml").write_text(EXAMPLE.read_text())
    ws = Workspace(tmp_path / "athlete.yaml", tmp_path / "out")
    ws.plan_week(WEEK)
    return ws


def _first(ws: Workspace, sport: str, day: date | None = None):
    plan = ws.plan(WEEK)
    assert plan is not None
    return next(p for p in plan.placements if p.session.discipline == sport
                and (day is None or p.slot.on == day))


def _client(ws: Workspace, now: datetime, **kw):
    app = create_app(ws, now=lambda: now, **kw)
    client = app.test_client()
    html = client.get("/setup").get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)  # type: ignore[union-attr]
    return client, token


def test_ac_077_experiment_is_switched_on_from_the_website(tmp_path):
    """AC-077 [e2e-test]: The experiment is switched on from the Profile page: weeks then alternate facility-aware / time-only, test weeks are labelled, and the season shows which is which"""
    ws = _joe(tmp_path)
    client, token = _client(ws, datetime(2026, 11, 10, 19))
    html = client.get("/setup").get_data(as_text=True)
    form = {k: v for k, v in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', html)
            if not k.startswith(("slot-", "loc-", "ov-", "p-")) and "__" not in k}
    raw = load_config(ws.config_path)  # keep everything else, just flip the switch
    form.update({"token": token, "mode": "form", "athlete": raw.athlete, "race": raw.race,
                 "race_date": str(raw.race_date), "experiment": "1",
                 "experiment_start": "2026-11-16"})
    for i, loc in enumerate(raw.locations):
        form[f"loc-{i}-name"] = loc.name
    data = {**form, **{f"loc-{i}-kit": [f.name.value for f in loc.facilities]
                       for i, loc in enumerate(raw.locations)}}
    for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun"):
        slots = [s for s in raw.templates["term"].slots if s.day == d]
        data[f"slot-{d}-start"] = [f"{s.start:%H:%M}" for s in slots]
        data[f"slot-{d}-end"] = [f"{s.end:%H:%M}" for s in slots]
        data[f"slot-{d}-loc"] = [s.location for s in slots]
    assert client.post("/setup", data=data).status_code == 302
    ws.reload()
    assert ws.cfg.experiment_start == date(2026, 11, 16)
    aware = ws.plan_week(date(2026, 11, 16))
    test = ws.plan_week(date(2026, 11, 23))
    assert aware.week_type == "facility_aware" and test.week_type == "time_only"
    assert not test.plan.facility_aware
    page = client.get("/week?w=2026-11-23").get_data(as_text=True)
    assert "Time-only test week" in page
    assert "Time-only test week" not in client.get("/week?w=2026-11-16").get_data(as_text=True)
    weeks = {w.week: w for w in ws.season(date(2026, 11, 10))}
    assert weeks[date(2026, 11, 23)].week_type == "time_only"
    assert weeks[WEEK].week_type == "facility_aware"  # before the start: normal


def test_ac_078_season_view_shows_the_road_to_race_day(tmp_path):
    """AC-078 [e2e-test]: The season view lists every week to race day with its phase, recovery weeks, holidays and exams, what was planned and done, and the volume the planner is heading for (≤10%/week growth, a ceiling for the distance, never more than free time)"""
    ws = _joe(tmp_path)
    weeks = ws.season(date(2026, 11, 10))
    assert weeks[0].week <= WEEK and weeks[-1].race and weeks[-1].week == date(2027, 6, 21)
    by = {w.week: w for w in weeks}
    assert by[WEEK].when == "now" and by[WEEK].planned_min  # planned this week
    assert any(w.recovery for w in weeks) and by[date(2027, 6, 21)].phase == "taper"
    assert "Christmas holiday" in by[date(2026, 12, 21)].labels
    assert "Summer exams" in by[date(2027, 5, 17)].labels
    for prev, cur in pairwise(weeks):
        assert cur.projected_min <= cur.available_min * 0.8 + 5
        if not (cur.recovery or prev.recovery or cur.phase == "taper" or cur.labels
                or prev.labels):
            assert cur.projected_min <= prev.projected_min * 1.1 + 10
    assert max(w.projected_min for w in weeks) <= 11 * 60
    app_client, _ = _client(ws, datetime(2026, 11, 10, 19))
    page = app_client.get("/season").get_data(as_text=True)
    assert "Season" in page and "Christmas holiday" in page and "Race week" in page


def test_ac_079_move_a_session_yourself_within_the_rules(tmp_path):
    """AC-079 [e2e-test]: You can move a session to any later slot where its kit is open and there's room; the plan, log and files follow, a logged session can't be moved, and breaking a coaching rule is allowed but flagged"""
    ws = _joe(tmp_path)
    now = datetime(2026, 11, 10, 8, 0)
    swim = _first(ws, "swim", date(2026, 11, 11)) if any(
        p.session.discipline == "swim" and p.slot.on == date(2026, 11, 11)
        for p in ws.plan(WEEK).placements) else _first(ws, "swim")  # type: ignore[union-attr]
    opts = ws.move_options(WEEK, swim.session.id, now)
    assert opts and all(o.slot.starts_at >= now for o in opts)
    cfg = ws.cfg
    for o in opts:  # never a slot where the pool is closed or missing
        loc = cfg.location(o.slot.location)
        end = (datetime.combine(o.slot.on, o.start)  # type: ignore[arg-type]
               + timedelta(minutes=swim.session.duration_min)).time()
        assert swim.session.fits(loc, o.slot.day, o.start, end)
    assert not any(o.slot.location == "Canterbury" for o in opts)
    target = opts[-1]
    new, _warnings = ws.move_session(WEEK, swim.session.id, target.uid, now)
    moved = new.placement(swim.session.id)
    assert moved is not None and moved.slot.on == target.slot.on and moved.reason == "you_moved_it"
    assert ws.plan(WEEK).placement(swim.session.id).slot.on == target.slot.on  # type: ignore[union-attr]
    assert ws.log_index(WEEK)[swim.session.id].on == target.slot.on
    with pytest.raises(PlannerError):
        ws.move_session(WEEK, swim.session.id, "2026-11-08|sun-09:00-12:00@Home", now)
    hard = [p for p in ws.plan(WEEK).placements if p.session.intensity >= 3]  # type: ignore[union-attr]
    if len(hard) >= 2:
        a, b = hard[0], hard[1]
        clash = next((o for o in ws.move_options(WEEK, b.session.id, now)
                      if o.slot.on == a.slot.on), None)
        if clash and b.session.discipline == a.session.discipline:
            assert any("Two" in w for w in clash.warnings)
    run = _first(ws, "run")
    ws.log_session(WEEK, run.session.id, "done")
    with pytest.raises(PlannerError, match="already logged"):
        ws.move_options(WEEK, run.session.id, now)
    client, token = _client(ws, now)
    other = next(p for p in ws.plan(WEEK).placements  # type: ignore[union-attr]
                 if p.session.id not in (run.session.id,) and p.starts_at > now
                 and ws.move_options(WEEK, p.session.id, now))
    page = client.get(f"/s/{WEEK}/{other.session.id}").get_data(as_text=True)
    assert "Move this session" in page
    uid = ws.move_options(WEEK, other.session.id, now)[0].uid
    res = client.post("/move", data={"token": token, "week": str(WEEK),
                                     "session": other.session.id, "slot": uid})
    assert res.status_code == 302
    assert ws.plan(WEEK).placement(other.session.id).slot.on is not None  # type: ignore[union-attr]


def test_ac_080_watch_files_tick_off_the_right_sessions_once(tmp_path):
    """AC-080 [integration-test]: Activity files (.fit, a .zip export, or a folder) tick off the matching planned session: same sport and week, same day = done, other day = moved; a brick's run leg is merged; extras are reported, not forced in; nothing is imported twice and sessions you logged yourself are left alone"""
    ws = _joe(tmp_path)
    run = _first(ws, "run")
    bike = _first(ws, "bike")
    day_run = make_fit(run.starts_at + timedelta(minutes=3), "run", 38.5, km=7.4, hr=151)
    other_day = run.slot.on + timedelta(days=1) if run.slot.on.weekday() < 6 \
        else run.slot.on - timedelta(days=1)  # type: ignore[operator]
    bike_moved = make_fit(datetime.combine(other_day, bike.start), "bike", 52, km=21,  # type: ignore[arg-type]
                          watts=168)
    extra = make_fit(datetime(2026, 11, 12, 20, 0), "swim", 30, km=1.5)  # no swim then
    folder = tmp_path / "watch" / "GARMIN" / "Activity"
    folder.mkdir(parents=True)
    (folder / "run.fit").write_bytes(day_run)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("123_ACTIVITY.fit", bike_moved)
    (tmp_path / "export.zip").write_bytes(buf.getvalue())
    (folder / "notes.txt").write_text("ignore me")

    res = ws.import_files([tmp_path / "watch", tmp_path / "export.zip"])
    by = {m.session_id: m for m in res.matched}
    assert by[run.session.id].moved is False and by[bike.session.id].moved is (
        other_day != bike.slot.on)
    rows = ws.log_index(WEEK)
    r = rows[run.session.id]
    assert (r.status, r.actual_min, r.avg_hr, r.distance_m, r.source) == ("done", 38, 151, 7400,
                                                                          "file")
    assert rows[bike.session.id].avg_power == 168
    again = ws.import_files([tmp_path / "watch", tmp_path / "export.zip"])
    assert not again.matched and again.duplicates == 2  # each activity imported once

    swim_extra = ws.import_uploads([("late.fit", extra)])
    planned_swim_days = {p.slot.on for p in ws.plan(WEEK).placements  # type: ignore[union-attr]
                         if p.session.discipline == "swim"}
    if date(2026, 11, 12) not in planned_swim_days and not swim_extra.matched:
        assert swim_extra.extras

    # Sessions you logged yourself are never overwritten.
    s2 = next(p for p in ws.plan(WEEK).placements  # type: ignore[union-attr]
              if p.session.discipline == "swim")
    ws.log_session(WEEK, s2.session.id, "skipped", reason="no_time")
    late = make_fit(s2.starts_at, "swim", 40)
    ws.import_uploads([("s.fit", late)])
    assert ws.log_index(WEEK)[s2.session.id].status == "skipped"

    # Brick: a ride and the run straight after it count as one session.
    from planner.activities import Activity, Match, match_activities
    from planner.solver import Plan
    brick = bike.model_copy(update={"session": bike.session.model_copy(
        update={"kind": "brick", "id": "bike-brick"})})
    plan = Plan(status="feasible", placements=[brick])
    ride = Activity(activity_id="r", start=brick.starts_at, sport="bike", seconds=45 * 60)
    leg = Activity(activity_id="l", start=brick.starts_at + timedelta(minutes=47), sport="run",
                   seconds=15 * 60)
    out = match_activities([ride, leg], {WEEK: plan}, [])
    assert [m.session_id for m in out.matched] == ["bike-brick"] and not out.extras
    assert isinstance(out.matched[0], Match) and out.matched[0].extra_minutes == 15
    strength = make_fit(datetime(2026, 11, 14, 9), "strength", 30)
    assert read_bytes("x.fit", strength, "Europe/London")[0].sport == "strength"

    # Regression (Windows): reading must not go through a temp file on disk.
    import tempfile

    def no_temp(*_a, **_k):
        raise PermissionError("Windows can't reopen an open temp file")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(tempfile, "NamedTemporaryFile", no_temp)
        mp.setattr(tempfile, "mkstemp", no_temp)
        assert read_bytes("x.fit", strength, "Europe/London")

    assert cli.main(["import", str(folder), "--config", str(ws.config_path), "--out",
                     str(ws.out)]) == 0  # the terminal route works too


def test_ac_081_garmin_personal_api_sync(tmp_path, monkeypatch):
    """AC-081 [integration-test]: "Sync from Garmin" uses Garmin's Personal API client with your key from ~/.config/garmin or GARMIN_PERSONAL_API_KEY, downloads recent activities' original files and ticks off sessions; no key or a refused key gives a plain message; the key is stored readable only by you and never in the project"""
    ws = _joe(tmp_path)
    run = _first(ws, "run")
    fit = make_fit(run.starts_at, "run", 41, km=8, hr=149)
    zipped = io.BytesIO()
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("98765_ACTIVITY.fit", fit)

    calls: dict[str, object] = {}

    class FakeAuth:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def obtain_token(self, key):
            calls["key"] = key
            return type("T", (), {"access_token": "tok"})()

    class FakeClient:
        def __init__(self, token): calls["token"] = token
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def search_activities(self, **kw):
            calls["search"] = kw
            return [{"activityId": 98765}, {"activityName": "no id"}]
        def download_activity(self, aid):
            calls.setdefault("downloads", []).append(aid)  # type: ignore[union-attr]
            return zipped.getvalue()

    import garmin_personal_api as lib
    monkeypatch.setattr(lib, "PersonalApiAuthenticator", FakeAuth)
    monkeypatch.setattr(lib, "GarminPersonalApiClient", FakeClient)
    monkeypatch.setattr(garmin, "KEY_FILE", tmp_path / "cfg" / "garmin" / "key")
    monkeypatch.delenv(garmin.KEY_ENV, raising=False)
    monkeypatch.setattr(ws, "now", lambda: datetime(2026, 11, 15, 20))

    with pytest.raises(garmin.GarminError, match="No Garmin key"):
        ws.sync_garmin()
    monkeypatch.setenv(garmin.KEY_ENV, "test-key-from-env-0123456789")
    ws.sync_garmin(days=7)
    assert calls["key"] == "test-key-from-env-0123456789" and calls["token"] == "tok"
    assert calls["search"]["start_date"] == date(2026, 11, 8)  # type: ignore[index]
    assert calls["downloads"] == [98765]
    row = ws.log_index(WEEK)[run.session.id]
    assert row.source == "garmin_personal" and row.actual_min == 41 and row.activity_id.startswith(
        "garmin:98765")
    assert not ws.sync_garmin(days=7).matched  # second sync: nothing new

    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as z:
        z.writestr("1_ACTIVITY.fit", b"not a fit file")
    acts, bad = garmin.fetch_activities(
        date(2026, 11, 1), date(2026, 11, 15), "Europe/London",
        fetch=lambda s, e: [("1", broken.getvalue()), ("98765", zipped.getvalue())])
    assert bad == ["Garmin activity 1"] and len(acts) == 1  # one bad file doesn't stop the rest

    class Refused(FakeAuth):
        def obtain_token(self, key):
            err = lib.HttpError.__new__(lib.HttpError)
            err.status_code = 401
            raise err

    monkeypatch.setattr(lib, "PersonalApiAuthenticator", Refused)
    with pytest.raises(garmin.GarminError, match="refused the key"):
        garmin.download_recent(date(2026, 11, 1), date(2026, 11, 15))

    # Saving the key from the website: private file, never in config or out/.
    monkeypatch.delenv(garmin.KEY_ENV)
    client, token = _client(ws, datetime(2026, 11, 15, 20))
    secret = "GCDC_example-not-a-real-key-0123456789"
    assert client.post("/garmin/key", data={"token": token, "key": secret}).status_code == 302
    key_file = tmp_path / "cfg" / "garmin" / "key"
    assert key_file.read_text().strip() == secret
    assert stat.S_IMODE(key_file.stat().st_mode) == 0o600
    for f in [ws.config_path, *ws.out.rglob("*")]:
        if f.is_file():
            assert secret not in f.read_bytes().decode("utf-8", "ignore"), f
    assert client.post("/garmin/key", data={"token": token, "key": "short"}).status_code == 302
    assert key_file.read_text().strip() == secret  # a bad key doesn't replace a good one


def test_ac_082_import_from_the_website_and_still_report_pain(tmp_path):
    """AC-082 [e2e-test]: On Today you can sync from Garmin or add activity files; imported sessions show time, distance and heart rate, and you can still say something hurt"""
    ws = _joe(tmp_path)
    run = _first(ws, "run")
    now = run.starts_at + timedelta(hours=2)
    client, token = _client(ws, now, garmin_fetch=lambda s, e: [])
    today = client.get(f"/?d={run.slot.on}").get_data(as_text=True)
    assert "Sync from Garmin" in today and "Add activity files" in today
    fit = make_fit(run.starts_at, "run", 40, km=8.1, hr=150)
    res = client.post("/import", data={"token": token, "next": f"/?d={run.slot.on}",
                                       "files": [(io.BytesIO(fit), "run.fit")]},
                      content_type="multipart/form-data", follow_redirects=True)
    page = res.get_data(as_text=True)
    assert "ticked off 1 session" in page and "8.1 km" in page and "150 bpm" in page
    assert "Something hurt" in page
    client.post("/log", data={"token": token, "week": str(WEEK), "session": run.session.id,
                              "action": "pain", "next": "/"})
    assert ws.log_index(WEEK)[run.session.id].pain
    synced = client.post("/sync", data={"token": token, "next": "/"}, follow_redirects=True)
    assert "nothing new" in synced.get_data(as_text=True)
