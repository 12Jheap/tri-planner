"""US-024: Effort and training load (v0)."""

from __future__ import annotations

import re
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from test_us_017_less_logging_season_and_control import make_fit

from planner import cli
from planner.activities import parse_fit
from planner.adherence import LogRow, read_log
from planner.load import weekly_loads
from planner.service import PlannerError, Workspace
from planner.web import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "short_weekday_slots.yaml"
W1, W2, W3 = date(2026, 11, 9), date(2026, 11, 16), date(2026, 11, 23)


def _ws(tmp_path: Path) -> Workspace:
    tmp_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE, tmp_path / "athlete.yaml")
    return Workspace(tmp_path / "athlete.yaml", tmp_path / "out")


def _client(ws: Workspace, now: datetime):
    client = create_app(ws, now=lambda: now, background=False).test_client()
    html = client.get("/setup").get_data(as_text=True)
    token = re.search(r'name="token" value="([^"]+)"', html).group(1)  # type: ignore[union-attr]
    return client, token


def test_ac_104_effort_is_asked_when_you_log_and_can_be_added_later(tmp_path):
    """AC-104 [e2e-test]: Marking a session done asks how hard it felt (1-10, optional); a session logged without it can be rated later with one tap; the command line takes --effort; anything outside 1-10 is refused"""
    ws = _ws(tmp_path)
    ws.plan_week(W1)
    now = datetime(2026, 11, 15, 20)
    client, token = _client(ws, now)
    first, second, third = [p.session.id for p in ws.plan(W1).placements][:3]  # type: ignore[union-attr]
    def page(sid: str) -> str:
        return client.get(f"/s/{W1}/{sid}").get_data(as_text=True)

    assert "How hard was it?" in page(first) and 'type="radio" name="rpe" value="7"' in page(first)
    base = {"token": token, "week": str(W1)}
    client.post("/log", data={**base, "session": first, "action": "done", "rpe": "7"})
    client.post("/log", data={**base, "session": second, "action": "done"})  # effort is optional
    rows = {r.session_id: r for r in ws.log()}
    assert (rows[first].status, rows[first].rpe) == ("done", 7)
    assert (rows[second].status, rows[second].rpe) == ("done", None)
    rate = 'name="action" value="rate"'
    assert "effort 7/10" in page(first) and rate not in page(first)
    assert rate in page(second)  # the unrated one offers a one-tap rating
    res = client.post("/log", data={**base, "session": second, "action": "rate", "rpe": "4"},
                      follow_redirects=True)
    assert "Effort saved" in res.get_data(as_text=True)
    assert {r.session_id: r for r in ws.log()}[second].rpe == 4
    assert "effort 4/10" in page(second) and rate not in page(second)
    for bad in (0, 11):
        with pytest.raises(PlannerError):
            ws.rate_session(W1, second, bad)
        with pytest.raises(PlannerError):
            ws.log_session(W1, third, "done", rpe=bad)
    with pytest.raises(PlannerError):
        ws.rate_session(W1, third, 5)  # nothing done yet: nothing to rate
    args = ["log", str(ws.config_path), "--out", str(ws.out), "--week", str(W1),
            "--session", third, "--status", "done"]
    assert cli.main([*args, "--effort", "6"]) == 0
    assert {r.session_id: r for r in read_log(ws.log_path)}[third].rpe == 6
    with pytest.raises(SystemExit):
        cli.main([*args, "--effort", "12"])
    ws.log_session(W1, third, None)  # undo clears the effort with the entry
    assert {r.session_id: r for r in ws.log()}[third].rpe is None


def test_ac_105_the_watchs_effort_score_comes_in_with_the_activity(tmp_path):
    """AC-105 [integration-test]: If you answer the watch's "how did that feel?" question, that effort score arrives with the imported activity (Garmin's 10-100 scale becomes 1-10); an activity without one leaves effort blank"""
    ws = _ws(tmp_path)
    ws.plan_week(W1)
    plan = ws.plan(W1)
    assert plan is not None
    runs = [p for p in plan.placements if p.session.discipline == "run"][:2]
    assert len(runs) == 2

    def recorded(p, rpe=None) -> bytes:
        start = datetime.combine(p.slot.on, p.start)
        return make_fit(start, "run", p.session.duration_min, km=6, hr=150, rpe=rpe)

    felt = parse_fit(recorded(runs[0], rpe=70))
    assert felt[0].rpe == 7
    assert parse_fit(recorded(runs[0], rpe=10))[0].rpe == 1  # Garmin's lowest answer
    assert parse_fit(recorded(runs[0], rpe=100))[0].rpe == 10
    assert parse_fit(recorded(runs[1]))[0].rpe is None
    res = ws.import_uploads([("a.fit", recorded(runs[0], rpe=70)), ("b.fit", recorded(runs[1]))])
    assert len(res.matched) == 2
    rows = {r.session_id: r for r in ws.log()}
    assert rows[runs[0].session.id].rpe == 7 and rows[runs[0].session.id].source == "file"
    assert rows[runs[1].session.id].status == "done" and rows[runs[1].session.id].rpe is None
    client, _ = _client(ws, datetime(2026, 11, 15, 20))
    felt_page = client.get(f"/s/{W1}/{runs[0].session.id}").get_data(as_text=True)
    assert "effort 7/10" in felt_page and "from watch file" in felt_page
    blank = client.get(f"/s/{W1}/{runs[1].session.id}").get_data(as_text=True)
    assert 'name="action" value="rate"' in blank  # no answer on the watch: ask here instead


def _row(week: date, i: int, minutes: int, rpe: int | None) -> LogRow:
    return LogRow(on=week + timedelta(days=i % 7), week=week, session_id=f"s{i}",
                  discipline="run", slot_key="k", planned_min=minutes, status="done",
                  actual_min=minutes, rpe=rpe)


def test_ac_106_a_very_hard_week_holds_the_next_one(tmp_path):
    """AC-106 [e2e-test]: A week's load is minutes x effort (unrated sessions count at the week's average and it says so); a jump of more than 30% on recent weeks is flagged; a week that felt very hard (average 7.5+ over at least 3 rated sessions) makes the next week hold its volume instead of adding 10%, on Season and in the plan alike, with a note saying why"""
    weeks = [date(2026, 10, 5) + timedelta(weeks=i) for i in range(4)]
    rows = [_row(weeks[0], 0, 60, 5), _row(weeks[0], 1, 60, 5),      # 120 min x 5 = 600
            _row(weeks[1], 0, 60, 6), _row(weeks[1], 1, 60, None),   # one unrated: estimated
            _row(weeks[2], 0, 60, 5), _row(weeks[2], 1, 40, 5),
            *[_row(weeks[3], i, 60, 8) for i in range(4)]]           # 240 min x 8 = 1920
    one, two, three, four = weekly_loads(rows)
    assert (one.load, one.mean_rpe, one.estimated, one.spike) == (600, 5.0, False, False)
    assert (two.load, two.estimated, two.rated) == (720, True, 1)
    assert three.load == 500 and not three.hard
    assert four.load == 1920 and four.spike and four.hard  # 3x the recent average, and felt hard
    hard_but_thin = weekly_loads([_row(weeks[0], 0, 60, 9), _row(weeks[0], 1, 60, 9)])[0]
    assert hard_but_thin.mean_rpe == 9 and not hard_but_thin.hard  # two sessions prove nothing
    assert weekly_loads([_row(weeks[0], 0, 60, None)])[0].load is None

    def after_a_week_at(effort: int, folder: str):
        ws = _ws(tmp_path / folder)
        now = datetime(2026, 11, 15, 20)
        ws.now = lambda: now  # type: ignore[method-assign]
        ws.plan_week(W1)
        for p in ws.plan(W1).placements:  # type: ignore[union-attr]
            ws.log_session(W1, p.session.id, "done", rpe=effort)
        now = datetime(2026, 11, 16, 7)
        ws.now = lambda: now  # type: ignore[method-assign]
        return ws, ws.plan_week(W2)

    _, easy = after_a_week_at(5, "easy")
    hard_ws, hard = after_a_week_at(8, "hard")
    did = sum(r.completed_min for r in hard_ws.log() if r.week == W1)
    assert sum(easy.targets.values()) > did  # a normal week adds up to 10%
    assert sum(hard.targets.values()) <= did < sum(easy.targets.values())
    assert any("Last week felt hard" in n and "8/10" in n for n in hard.notes)
    assert not any("felt hard" in n for n in easy.notes)
    chain = {c.week: c for c in hard_ws.volume_chain(W2, W3)}
    assert chain[W2].ramp == 0 and chain[W2].held_after_rpe == 8
    assert chain[W3].ramp == 0.10  # only the week straight after holds
    season = {w.week: w for w in hard_ws.season(W2)}
    assert abs(season[W2].projected_min - sum(hard.targets.values())) <= 10  # Season agrees
    client, token = _client(hard_ws, datetime(2026, 11, 16, 7))
    progress = client.get("/progress").get_data(as_text=True)
    assert "felt very hard: next week holds volume" in progress and "effort 8.0/10" in progress
    planned = client.post("/week/plan", data={"token": token, "week": str(W2)},
                          follow_redirects=True).get_data(as_text=True)
    assert "Last week felt hard" in planned
