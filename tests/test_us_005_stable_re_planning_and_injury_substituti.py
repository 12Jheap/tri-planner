"""US-005: Stable re-planning and injury substitution (v0)."""

from datetime import date, datetime

from conftest import DAYS, make_config, make_session

from planner.adherence import LogRow
from planner.config import calendar_for_week
from planner.replan import Injury, frozen_by_pain, replan
from planner.solver import plan_week, slot_uid
from planner.store import PlanStore

MON = date(2026, 11, 2)


def _setup():
    cfg = make_config(
        [{"day": d, "start": "16:15", "end": "18:15", "location": "School"} for d in DAYS[:5]]
        + [{"day": d, "start": "08:00", "end": "11:00", "location": "Home"} for d in DAYS[5:]]
    )
    sessions = [
        make_session("bike-long", "bike", 90),
        make_session("bike-thr", "bike", 50, 4),
        make_session("run-long", "run", 60),
        make_session("run-easy", "run", 40, 1, key=False),
        make_session("swim", "swim", 45),
    ]
    plan = plan_week(sessions, calendar_for_week(cfg, MON), cfg)
    assert plan.status in ("optimal", "feasible")
    return cfg, plan


def test_ac_019_freezes_sessions_in_the_next_24_hours_unless_the_athlete_fla():
    """AC-019 [unit-test]: Freezes sessions in the next 24 hours unless the athlete flags them"""
    cfg, plan = _setup()
    first = plan.placements[0]
    now = datetime.combine(first.slot.on, first.slot.start).replace(hour=first.slot.start.hour - 2)
    # Make the first session's slot look terrible: still frozen, so it stays.
    p = {first.slot.key: 0.01}
    res = replan(cfg, plan, now, p_complete=p)
    assert slot_uid(res.plan.placement(first.session.id).slot) == slot_uid(first.slot)
    # Flag it and it's free to move.
    res = replan(cfg, plan, now, p_complete=p, flagged=[first.session.id])
    moved = res.plan.placement(first.session.id)
    assert slot_uid(moved.slot) != slot_uid(first.slot)
    assert moved.reason == "athlete_flagged"


def test_ac_020_penalises_churn_a_re_plan_moves_the_fewest_sessions_needed_a():
    """AC-020 [unit-test]: Penalises churn: a re-plan moves the fewest sessions needed, and every move carries a reason code"""
    cfg, plan = _setup()
    now = datetime(2026, 11, 1, 20, 0)  # Sunday night before the week
    unchanged = replan(cfg, plan, now)
    assert unchanged.moves == []
    # Wednesday's slot disappears (pool closed / exam): only what was there moves.
    wed = next(p for p in plan.placements if p.slot.day == "wed")
    affected = {p.session.id for p in plan.placements if slot_uid(p.slot) == slot_uid(wed.slot)}
    res = replan(cfg, plan, now, unavailable_slots=[slot_uid(wed.slot)])
    assert {m.session_id for m in res.moves} == affected
    assert all(m.reason == "slot_unavailable" for m in res.moves)
    for m in res.moves:
        assert res.plan.placement(m.session_id).reason == "slot_unavailable"


def test_ac_021_an_injury_flag_on_a_discipline_e_g_calf_no_running_for_n_day():
    """AC-021 [unit-test]: An injury flag on a discipline (e.g. calf → no running for N days) remaps its load to allowed disciplines and records the shortfall in a per-discipline debt ledger"""
    cfg, plan = _setup()
    now = datetime(2026, 11, 1, 20, 0)
    res = replan(cfg, plan, now, injuries=[Injury(discipline="run", until=date(2026, 11, 9), note="calf")])
    assert not any(p.session.discipline == "run" for p in res.plan.placements)
    subs = [p for p in res.plan.placements if p.session.id.endswith("-as-bike")]
    assert {p.session.id for p in subs} == {"run-long-as-bike", "run-easy-as-bike"}
    long_sub = res.plan.placement("run-long-as-bike")
    assert long_sub.session.duration_min == 80  # 60' run ≈ 80' bike
    assert long_sub.session.key and long_sub.session.intensity <= 3
    assert res.ledger.minutes == {"run": 100}
    assert all(m.reason == "injury_remap" for m in res.moves if m.session_id.endswith("-as-bike"))
    assert any("debt" in n for n in res.notes)
    # Injury over: running comes back.
    later = replan(cfg, plan, now, injuries=[Injury(discipline="run", until=date(2026, 10, 30))])
    assert any(p.session.discipline == "run" for p in later.plan.placements)


def test_ac_022_two_consecutive_pain_reports_freeze_that_discipline_and_outp():
    """AC-022 [unit-test]: Two consecutive pain reports freeze that discipline and output a "see a physio" message"""
    def log(on, pain, disc="run"):
        return LogRow(on=on, week=MON, session_id=f"{disc}-{on}", discipline=disc,
                      slot_key="k", planned_min=40, status="done", actual_min=40, pain=pain)
    one = [log(date(2026, 10, 27), False), log(date(2026, 10, 29), True)]
    assert frozen_by_pain(one) == {}
    broken = [log(date(2026, 10, 27), True), log(date(2026, 10, 28), False, "bike"),
              log(date(2026, 10, 29), True)]
    frozen = frozen_by_pain(broken)
    assert set(frozen) == {"run"} and "physio" in frozen["run"]
    cfg, plan = _setup()
    res = replan(cfg, plan, datetime(2026, 11, 1, 20, 0), log=broken)
    assert "run" in res.frozen_disciplines
    assert not any(p.session.discipline == "run" for p in res.plan.placements)
    assert any("See a physio" in n for n in res.notes)
    assert all(m.reason == "discipline_frozen" for m in res.moves if "-as-" in m.session_id)


def test_ac_023_every_plan_version_is_appended_never_overwritten_to_a_plan_s(tmp_path):
    """AC-023 [unit-test]: Every plan version is appended (never overwritten) to a `plan_session_version` table"""
    cfg, plan = _setup()
    store = PlanStore(tmp_path / "plan_session_version.jsonl")
    assert store.append(plan, MON, "initial") == 1
    snapshot = store.path.read_text()
    res = replan(cfg, plan, datetime(2026, 11, 1, 20, 0),
                 injuries=[Injury(discipline="run", until=date(2026, 11, 9))])
    assert store.append(res.plan, MON, "calf") == 2
    after = store.path.read_text()
    assert after.startswith(snapshot)  # version 1 untouched
    assert len(after.splitlines()) == len(plan.placements) + len(res.plan.placements)
    v1, v2 = store.load(MON, 1), store.load(MON)
    assert v1.assignment() == plan.assignment()
    assert v2.assignment() == res.plan.assignment()
    assert v2.placement("run-long-as-bike").reason == "injury_remap"
