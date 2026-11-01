"""US-015: Local web app (v0, single athlete, runs on your own computer)."""

from __future__ import annotations

import re
import zipfile
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import pytest

from planner.adherence import read_log
from planner.cli import build_parser
from planner.config import load_config
from planner.service import Workspace
from planner.store import InjuryStore
from planner.web import create_app

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"
NOW = datetime(2026, 11, 10, 19, 0)  # Tuesday evening
WEEK = date(2026, 11, 9)


def _client(tmp_path: Path, with_config: bool = True):
    tmp_path.mkdir(parents=True, exist_ok=True)
    cfg = tmp_path / "athlete.yaml"
    if with_config:
        cfg.write_text(EXAMPLE.read_text())
    ws = Workspace(cfg, tmp_path / "out")
    app = create_app(ws, now=lambda: NOW)
    app.config["TESTING"] = True
    return app.test_client(), ws


def _token(client) -> str:
    html = client.get("/setup").get_data(as_text=True)
    m = re.search(r'name="token" value="([^"]+)"', html)
    assert m
    return m.group(1)


def _plan(client, token: str):
    return client.post("/week/plan", data={"token": token, "week": str(WEEK)})


def test_ac_065_serves_every_page_and_sends_first_run_to_setup(tmp_path):
    """AC-065 [e2e-test]: `tri-plan web` serves Today, Week, Changed, Progress and Setup; with no config the first page is Setup"""
    client, _ = _client(tmp_path, with_config=False)
    first = client.get("/")
    assert first.status_code == 302 and first.headers["Location"].endswith("/setup")
    assert "Set up your week" in client.get("/setup").get_data(as_text=True)

    client, _ = _client(tmp_path / "joe")
    for url in ("/", "/week", "/replan", "/progress", "/setup", f"/week?w={WEEK}"):
        res = client.get(url)
        assert res.status_code == 200, url
        assert "tri-planner" in res.get_data(as_text=True)
    assert "No plan for this week yet" in client.get("/").get_data(as_text=True)
    a = build_parser().parse_args(["web"])
    assert a.host == "127.0.0.1" and a.port == 8000  # only this computer, unless you ask


def test_ac_066_setup_form_writes_a_valid_config_and_rejects_bad_input(tmp_path):
    """AC-066 [e2e-test]: The setup form creates and edits the config without YAML; bad input is rejected with a reason and the file is left alone; an existing config round-trips unchanged"""
    client, ws = _client(tmp_path, with_config=False)
    token = _token(client)
    form = {
        "token": token, "mode": "form", "athlete": "Sam", "race": "olympic",
        "race_date": "2027-07-04", "weekly_hours": "9",
        "loc-0-name": "Home", "loc-0-kit": ["road_bike", "outdoor_run"],
        "loc-1-name": "Leisure centre", "loc-1-kit": ["pool", "treadmill"],
        "loc-1-hours-pool": "weekdays 6:30-21:00; weekends 8-18",
        "slot-mon-start": ["06:30", "18:00"], "slot-mon-end": ["07:30", "19:30"],
        "slot-mon-loc": ["Home", "Leisure centre"],
        "slot-sat-start": "08:00", "slot-sat-end": "11:00", "slot-sat-loc": "Home",
    }
    res = client.post("/setup", data=form)
    assert res.status_code == 302
    cfg = load_config(ws.config_path)
    assert cfg.athlete == "Sam" and cfg.race == "olympic" and cfg.weekly_hours == 9
    pool = next(f for f in cfg.location("Leisure centre").facilities if f.name.value == "pool")
    assert len(pool.windows) == 2 and pool.windows[0].days == ["mon", "tue", "wed", "thu", "fri"]
    assert [s.day for s in cfg.templates[cfg.default_template].slots] == ["mon", "mon", "sat"]

    before = ws.config_path.read_text()
    bad = {**form, "slot-sat-loc": "Mars"}  # a place that doesn't exist
    res = client.post("/setup", data=bad, follow_redirects=True)
    assert "Not saved" in res.get_data(as_text=True) and "Mars" in res.get_data(as_text=True)
    assert ws.config_path.read_text() == before
    res = client.post("/setup", data={"token": token, "mode": "raw", "raw": "athlete: [oops"},
                      follow_redirects=True)
    assert "Not saved" in res.get_data(as_text=True) and ws.config_path.read_text() == before

    # Joe's multi-template config survives a save from the form untouched.
    client, ws = _client(tmp_path / "joe")
    html = client.get("/setup").get_data(as_text=True)
    data: dict[str, list[str]] = {}
    for tag in re.finditer(r'<(input|select)[^>]*name="([^"]+)"[^>]*>', html):
        if "__" in tag.group(2):
            continue  # JS row templates
        name, el = tag.group(2), tag.group(0)
        if 'type="checkbox"' in el and "checked" not in el:
            continue
        value = re.search(r'value="([^"]*)"', el)
        if tag.group(1) == "select":
            value = re.search(r'data-value="([^"]*)"', el) or _selected(html, tag.end())
        data.setdefault(name, []).append(value.group(1) if value else "")
    data["mode"] = ["form"]
    assert client.post("/setup", data=data).status_code == 302
    assert load_config(ws.config_path).model_dump() == load_config(EXAMPLE).model_dump()


def _selected(html: str, pos: int):
    chunk = html[pos: html.index("</select>", pos)]
    return re.search(r"<option[^>]*selected[^>]*>([^<]*)<", chunk) or re.search(
        r'<option[^>]*value="([^"]*)"[^>]*selected', chunk)


def test_ac_067_planning_from_the_website_writes_the_same_files_and_offers_downloads(tmp_path):
    """AC-067 [e2e-test]: Planning a week from the website writes the same plan, .ics, .FIT and log as the CLI, and offers the .ics and a .zip of workouts to download"""
    client, ws = _client(tmp_path)
    res = _plan(client, _token(client))
    assert res.status_code == 302
    plan = ws.plan(WEEK)
    assert plan is not None and plan.placements
    assert len([r for r in read_log(ws.log_path) if r.week == WEEK]) == len(plan.placements)
    page = client.get(f"/week?w={WEEK}").get_data(as_text=True)
    assert f"Planned {plan.planned_minutes // 60}h{plan.planned_minutes % 60:02d}" in page
    assert "Bike long" in page and "Calendar file" in page
    ics = client.get(f"/files/{WEEK}/plan.ics")
    assert ics.status_code == 200 and b"BEGIN:VCALENDAR" in ics.data
    z = zipfile.ZipFile(BytesIO(client.get(f"/files/{WEEK}/workouts.zip").data))
    assert z.namelist() and all(n.endswith(".fit") for n in z.namelist())
    assert client.get(f"/files/{WEEK}/secrets.txt").status_code == 404


def test_ac_068_log_done_skipped_and_undo_from_the_website(tmp_path):
    """AC-068 [e2e-test]: From Today or Week: Done (minutes, something hurt, another time), Skipped with one reason tap, and Undo"""
    client, ws = _client(tmp_path)
    token = _token(client)
    _plan(client, token)
    mon, tue = (next(r for r in ws.log() if r.on == d) for d in (WEEK, date(2026, 11, 10)))
    today = client.get("/").get_data(as_text=True)
    assert "Not logged yet" in today and "Done it" in today  # Monday waits to be logged

    def post(**kw):
        return client.post("/log", data={"token": token, "week": str(WEEK), "next": "/", **kw})

    post(session=mon.session_id, action="done", minutes="25", pain="1", other_time="1")
    post(session=tue.session_id, action="skipped", reason="facility_closed")
    rows = ws.log_index(WEEK)
    assert (rows[mon.session_id].status, rows[mon.session_id].actual_min) == ("moved", 25)
    assert rows[mon.session_id].pain
    assert (rows[tue.session_id].status, rows[tue.session_id].reason) == ("skipped",
                                                                          "facility_closed")
    post(session=tue.session_id, action="undo")
    assert not ws.log_index(WEEK)[tue.session_id].logged
    res = post(session=mon.session_id, action="done", minutes="lots")
    assert res.status_code == 302 and ws.log_index(WEEK)[mon.session_id].actual_min == 25
    res = post(session="nope", action="done")
    assert res.status_code == 302  # friendly message, not a crash


def test_ac_069_something_changed_replans_and_shows_a_receipt_per_move(tmp_path):
    """AC-069 [e2e-test]: "Something's changed" re-plans from ticked slots, a new or cleared injury and flagged sessions, and shows a receipt for every move"""
    client, ws = _client(tmp_path)
    token = _token(client)
    _plan(client, token)
    form = client.get("/replan").get_data(as_text=True)
    gone = re.findall(r'name="gone" value="([^"]+)"', form)
    thu_pm = next(g for g in gone if "thu-16" in g)
    res = client.post("/replan", data={"token": token, "gone": thu_pm, "injury_sport": "run",
                                       "injury_days": "5"})
    page = res.get_data(as_text=True)
    assert res.status_code == 200 and "What changed" in page and "Injury remap" in page
    plan = ws.plan(WEEK)
    assert plan is not None
    assert not any("thu-16" in p.slot.key and p.slot.on == date(2026, 11, 12)
                   for p in plan.placements)
    assert [i.discipline for i in InjuryStore(ws.out / "injuries.json").active(NOW.date())] == ["run"]
    assert "Run paused" in client.get("/").get_data(as_text=True)
    client.post("/replan", data={"token": token, "clear": "run"})
    assert InjuryStore(ws.out / "injuries.json").active(NOW.date()) == []


def test_ac_070_forms_only_accept_posts_from_the_app_itself(tmp_path):
    """AC-070 [unit-test]: Every form needs the page's secret token, so another website open in your browser can't change your plan or log"""
    client, ws = _client(tmp_path)
    assert _plan(client, "forged").status_code == 400
    assert client.post("/week/plan", data={"week": str(WEEK)}).status_code == 400
    assert ws.plan(WEEK) is None
    other, _ = _client(tmp_path / "other")
    assert _plan(client, _token(other)).status_code == 400  # each run has its own token
    assert _plan(client, _token(client)).status_code == 302


@pytest.fixture(autouse=True)
def _no_browser(monkeypatch):
    monkeypatch.setattr("webbrowser.open", lambda *_a, **_k: None)
