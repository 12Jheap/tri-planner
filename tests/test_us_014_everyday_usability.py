"""US-014: Everyday usability and sane training load (v0)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
import yaml
from conftest import make_config, make_session

from planner import cli
from planner.adherence import LogRow, read_log, sync_log
from planner.config import calendar_for_week, load_config, parse_config
from planner.friendly import parse_injury, parse_week, resolve_slots
from planner.replan import Injury, replan
from planner.sessions import CAPS, build_week_sessions
from planner.solver import fit_to_slots, plan_week, slot_uid
from planner.store import InjuryStore
from planner.targets import phase_for, weekly_targets
from planner.wizard import parse_slots, parse_windows, run_wizard, to_yaml

EXAMPLE = Path(__file__).parent.parent / "examples" / "joe.yaml"


def _answers(*lines: str):
    it = iter(lines)
    return lambda _prompt: next(it)


def test_ac_055_weekly_volume_comes_from_target_hours_not_free_time():
    """AC-055 [unit-test]: Weekly volume comes from the athlete's target hours; free time is only a ceiling (build +10%, taper −40%)"""
    lots_free = weekly_targets("sprint", "base", available_minutes=1800, weekly_hours=7)
    assert sum(lots_free.values()) <= 420  # 30h free still means a 7h week
    little_free = weekly_targets("sprint", "base", available_minutes=300, weekly_hours=7)
    assert sum(little_free.values()) <= 240  # 5h free -> at most 80% of it
    build = weekly_targets("sprint", "build", available_minutes=1800, weekly_hours=7)
    taper = weekly_targets("sprint", "taper", available_minutes=1800, weekly_hours=7)
    assert sum(build.values()) > sum(lots_free.values()) > sum(taper.values())
    assert sum(build.values()) <= 462 and sum(taper.values()) <= 252
    with pytest.raises(ValueError):
        weekly_targets("sprint", "base", 600, weekly_hours=0)


def test_ac_056_no_session_is_longer_than_its_race_appropriate_cap():
    """AC-056 [unit-test]: No session exceeds the race-appropriate cap for its kind (e.g. sprint long run ≤ 60')"""
    for race in ("sprint", "olympic"):
        for phase in ("base", "build", "taper"):
            targets = weekly_targets(race, phase, available_minutes=3000)  # huge week
            for s in build_week_sessions(targets, race, phase):  # type: ignore[arg-type]
                if s.discipline == "strength":
                    assert s.duration_min <= 45
                    continue
                assert s.duration_min <= CAPS[race][s.discipline][s.kind], s
    sprint = build_week_sessions(weekly_targets("sprint", "base", 3000), "sprint", "base")
    assert next(s for s in sprint if s.id == "run-long").duration_min == 60


def test_ac_057_key_session_too_long_for_every_slot_is_shortened_not_infeasible(monday):
    """AC-057 [unit-test]: A Key session too long for every slot is shortened to the longest slot that can host it, with a note, instead of failing the week"""
    cfg = make_config(
        [
            {"day": "tue", "start": "16:15", "end": "17:45", "location": "School"},  # 90'
            {"day": "sat", "start": "08:00", "end": "09:00", "location": "Home"},  # 60'
        ]
    )
    slots = calendar_for_week(cfg, monday)
    long_ride = make_session("bike-long", "bike", 120)
    assert plan_week([long_ride], slots, cfg).status == "infeasible"  # the old behaviour
    fitted, notes = fit_to_slots([long_ride], slots, cfg)
    assert fitted[0].duration_min == 90 and fitted[0].id == "bike-long"
    assert fitted[0].value < long_ride.value  # value recomputed for the shorter session
    assert notes and "120' → 90'" in notes[0]
    plan = plan_week(fitted, slots, cfg)
    assert plan.status != "infeasible"
    # Nothing to gain shortening a session nothing can host (no pool anywhere).
    no_pool = make_config([{"day": "sat", "start": "08:00", "end": "09:00", "location": "Home"}])
    same, notes = fit_to_slots([make_session("swim", "swim", 45)], calendar_for_week(no_pool, monday), no_pool)
    assert same[0].duration_min == 45 and not notes


def _row(sid: str, on: date, week: date, status: str = "", **kw) -> LogRow:
    return LogRow(on=on, week=week, session_id=sid, discipline="bike", slot_key=f"k-{sid}",
                  planned_min=60, status=status, **kw)  # type: ignore[arg-type]


def test_ac_058_log_follows_the_plan_without_touching_logged_rows(monday):
    """AC-058 [unit-test]: After a plan or re-plan the log matches it: unlogged rows follow moves, dropped sessions are removed, logged rows never change"""
    other_week = monday - timedelta(days=7)
    log = [
        _row("old", other_week, other_week),
        _row("done", monday, monday, "done", actual_min=55),
        _row("moved", monday, monday),
        _row("dropped", monday, monday),
    ]
    tue = monday + timedelta(days=1)
    planned = [
        _row("done", tue, monday),  # the plan can't rewrite history
        _row("moved", tue, monday),
        _row("new", tue, monday),
    ]
    res = sync_log(log, planned, monday)
    by_id = {r.session_id: r for r in res.rows}
    assert set(by_id) == {"old", "done", "moved", "new"}
    assert by_id["done"].on == monday and by_id["done"].actual_min == 55
    assert by_id["moved"].on == tue
    assert (res.added, res.updated, res.removed) == (1, 1, 1)


def test_ac_059_replan_keeps_history_and_only_redoes_skipped_key_sessions(monday, tmp_path):
    """AC-059 [unit-test]: A re-plan keeps earlier sessions in the stored week and only reschedules Key sessions logged as skipped, as Flex catch-ups"""
    cfg = make_config(
        [
            {"day": "mon", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "tue", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "thu", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "sat", "start": "08:00", "end": "11:00", "location": "Home"},
        ]
    )
    sessions = [make_session("bike-a", "bike", 60), make_session("run-a", "run", 45),
                make_session("bike-b", "bike", 60, key=False)]
    plan = plan_week(sessions, calendar_for_week(cfg, monday), cfg)
    early = [p for p in plan.placements if p.slot.on and p.slot.on <= monday + timedelta(days=1)]
    assert early
    now = datetime.combine(monday + timedelta(days=2), time(8))
    skipped_key = next(p.session.id for p in early if p.session.key)
    # Unlogged past sessions are unknown, so nothing is redone...
    res = replan(cfg, plan, now, skipped_ids=[])
    assert not any(p.session.id.endswith("-redo") for p in res.plan.placements)
    # ...but a skipped Key session comes back once, as Flex.
    res = replan(cfg, plan, now, skipped_ids=[skipped_key])
    redo = next(p for p in res.plan.placements if p.session.id == f"{skipped_key}-redo")
    assert not redo.session.key and redo.reason == "missed_session_rescheduled"

    # Through the CLI: the stored week still shows Monday and Tuesday afterwards.
    joe = tmp_path / "athlete.yaml"
    joe.write_text(EXAMPLE.read_text())
    out = tmp_path / "out"
    assert cli.main(["week", str(joe), "--week", "2026-11-09", "--out", str(out)]) == 0
    rows_before = {r.session_id for r in read_log(out / "log.csv")}
    assert cli.main(["replan", str(joe), "--out", str(out), "--now", "2026-11-11T07:00",
                     "--unavailable", "thu-pm"]) == 0
    rows_after = read_log(out / "log.csv")
    early_ids = {r.session_id for r in rows_after if r.on < date(2026, 11, 11)}
    assert early_ids and early_ids <= rows_before  # history kept in the log
    assert not any(r.on == date(2026, 11, 12) and r.slot_key.startswith("thu-16")
                   for r in rows_after)  # nothing left in the lost slot


def test_ac_060_init_wizard_builds_a_valid_config_from_plain_answers(tmp_path):
    """AC-060 [unit-test]: `init` builds a valid config from plain answers (no YAML knowledge), and unquoted YAML times like 6:30 load as 06:30"""
    ask = _answers(
        "Sam", "olympic", "2027-07-04", "",  # name, race, date, default hours
        "Home", "3,5",  # road bike + run outside
        "Leisure centre", "1,6", "mon-fri 6:30-21:00; weekends 8-18",  # pool hours
        "",  # done adding places
        "6:30-7:30 home, 18:00-19:30 leis", "", "18-19:30 l", "", "", "8-11 home", "9-11",
    )
    said: list[str] = []
    with pytest.raises(StopIteration):  # 'Sunday: 9-11' has two places: it asks again
        run_wizard(ask, said.append)
    assert any("say where" in s for s in said)

    ask = _answers("", "", "", "6", "", "3,5", "", "7-8", "", "7-8", "", "", "8-10", "")
    data = run_wizard(ask, said.append)
    cfg = parse_config(data)
    assert cfg.race == "sprint" and cfg.weekly_hours == 6 and cfg.locations[0].name == "Home"
    assert [s.day for s in cfg.templates["normal"].slots] == ["mon", "wed", "sat"]
    path = tmp_path / "a.yaml"
    path.write_text(to_yaml(data))
    assert load_config(path).templates["normal"].slots[0].start == time(7)

    assert parse_windows("weekdays 16:00-19:00")[0]["days"] == ["mon", "tue", "wed", "thu", "fri"]
    assert parse_windows("16-19") == [{"start": "16:00", "end": "19:00"}]
    with pytest.raises(ValueError, match="overlap"):
        parse_slots("7-9, 8-10", "mon", ["Home"])
    raw = yaml.safe_load("start: 6:30\nend: 07:30\nday: mon\nlocation: Home")
    assert raw["start"] == 390  # what YAML really gives you
    hand = make_config([raw])
    assert hand.templates["t"].slots[0].start == time(6, 30)


def test_ac_061_plain_english_week_injury_and_slot_inputs(monday):
    """AC-061 [unit-test]: Plain-English inputs: --week this/next, --injury run[:days|:date], --unavailable thu / thu-pm / "thu 16:30" / a date"""
    wed = monday + timedelta(days=2)
    assert parse_week("this", wed) == monday
    assert parse_week("next", wed) == monday + timedelta(days=7)
    assert parse_week("2026-11-05", wed) == monday
    assert parse_injury("run", wed) == Injury(discipline="run", until=wed + timedelta(days=7))
    assert parse_injury("run:10", wed).until == wed + timedelta(days=10)
    assert parse_injury("bike:2026-11-20", wed).until == date(2026, 11, 20)
    with pytest.raises(ValueError):
        parse_injury("calf", wed)

    cfg = make_config(
        [
            {"day": "thu", "start": "06:30", "end": "07:30", "location": "School"},
            {"day": "thu", "start": "16:15", "end": "18:15", "location": "School"},
            {"day": "fri", "start": "16:15", "end": "18:15", "location": "School"},
        ]
    )
    slots = calendar_for_week(cfg, monday)
    am, pm, fri = (slot_uid(k) for k in slots)
    assert resolve_slots(["thu"], slots) == [am, pm]
    assert resolve_slots(["thu-pm"], slots) == [pm]
    assert resolve_slots(["thu am"], slots) == [am]
    assert resolve_slots(["thu 16:30"], slots) == [pm]
    assert resolve_slots(["2026-11-06"], slots) == [fri]
    assert resolve_slots([pm], slots) == [pm]  # the raw uid still works
    with pytest.raises(ValueError, match="no slot"):
        resolve_slots(["sun"], slots)


def test_ac_062_log_command_records_sessions_interactively_or_in_one_line(tmp_path, monkeypatch):
    """AC-062 [e2e-test]: `log` records done/skipped/moved with minutes, reason and pain, by asking one session at a time or in one line"""
    joe = tmp_path / "athlete.yaml"
    joe.write_text(EXAMPLE.read_text())
    out = tmp_path / "out"
    assert cli.main(["week", str(joe), "--week", "2026-11-09", "--out", str(out)]) == 0
    monkeypatch.setattr(cli, "_now", lambda _cfg: datetime(2026, 11, 10, 21, 0))
    # Mon: done, 25 minutes, sore. Tue: skipped, pool closed.
    monkeypatch.setattr("builtins.input", _answers("d", "25", "y", "s", "2"))
    assert cli.main(["log", str(joe), "--out", str(out)]) == 0
    rows = {r.on: r for r in read_log(out / "log.csv") if r.on <= date(2026, 11, 10)}
    mon, tue = rows[date(2026, 11, 9)], rows[date(2026, 11, 10)]
    assert (mon.status, mon.actual_min, mon.pain) == ("done", 25, True)
    assert (tue.status, tue.reason) == ("skipped", "facility_closed")
    sid = next(r.session_id for r in read_log(out / "log.csv") if r.on == date(2026, 11, 14))
    assert cli.main(["log", str(joe), "--out", str(out), "--session", sid, "--status", "done"]) == 0
    sat = next(r for r in read_log(out / "log.csv") if r.session_id == sid)
    assert sat.status == "done" and sat.actual_min == sat.planned_min
    assert cli.main(["log", str(joe), "--out", str(out), "--session", "nope", "--status", "done"]) == 2


def test_ac_063_declared_injuries_persist_apply_to_week_and_can_be_cleared(tmp_path):
    """AC-063 [unit-test]: Declared injuries persist across commands, apply when planning a new week, and can be cleared (which also lifts a pain freeze)"""
    store = InjuryStore(tmp_path / "injuries.json")
    today = date(2026, 11, 11)
    store.declare([Injury(discipline="run", until=date(2026, 11, 20))], [], today)
    assert [i.discipline for i in store.active(date(2026, 11, 16))] == ["run"]
    assert store.active(date(2026, 11, 21)) == []

    joe = tmp_path / "athlete.yaml"
    joe.write_text(EXAMPLE.read_text())
    out = tmp_path / "out"
    InjuryStore(out / "injuries.json").declare([Injury(discipline="run", until=date(2026, 11, 20))], [], today)
    assert cli.main(["week", str(joe), "--week", "2026-11-16", "--out", str(out)]) == 0
    week = [r for r in read_log(out / "log.csv") if r.week == date(2026, 11, 16)]
    assert week and not any(r.discipline == "run" for r in week)

    pain = [_row(f"r{i}", today - timedelta(days=i), today, "done", pain=True) for i in (1, 2)]
    for r in pain:
        r.discipline = "run"
    assert len(store.pain_rows(pain)) == 2
    store.declare([], ["run"], today)  # back from the physio
    assert store.active(today) == [] and store.pain_rows(pain) == []


def test_ac_064_today_shows_sessions_with_instructions_and_phase_from_race_date(tmp_path, capsys):
    """AC-064 [e2e-test]: `today` shows today's sessions with plain-English instructions, and the phase is picked from the race date"""
    race = date(2027, 6, 27)
    assert phase_for(date(2026, 11, 9), race) == "base"
    assert phase_for(date(2027, 5, 3), race) == "build"
    assert phase_for(date(2027, 6, 21), race) == "taper"
    assert phase_for(date(2027, 7, 5), race) == "base"
    assert phase_for(date(2027, 5, 3), None) == "base"

    joe = tmp_path / "athlete.yaml"
    joe.write_text(EXAMPLE.read_text())
    out = tmp_path / "out"
    assert cli.main(["week", str(joe), "--week", "2026-11-09", "--out", str(out)]) == 0
    capsys.readouterr()
    assert cli.main(["today", str(joe), "--out", str(out), "--date", "2026-11-14"]) == 0
    text = capsys.readouterr().out
    assert "Saturday 14 November" in text and "Bike long" in text and "easy, steady" in text
    assert cli.main(["today", str(joe), "--out", str(out), "--date", "2026-11-20"]) == 2
    assert cli.main(["week", str(tmp_path / "missing.yaml")]) == 1  # friendly config error
    assert "tri-plan init" in capsys.readouterr().err
