"""US-022: Run it as a home server you can trust (v0)."""

from __future__ import annotations

import io
import json
import re
import shutil
import sys
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

from icalendar import Calendar

from planner import backup, cli, web
from planner.service import Workspace
from planner.web import create_app

ROOT = Path(__file__).parent.parent
FIXTURE = Path(__file__).parent / "fixtures" / "short_weekday_slots.yaml"
W1, W2 = date(2026, 11, 9), date(2026, 11, 16)


def _ws(tmp_path: Path) -> Workspace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, tmp_path / "athlete.yaml")
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def _site(ws: Workspace, now: datetime):
    clock = {"now": now}
    client = create_app(ws, now=lambda: clock["now"], background=False).test_client()
    return client, clock


def test_ac_097_your_data_is_backed_up_every_day(tmp_path, monkeypatch):
    """AC-097 [e2e-test]: A backup zip of your settings and history is written once a day when the site is used (newest 14 kept), can be downloaded from Profile and made with `tri-plan backup`; it never holds the Garmin key, old backups or the server log"""
    key_file = tmp_path / "home" / "connect-personal-api-key"
    key_file.parent.mkdir()
    key_file.write_text("SECRET-KEY-123")
    monkeypatch.setenv("GARMIN_PERSONAL_API_KEY", "SECRET-KEY-123")
    ws = _ws(tmp_path / "app")
    ws.plan_week(W1)
    ws.log_session(W1, ws.plan(W1).placements[0].session.id, "done", rpe=5)  # type: ignore[union-attr]
    (ws.out / "server.log").write_text("noise")
    client, clock = _site(ws, datetime(2026, 11, 10, 7))
    folder = ws.out / "backups"
    assert not folder.exists()
    client.get("/")
    first = folder / "tri-planner-2026-11-10.zip"
    assert [p.name for p in folder.iterdir()] == [first.name]
    stamp = first.stat().st_mtime_ns
    client.get("/")
    assert first.stat().st_mtime_ns == stamp and len(list(folder.iterdir())) == 1  # once a day
    with zipfile.ZipFile(first) as z:
        names = set(z.namelist())
        assert {"athlete.yaml", "out/log.csv"} <= names
        assert any(n.startswith(f"out/{W1}/") for n in names)
        assert not any("backups" in n or n.endswith("server.log") for n in names)
        assert not any(b"SECRET-KEY-123" in z.read(n) for n in names)
        assert z.read("athlete.yaml") == ws.config_path.read_bytes()

    for i in range(1, 20):  # nineteen more days of use
        clock["now"] = datetime(2026, 11, 10, 7) + timedelta(days=i)
        client.get("/")
    kept = sorted(p.name for p in folder.iterdir())
    assert len(kept) == backup.KEEP == 14
    assert kept[0] == "tri-planner-2026-11-16.zip" and kept[-1] == "tri-planner-2026-11-29.zip"
    assert backup.last_backup(ws.out) == date(2026, 11, 29)

    profile = client.get("/setup").get_data(as_text=True)
    assert "Download backup" in profile and "the last one was 29 Nov" in profile
    res = client.get("/backup.zip")
    assert res.status_code == 200 and res.mimetype == "application/zip"
    assert "tri-planner-backup-2026-11-29.zip" in res.headers["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(res.data)) as z:
        assert "athlete.yaml" in z.namelist() and "out/log.csv" in z.namelist()

    # Restoring is just unzipping it: the plan and the log come back.
    restored = tmp_path / "restored"
    with zipfile.ZipFile(io.BytesIO(res.data)) as z:
        z.extractall(restored)
    again = Workspace(restored / "athlete.yaml", restored / "out")
    assert again.plan(W1) is not None and [r.rpe for r in again.log() if r.logged] == [5]

    usb = tmp_path / "usb"
    monkeypatch.setattr(cli, "_now", lambda _cfg: datetime(2026, 11, 30, 9))
    assert cli.main(["backup", str(ws.config_path), "--out", str(ws.out), "--to", str(usb)]) == 0
    assert (usb / "tri-planner-2026-11-30.zip").exists()
    assert cli.main(["backup", str(ws.config_path), "--out", str(ws.out)]) == 0
    assert (folder / "tri-planner-2026-11-30.zip").exists()


def test_ac_098_it_runs_as_a_proper_server_and_installs_like_an_app(tmp_path, monkeypatch):
    """AC-098 [integration-test]: `tri-plan web` serves with a production server (waitress) when it's installed and falls back to Flask's when it isn't, writing a backup as it starts; Windows start and update scripts are included; the site can be added to a phone's home screen (manifest + icons); Profile shows the running version"""
    ws = _ws(tmp_path)
    ws.plan_week(W1)
    calls: list[tuple[str, dict]] = []
    import waitress

    monkeypatch.setattr(waitress, "serve", lambda app, **kw: calls.append(("waitress", kw)))
    web.serve(ws.config_path, ws.out, host="0.0.0.0", port=8123, open_browser=False)
    assert calls == [("waitress", {"host": "0.0.0.0", "port": 8123, "threads": 6,
                                   "ident": "tri-planner"})]
    assert len(list((ws.out / "backups").glob("tri-planner-*.zip"))) == 1  # backed up at start
    from flask import Flask

    monkeypatch.setitem(sys.modules, "waitress", None)  # not installed
    monkeypatch.setattr(Flask, "run", lambda self, **kw: calls.append(("flask", kw)))
    web.serve(ws.config_path, ws.out, port=8124, open_browser=False)
    assert calls[-1] == ("flask", {"host": "127.0.0.1", "port": 8124, "debug": False})
    assert any("waitress" in dep for dep in _extras()["web"])

    start = (ROOT / "scripts" / "start-server.bat").read_bytes()
    update = (ROOT / "scripts" / "update-server.bat").read_bytes()
    assert b"web --host 0.0.0.0 --no-browser" in start and b"server.log" in start
    assert b"git pull" in update and b"pip" in update
    for script in (start, update):  # Windows line endings, or cmd misreads them
        assert b"\r\n" in script and b"\n" not in script.replace(b"\r\n", b"")

    client, _ = _site(ws, datetime(2026, 11, 10, 7))
    home = client.get("/").get_data(as_text=True)
    assert 'rel="manifest" href="/static/manifest.webmanifest"' in home
    assert 'rel="apple-touch-icon"' in home
    manifest = json.loads(client.get("/static/manifest.webmanifest").data)
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    sizes = {i["sizes"] for i in manifest["icons"]}
    assert {"192x192", "512x512"} <= sizes
    assert any(i.get("purpose") == "maskable" for i in manifest["icons"])
    for icon in [i["src"] for i in manifest["icons"]] + ["/static/icons/apple-touch-icon.png"]:
        res = client.get(icon)
        assert res.status_code == 200 and res.data[:8] == b"\x89PNG\r\n\x1a\n", icon
    profile = client.get("/setup").get_data(as_text=True)
    assert re.search(r"tri-planner version <code>[0-9a-f]{7}</code>", profile)


def _extras() -> dict[str, list[str]]:
    import tomllib

    return tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"]


def test_ac_099_one_calendar_link_always_shows_the_current_plan(tmp_path):
    """AC-099 [e2e-test]: The site offers one calendar link to subscribe to: it holds last week, this week and every planned week after, and reflects re-plans and moved sessions without downloading anything again"""
    ws = _ws(tmp_path)
    now = datetime(2026, 11, 17, 7)
    client, _ = _site(ws, now)

    def feed() -> dict[str, datetime]:
        res = client.get("/calendar.ics")
        assert res.status_code == 200 and res.mimetype == "text/calendar"
        assert res.headers["Cache-Control"] == "no-cache"
        cal = Calendar.from_ical(res.data)
        return {str(e["UID"]): e["DTSTART"].dt for e in cal.walk("VEVENT")}

    assert feed() == {}  # nothing planned yet: an empty calendar, not an error
    for wk in (date(2026, 11, 2), W1, W2, date(2026, 11, 23)):
        ws.plan_week(wk)
    events = feed()
    days = {start.date() for start in events.values()}
    assert min(days) >= W1 and max(days) >= date(2026, 11, 23)  # last week onwards
    count = sum(len(ws.plan(wk).placements)  # type: ignore[union-attr]
                for wk in (W1, W2, date(2026, 11, 23)))
    assert len(events) == count

    plan = ws.plan(W2)
    assert plan is not None
    target = next(p for p in plan.placements if p.slot.on and p.slot.on >= date(2026, 11, 19)
                  and ws.move_options(W2, p.session.id, now))
    option = ws.move_options(W2, target.session.id, now)[0]
    before = feed()
    ws.move_session(W2, target.session.id, option.uid, now)
    after = feed()
    gone, new = set(before) - set(after), set(after) - set(before)
    assert len(gone) == len(new) == 1 and len(after) == len(before)  # moved, not duplicated
    assert next(iter(gone)).startswith(target.session.id)
    moved = after[next(iter(new))]
    assert moved.date() == option.slot.on
    assert (moved.hour, moved.minute) == (option.start.hour, option.start.minute)
    week = client.get(f"/week?w={W2}").get_data(as_text=True)
    assert "/calendar.ics" in week and "subscribe" in week.lower()
